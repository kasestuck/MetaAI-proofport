"""Finite judge checks using existing pipelines. No model call or host execution.

Scenario definitions/candidates are authored inputs. Golden observations and all
results come from actual Docker checks; a missing prerequisite cannot pass.
"""
from copy import deepcopy
from hashlib import sha256
from html import escape
import json
from pathlib import Path, PurePosixPath
from uuid import uuid4
from unittest.mock import patch

from backend.core.comparator import compare_cases
from backend.core.evidence import Evidence,entry_hash
from backend.core.models import Metrics,RunState
from backend.core.projects import copy_project,linked
from backend.core.recorder import invoke,load_cases
from backend.core.runs import Run,RunStore,hashes_for
from backend.core.security import SCANNER_IMAGE,findings_for,scan
from backend.languages.base import hashes,inventory
from backend.php.fixes import verify_fixes
from backend.php.pipeline import PHPJob,execute as php_execute
from backend.php.protocol import load_cases as php_cases
from backend.php.runtime import PHPExecutor,local_images,source_hashes
from backend.sandbox.runner import DockerRunner
from backend.security.engine import SecurityFixEngine,project_hashes
from backend.security.models import FixProposal

ROOT=Path(__file__).resolve().parents[1]
IDS=('01_python_legacy_migration','02_python_math_edge_cases','03_python_compatibility',
     '04_python_sql_injection','05_python_unsafe_eval','06_python_secrets_crypto',
     '07_php_legacy_migration','08_php_xss','09_php_command_injection','10_php_security_regression')
IMAGES={'2.7':'python:2.7','3.12':'python:3.12-slim','3.13':'python:3.13-slim',
        '7.4':'php:7.4.33-cli','8.3':'php:8.3.36-cli'}


def reference(name,root=ROOT):
    if not isinstance(name,str) or '\\' in name or ':' in name: raise ValueError('Invalid judge reference')
    parts=name.split('/')
    if any(p in {'','.','..'} or p.startswith('.') for p in parts) or parts[0] not in {'judge_tests','samples','tests'}:
        raise ValueError('References must stay in owned scenario/demo/fixture directories')
    if parts[0]=='tests' and (len(parts)<2 or parts[1]!='fixtures'): raise ValueError('Only owned test fixtures may be referenced')
    path=root.joinpath(*parts)
    if not path.exists() or not path.resolve().is_relative_to(root.resolve()) or any(linked(p) for p in (path,*path.parents)):
        raise ValueError('Absent/linked/escaped judge reference')
    return path


def dump(path,data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True,ensure_ascii=True),encoding='utf-8')


def check(result,name,passed,detail=''):
    if type(passed) is not bool: raise ValueError('Checks must be explicit booleans')
    result['checks'].append({'name':name,'required':True,'passed':passed,'detail':detail})


def suite_passed(results):
    return bool(results) and all(r['status'] in {'PASS','NEEDS_REVIEW'} and r['checks']
        and any(c['required'] for c in r['checks'])
        and all(c['passed'] is True for c in r['checks'] if c['required']) for r in results)


def passing_tests(data):
    outcomes=data.get('outcomes',[]);count=data.get('tests_run')
    return (type(count) is int and count>0 and count==len(outcomes)==len({t['id'] for t in outcomes})
            and all(t['status']=='passed' for t in outcomes))


def python_pair(config,out,evidence,result,runner):
    source=reference(config['source']);cases=load_cases(reference(config['cases']))
    original=out/'original';copy_project(source,original)
    target=out/'candidate';copy_project(source,target)
    for name,candidate in config.get('candidates',{}).items():
        if PurePosixPath(name).name!=name or not name.endswith('.py'): raise ValueError('Single application source candidate required')
        (target/name).write_bytes(reference(candidate).read_bytes())
    src=IMAGES[config['source_version']];dst=IMAGES[config['target_version']]
    compiled=invoke(runner,src,original,'compile',evidence=evidence)
    golden=invoke(runner,src,original,'cases',cases,evidence)
    baseline=invoke(runner,src,original,'tests',evidence=evidence)
    syntax=invoke(runner,dst,target,'compile',evidence=evidence)
    observed=invoke(runner,dst,target,'cases',cases,evidence)
    tests=invoke(runner,dst,target,'tests',evidence=evidence)
    comparisons=compare_cases(golden['cases'],observed['cases'])
    ids=lambda data:{x['id'] for x in data['outcomes']}
    check(result,'source_syntax',not compiled['errors'])
    check(result,'source_tests',passing_tests(baseline))
    check(result,'target_syntax',not syntax['errors'])
    check(result,'golden_comparisons',len(comparisons)==config['expected_cases'] and all(c['matches'] for c in comparisons))
    check(result,'existing_tests_same_ids',ids(baseline)==ids(tests) and passing_tests(tests))
    result['verification']={'golden_matched':sum(c['matches'] for c in comparisons),'golden_total':len(comparisons),
        'source_tests':baseline,'target_tests':tests,'source_runtime':golden['python'],'target_runtime':observed['python'],
        'comparisons':comparisons,'behavior_scope':'Only recorded inputs and existing test IDs'}
    for name,data in {'golden':golden,'observed':observed,'source-tests':baseline,'target-tests':tests}.items(): dump(out/(name+'.json'),data)


def python_migration(config,out,evidence,result,runner):
    from backend.core.pipeline import execute
    source=reference(config['source']);before=hashes_for(source)
    run=Run(RunState(modules=[],hashes={**before,'unchanged':None},metrics=Metrics()),source,before,{},1,runner=runner)
    settings={'PROOFPORT_CASES_FILE':str(reference(config['cases'])),'PROOFPORT_FIXTURE_FILE':str(reference(config['fixture']))}
    execute(run,'pipeline',out,settings,'fixtures');RunStore._finish(run)
    check(result,'migration_done',run.state.status=='done')
    comparisons=run.verification.get('comparisons',[])
    check(result,'golden_comparisons',len(comparisons)==90 and all(c['matches'] for c in comparisons))
    for field in ('legacy_tests','target_tests'):
        tests=run.verification.get(field,{})
        check(result,field,tests.get('tests_run')==10 and all(t['status']=='passed' for t in tests.get('outcomes',[])))
    check(result,'pipeline_evidence',run.evidence.verify() and run.state.hashes.get('unchanged') is True)
    check(result,'no_model_usage',run.verification.get('ai_migration') is False and run.state.metrics.tokens_in==run.state.metrics.tokens_out==0)
    evidence.append('pipeline_receipt',str(run.workspace.relative_to(out)))
    result['verification']={'golden_matched':sum(c['matches'] for c in comparisons),'golden_total':len(comparisons),
        'source_tests':run.verification.get('legacy_tests'),'target_tests':run.verification.get('target_tests'),
        'pipeline_artifacts':str(run.workspace.relative_to(out))}


def python_security(config,out,evidence,result,runner):
    source=reference(config['source']);working=out/'accepted';copy_project(source,working)
    cases=load_cases(reference(config['cases']))
    golden=invoke(runner,'python:3.12-slim',working,'cases',cases,evidence)['cases']
    baseline=invoke(runner,'python:3.12-slim',working,'tests',evidence=evidence)
    check(result,'baseline_tests',passing_tests(baseline))
    scanned=scan(runner,working,evidence);_,findings=findings_for(scanned)
    check(result,'required_findings_detected',not scanned['errors'] and set(config['rules'])<={f['scanner_test'] for f in findings})
    engine=SecurityFixEngine(runner=runner,working=working,original=source,original_hashes=project_hashes(source),
        artifacts=out/'attempts',cases=cases,golden=golden,existing_tests=baseline,evidence=evidence)
    engine.artifacts.mkdir();attempts=[];before=project_hashes(working)
    for rule in config['proposals']:
        chosen=[f for f in findings if f['scanner_test']==rule['rule'] and f['file']=='subject.py']
        check(result,'finding_binding_'+rule['rule'],len(chosen)==1)
        if len(chosen)!=1: continue
        code=reference(rule['candidate']).read_text(encoding='utf-8')
        proposal=FixProposal(finding_id=chosen[0]['id'],proposed_code=code,explanation='Explicit authored offline judge proposal, not Meta AI.',
            behavior_impact='changes',review_areas=rule['review_areas'],confidence=1,mode='fixture')
        attempt=engine._attempt(chosen[0],proposal,scanned);attempts.append(attempt)
        checks=attempt.get('checks',{})
        check(result,'candidate_syntax_'+rule['rule'],checks.get('syntax',{}).get('passed') is True)
        check(result,'behavior_change_detected_'+rule['rule'],checks.get('golden',{}).get('ran') is True and checks['golden'].get('passed') is False)
        check(result,'existing_tests_ran_'+rule['rule'],checks.get('existing_tests',{}).get('ran') is True)
        check(result,'review_and_rollback_'+rule['rule'],attempt['status']=='needs_review' and not attempt['applied'] and attempt['rolled_back'])
        check(result,'rescan_'+rule['rule'],attempt.get('rescan',{}).get('passed') is True)
    check(result,'accepted_copy_unchanged',project_hashes(working)==before)
    result['verification']={'findings_before':findings,'attempts':attempts,'golden_total':len(golden),
        'baseline_tests':baseline,'fixed':[],'decision':'needs_review','reachability':'Potential static risks; no external exploit tested'}
    dump(out/'golden.json',golden)


def php_security(config,out,evidence,result,runner):
    source=reference(config['source']);working=out/'baseline';copy_project(source,working)
    executor=PHPExecutor(runner=runner,images=local_images(runner),evidence=evidence)
    profile=php_cases(reference(config['cases']))
    golden=executor.cases(working,'7.4',profile);baseline=executor.tests(working,'7.4')
    check(result,'baseline_tests',baseline['passed'] and baseline['tests_run']>0)
    class Generator:
        mode='fixture'
        def generate(self,finding,code):
            if finding['scanner_test'] not in config['rules']: return None
            return FixProposal(finding_id=finding['id'],explanation='Authored offline fixture, not a model response.',
                proposed_code=reference(config['candidate']).read_text(encoding='utf-8'),
                behavior_impact=config['behavior_impact'],review_areas=config['review_areas'],confidence=1,mode='fixture')
    artifacts=out/'attempts';artifacts.mkdir()
    accepted,report,_=verify_fixes(working=working,original=source,original_hashes=source_hashes(source),artifacts=artifacts,
        profile=profile,golden=golden,baseline_tests=baseline,executor=executor,evidence=evidence,generator=Generator(),verification_versions=('7.4','8.3'))
    check(result,'required_findings_detected',set(config['rules'])<={f['scanner_test'] for f in report['findings_before']})
    check(result,'final_copy_verified',report['verified'] is True)
    check(result,'proposal_was_verified',len(report['attempts'])==1 and set(report['attempts'][0]['checks']['runtime_checks'])=={'7.4','8.3'})
    if config['expected_status']=='PASS':
        check(result,'narrow_hardening_accepted',len(report['fixed'])==1 and accepted!=working)
        check(result,'warning_removed_with_tests',report['attempts'][0]['security_rescan']['target_removed'] and report['attempts'][0]['checks']['passed'])
    else:
        check(result,'needs_review_and_rollback',len(report['needs_review'])==1 and not report['fixed'] and accepted==working)
        check(result,'behavior_difference_measured',report['attempts'][0]['checks']['golden']['passed'] is False)
    result['verification']=report
    dump(out/'golden.json',golden)


def php_pipeline(config,out,evidence,result,runner):
    job=PHPJob(reference(config['source']),cases=reference(config['cases']),fixture=reference(config['fixture']),max_iterations=1,
        security_fixture=reference(config['security_fixture']) if config.get('security_fixture') else None)
    data,artifacts=php_execute(job,runner=runner,artifacts=out/'pipeline')
    check(result,'migration_done',data['status']=='done')
    check(result,'golden_comparisons',data.get('golden_case_count')==22 and data.get('behavior_verified') is True)
    for field in ('source_tests','target_tests'):
        check(result,field,data.get(field,{}).get('tests_run')==9 and data[field]['passed'] is True)
    check(result,'pipeline_integrity',data['chain_intact'] and data['originals_unchanged'])
    check(result,'no_model_usage',data['model_calls']==0 and data['ai_migration'] is False)
    if config.get('security_fixture'):
        fix=data.get('security_fix',{})
        check(result,'success_review_and_syntax_rejection',[a['status'] for a in fix.get('attempts',[])]==['fixed','needs_review','fix_reverted'])
        check(result,'rollback_preserved_only_verified_fix',len(fix.get('fixed',[]))==1 and fix['source_unchanged'] and fix['evidence_chain_intact'])
    result['verification']={'pipeline_artifacts':str(artifacts.relative_to(out)),'golden_total':data.get('golden_case_count'),
        'source_tests':data.get('source_tests'),'target_tests':data.get('target_tests'),'security_fix':data.get('security_fix')}
    evidence.append('pipeline_receipt',str(artifacts.relative_to(out)))


WORKERS={'python_migration':python_migration,'python_pair':python_pair,'python_security':python_security,
         'php_migration':php_pipeline,'php_security':php_security}


def run_suite(selected=IDS,*,runner=None,root=ROOT):
    # Restore the class attributes afterward, including on failure. No environment
    # or RunStore setting is changed, and in-process callers cannot leak this guard.
    import backend.llm.client as llm
    def forbidden(*a,**kw): raise RuntimeError('Judge suite forbids all model generation')
    with patch.object(llm,'OpenAI',forbidden),patch.object(llm.LLMClient,'complete',forbidden):
        return _run_suite(selected,runner=runner,root=root)


def _run_suite(selected=IDS,*,runner=None,root=ROOT):
    if not selected or len(set(selected))!=len(selected) or any(name not in IDS for name in selected): raise ValueError('Select fixed judge scenario IDs')
    runner=runner or DockerRunner();docker=runner.available()
    destination=root/'backend/.work'/('judge-'+uuid4().hex[:8]);destination.mkdir(parents=True)
    results=[]
    for name in selected:
        config=json.loads((root/'judge_tests'/name/'scenario.json').read_text(encoding='utf-8'))
        if config['id']!=name or config['worker'] not in WORKERS: raise ValueError('Invalid scenario binding')
        out=destination/name[:2];out.mkdir();evidence=Evidence();evidence.bind(out/'evidence.log')
        source=before=None
        result={'name':name,'language':config['language'],'operation':config['operation'],
            'source_version':config['source_version'],'target_version':config['target_version'],
            'mode':'offline_authored_fixtures_not_AI','model_calls':0,'checks':[],'status':'FAIL','reason':''}
        evidence.append('judge_started',name+'; authored offline inputs, no Meta calls')
        try:
            source=reference(config['source'],root);base,files=inventory(source);before=hashes(base,files)
            result['source_sha256']=before
            inputs={root/'judge_tests'/name/'scenario.json'}
            for key in ('cases','fixture','security_fixture','candidate'):
                if config.get(key): inputs.add(reference(config[key],root))
            inputs.update(reference(p,root) for p in config.get('candidates',{}).values())
            inputs.update(reference(p['candidate'],root) for p in config.get('proposals',[]))
            result['input_sha256']={p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in inputs}
            missing=[]
            for image in config['required_images']:
                if image not in set(IMAGES.values())|{SCANNER_IMAGE}: raise ValueError('Unconfigured runtime/scanner')
                try:
                    if not docker: missing.append(image)
                    else: runner.image_id(image)
                except RuntimeError: missing.append(image)
            if missing:
                result.update(status='SKIP',reason='Mandatory Docker/image checks unavailable; nothing was executed.')
                result['missing_images']=missing;check(result,'mandatory_dynamic_checks',False,result['reason'])
                evidence.append('judge_skipped',result['reason'])
            else:
                WORKERS[config['worker']](config,out,evidence,result,runner)
                good=bool(result['checks']) and all(c['passed'] is True for c in result['checks'])
                result.update(status=config['expected_status'] if good else 'FAIL',reason='Required assertions passed; inspect review status and finite scope.' if good else 'One or more required assertions failed.')
        except Exception as exc:
            result.update(status='FAIL',reason='Execution/verification error; no fallback.',error_type=type(exc).__name__)
            check(result,'execution_completed',False)
            evidence.append('error',type(exc).__name__+'; private details withheld')
        try:
            _,after_files=inventory(source);unchanged=before is not None and hashes(source,after_files)==before
        except (OSError,ValueError,TypeError): unchanged=False
        check(result,'original_source_hashes_unchanged',unchanged)
        evidence.append('judge_finished',result['status']+'; originals unchanged='+str(unchanged))
        result['events']=evidence.since(0);result['evidence_chain_intact']=evidence.verify()
        check(result,'evidence_chain',result['evidence_chain_intact'])
        if not unchanged or not result['evidence_chain_intact']: result.update(status='FAIL',reason='Source/evidence integrity failed')
        result['images']={tag:runner._images[tag] for tag in config['required_images'] if tag in runner._images}
        dump(out/'result.json',result)
        (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><h1>Offline judge scenario, not AI</h1><pre>'+escape(json.dumps(result,indent=2))+'</pre>',encoding='utf-8')
        dump(out/'receipt.json',{p:sha256((out/p).read_bytes()).hexdigest() for p in ('result.json','report.html','evidence.log')})
        results.append(result)
    summary={'mode':'offline_authored_fixtures_not_AI','model_calls':0,'docker_available':docker,
        'scenarios':results,'counts':{s:sum(r['status']==s for r in results) for s in ('PASS','FAIL','SKIP','NEEDS_REVIEW')},
        'mandatory_checks_passed':suite_passed(results),'scope':'Finite assertions only. Expected review is not accepted remediation; mandatory skips/failures make exit nonzero.'}
    path=destination/'summary.json';dump(path,summary)
    return summary,path


def verify_summary(path):
    """Check saved result bytes/chain and recompute the required-check decision."""
    path=Path(path).absolute()
    if path.stat().st_size>20_000_000 or any(linked(p) for p in (path,*path.parents)): raise ValueError('Unsafe/oversized summary')
    summary=json.loads(path.read_text(encoding='utf-8'))
    results=summary['scenarios']
    if not 1<=len(results)<=10 or len({r['name'] for r in results})!=len(results): raise ValueError('Invalid saved selection')
    for result in results:
        if result['name'] not in IDS: raise ValueError('Unknown saved scenario')
        folder=path.parent/result['name'][:2]
        if linked(folder): raise ValueError('Linked scenario artifacts')
        receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
        if set(receipt)!={'result.json','report.html','evidence.log'}: raise ValueError('Invalid scenario receipt')
        for name,value in receipt.items():
            file=folder/name
            if linked(file) or file.stat().st_size>20_000_000 or sha256(file.read_bytes()).hexdigest()!=value: raise ValueError('Saved scenario bytes differ')
        if json.loads((folder/'result.json').read_text(encoding='utf-8'))!=result: raise ValueError('Summary/result differs')
        events=[json.loads(line) for line in (folder/'evidence.log').read_text(encoding='utf-8').splitlines()]
        if events!=result['events']: raise ValueError('Evidence differs from result')
        previous='0'*64
        for index,event in enumerate(events,1):
            if event['seq']!=index or event['prev_hash']!=previous or event['entry_hash']!=entry_hash(event): raise ValueError('Broken judge evidence')
            previous=event['entry_hash']
    if summary['mandatory_checks_passed'] is not suite_passed(results): raise ValueError('Saved suite decision differs')
    expected={s:sum(r['status']==s for r in results) for s in ('PASS','FAIL','SKIP','NEEDS_REVIEW')}
    if summary['counts']!=expected: raise ValueError('Saved counts differ')
    return summary
