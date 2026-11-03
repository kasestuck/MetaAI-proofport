"""P8.3 preparation and a separately approved, bounded PHP module live trial.

Default preparation never constructs a model client. No fixture manifest,
automatic fallback, dependency installation or public live API is enabled.
"""

import argparse
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4

from backend.ai import artifacts
from backend.ai.first_live import ROOT, P82_LIMITS, digest, local_settings, public_limits, write, notify
from backend.ai.provider import ModelSession, PHPModuleLiveApproval, StructuredTranslator
from backend.core.evidence import Evidence
from backend.core.projects import copy_project, linked
from backend.languages.base import AdapterError, inventory
from backend.languages.php import analyze_php
from backend.php.protocol import compare, load_cases
from backend.php.runtime import PHPExecutor, local_images, source_hashes
from backend.php.verification import verify
from backend.llm.client import LLMClient, ModelUnavailable
from backend.sandbox.runner import DockerRunner, SandboxError


SOURCE = ROOT / 'tests/fixtures/php_shop'
CASES = ROOT / 'tests/fixtures/php_profiles/cases.json'
FILE = 'src/legacy.php'
LIMITS = P82_LIMITS  # Frozen: 2 calls, 9216 input / 3072 output, USD .05, 30s.


def unchanged(before):
    if source_hashes(SOURCE) != before:
        raise ModelUnavailable('Original PHP project changed; no success claim.', 'source_changed')


def prepare(env_file, *, runner=None, progress=None, isolate_settings=False):
    settings = local_settings(env_file, inherit_environment=False) if isolate_settings else local_settings(env_file)
    before = source_hashes(SOURCE)
    if any(settings['MODEL_API_KEY'].encode() in p.read_bytes() for p in inventory(SOURCE)[1]):
        raise ModelUnavailable('Credential found in input; stopped before copying.', 'credential_in_prompt')
    runner = runner or DockerRunner()
    images = local_images(runner)
    workspace = ROOT / 'backend/.work' / ('p83-php-' + uuid4().hex)
    if any(linked(p) for p in (workspace, *workspace.parents)): raise ValueError('Link-free workspace required')
    workspace.mkdir(parents=True)
    evidence = Evidence(); evidence.bind(workspace / 'preparation.log')
    original = workspace / 'original'; copy_project(SOURCE, original)
    if source_hashes(original) != before: raise ValueError('Copy differs from original bytes')
    profile = load_cases(CASES)
    scoped = [c for c in profile['cases'] if c['file'] == FILE]
    if len(profile['cases']) != 22 or len(scoped) != 5: raise ValueError('Review changed PHP case scope before live preparation')
    notify(progress, "analyzing")
    analysis = analyze_php(original, source_version='7.4', target_version='8.3', evidence=evidence).analysis
    if analysis['diagnostics']: raise ValueError('PHP lexical analysis incomplete')
    executor = PHPExecutor(runner=runner, images=images, evidence=evidence)
    notify(progress, "recording")
    source_lint = executor.lint(original,'7.4')
    source_tests = executor.tests(original,'7.4')
    golden = executor.cases(original,'7.4',profile)
    if not source_lint['passed'] or not source_tests['passed'] or source_tests['tests_run'] != 9:
        raise ValueError('PHP baseline syntax/existing tests failed or changed')
    if not all(c['matches'] for c in compare(profile,golden,golden)): raise ValueError('Baseline did not exercise declared cases')
    target_runtime = executor.invoke(original,'8.3','version')
    target_lint = executor.lint(original,'8.3')
    unchanged(before)
    for name,data in {'cases.json':profile,'golden.json':golden,'source-tests.json':source_tests,
                      'analysis.json':analysis,'source-lint.json':source_lint,'target-lint.json':target_lint,
                      'target-runtime.json':target_runtime}.items(): write(workspace / name,data)
    manifest = {'profile':'p8.3-php','file':FILE,'model':settings['MODEL_NAME'],
        'source_sha256':sha256((original / FILE).read_text(encoding='utf-8').encode()).hexdigest(),
        'original_hashes':before,'images':images,'limits':public_limits(LIMITS),
        'artifacts':{p.name:digest(p) for p in workspace.iterdir() if p.is_file() and p.suffix == '.json'}}
    write(workspace / 'prepared.json',manifest)
    report = {'phase':'preparation','status':'awaiting_paid_approval','language':'php',
        'execution_mode':'offline_baseline_preparation','ai_migration':False,'model_calls':0,
        'estimated_cost_usd':0,'max_reserved_cost_usd':'0.049152','limits':public_limits(LIMITS),
        'target_file':FILE,'module_golden_cases':len(scoped),'golden_case_count':len(golden),
        'source_syntax':source_lint,'source_tests':source_tests,'source_php':source_tests['php'],
        'target_runtime':target_runtime,'target_original_syntax':target_lint,
        'syntax_passed':None,'tests_passed':None,'behavior_verified':None,
        'original_hashes':before,'originals_unchanged':True,'images':images,'isolation':'docker',
        'limitations':['Only source baseline and target runtime/original lint ran; no migration candidate or target behavior success.',
                       'All 22 cases and nine unchanged native tests will verify one changed file; finite coverage only.',
                       'Only deprecation notices may differ, as explicitly recorded in the existing profile.']}
    evidence.append('baseline_ready','PHP 7.4 actual baseline recorded; PHP 8.3 runtime/original lint checked. No model call.')
    artifacts.export(workspace,report,evidence,stem='baseline-report')
    artifacts.verify(workspace,unchanged,stem='baseline-report')
    return report,workspace


def validate_prepared(workspace, runner):
    workspace = Path(workspace).absolute()
    if workspace.parent != ROOT / 'backend/.work' or not workspace.name.startswith('p83-php-'):
        raise ValueError('Expected retained PHP preparation workspace')
    if any(linked(p) for p in (workspace, *workspace.parents)): raise ValueError('Workspace cannot follow links')
    artifacts.verify(workspace,unchanged,stem='baseline-report')
    m = json.loads((workspace / 'prepared.json').read_text(encoding='utf-8'))
    if m['profile'] != 'p8.3-php' or m['file'] != FILE or m['limits'] != public_limits(LIMITS) or m['model'] != 'muse-spark-1.3':
        raise ValueError('Prepared scope or budget changed')
    if set(m['artifacts']) != {'cases.json','golden.json','source-tests.json','analysis.json','source-lint.json','target-lint.json','target-runtime.json'}:
        raise ValueError('Prepared PHP artifacts changed')
    if any(digest(workspace / name) != value for name,value in m['artifacts'].items()):
        raise ValueError('Prepared PHP data changed')
    unchanged(m['original_hashes'])
    if source_hashes(workspace / 'original') != m['original_hashes']: raise ValueError('Working original changed')
    if load_cases(workspace / 'cases.json') != load_cases(CASES): raise ValueError('Golden inputs changed')
    if sha256((workspace / 'original' / FILE).read_text(encoding='utf-8').encode()).hexdigest() != m['source_sha256']:
        raise ValueError('Source binding changed')
    if local_images(runner) != m['images']: raise ValueError('Prepared runtime images changed')
    return m


def repair_feedback(checks, profile, golden, observed):
    inputs = {c['id']:c for c in profile['cases']}
    old = {c['id']:c for c in golden}; new = {c['id']:c for c in observed}
    failed = [c for c in checks['golden'].get('comparisons',[]) if not c['matches']]
    if len(failed) > 8 or any(inputs[c['id']]['file'] != FILE for c in failed):
        raise ModelUnavailable('Repair exceeds the approved module scope.', 'needs_review')
    ignored = {'id'} | ({'deprecations'} if 'deprecation_notices' in profile.get('allowed_differences',[]) else set())
    data = {'syntax':{'ran':checks['syntax']['ran'],'passed':checks['syntax']['passed'],
                     'failed_files':[f for f in checks['syntax'].get('files',[]) if not f['passed']]},
        'existing_tests':{'ran':checks['existing_tests']['ran'],'passed':checks['existing_tests']['passed'],
                         'failed':[t for t in checks['existing_tests'].get('outcomes',[]) if t['status'] != 'passed']},
        'golden':{'passed':checks['golden']['passed']},'repair_requested':True,
        'allowed_differences':profile.get('allowed_differences',[]),
        'failing_cases':[{'input':inputs[c['id']],
                         'expected':{k:v for k,v in old[c['id']].items() if k not in ignored},
                         'actual':{k:v for k,v in new[c['id']].items() if k not in ignored}} for c in failed]}
    if len(json.dumps(data,ensure_ascii=True).encode()) > 16384:
        raise ModelUnavailable('PHP repair feedback exceeds bounded context.', 'input_budget_exceeded')
    return data


def execute(workspace, env_file, *, acknowledged=False, runner=None, client=None, progress=None, isolate_settings=False):
    if acknowledged is not True:
        raise ModelUnavailable('Separate paid permission and explicit acknowledgment required.', 'approval_required')
    settings = local_settings(env_file, inherit_environment=False) if isolate_settings else local_settings(env_file)
    runner = runner or DockerRunner()
    workspace = Path(workspace).absolute()
    manifest = validate_prepared(workspace,runner)
    write(workspace / 'execution_started.json',{'manifest_sha256':digest(workspace / 'prepared.json'),
                                              'limits':public_limits(LIMITS),'file':FILE,'mode':'live'})
    evidence = Evidence(); evidence.bind(workspace / 'evidence.log')
    evidence.append('prepared_baseline',digest(workspace / 'prepared.json'))
    original = workspace / 'original'; candidate = workspace / 'candidate'; copy_project(original,candidate)
    executor = PHPExecutor(runner=runner,images=manifest['images'],evidence=evidence)
    profile = load_cases(workspace / 'cases.json')
    golden = json.loads((workspace / 'golden.json').read_text(encoding='utf-8'))
    baseline = json.loads((workspace / 'source-tests.json').read_text(encoding='utf-8'))
    source = (original / FILE).read_text(encoding='utf-8')
    report = {'phase':'execution','status':'failed','language':'php','mode':'live','ai_migration':False,
        'target_file':FILE,'limits':public_limits(LIMITS),'original_hashes':manifest['original_hashes'],
        'images':manifest['images'],'source_php':baseline['php'],'source_tests':baseline,
        'golden_case_count':len(golden),'iterations':[],'isolation':'docker'}
    client = client or LLMClient(env_file,mode='live',allow_live=True,limits=LIMITS)
    session = None
    try:
        if (client.mode != 'live' or client.limits != LIMITS or client.model != settings['MODEL_NAME']
                or client.base_url != settings['MODEL_BASE_URL'] or client._api_key != settings['MODEL_API_KEY']
                or client._price_in != Decimal('1.25') or client._price_out != Decimal('4.25')):
            raise ModelUnavailable('Unexpected PHP client/configuration; no fallback.', 'live_not_authorized')
        session = ModelSession(client,'php',evidence=evidence,response_dir=workspace,case_feedback=True,
            live_approval=PHPModuleLiveApproval(FILE,manifest['source_sha256']))
        translator = StructuredTranslator(session)
        previous = feedback = None
        for iteration in range(1,LIMITS.max_calls+1):
            unchanged(manifest['original_hashes'])
            notify(progress, "translating" if iteration == 1 else "fixing", iteration=iteration)
            code = translator.translate(FILE,source,previous,feedback)
            notify(progress, "testing", iteration=iteration, usage=[asdict(c) for c in client.calls], model_calls=len(client.attempts))
            (candidate / FILE).write_bytes(code.encode())
            saved = workspace / ('iteration_%02d' % iteration); copy_project(candidate,saved)
            checks = verify(executor,candidate,'8.3',profile=profile,golden=golden,baseline_tests=baseline)
            record = {'iteration':iteration,'candidate':saved.name,'checks':checks}
            report['iterations'].append(record)
            if progress:
                notify(progress,"verified_iteration",iteration=iteration,
                    golden_matched=checks['golden'].get('matched',0),golden_total=checks['golden'].get('total',0),
                    tests_passed=sum(t['status']=='passed' for t in checks['existing_tests'].get('outcomes',[])),
                    tests_total=checks['existing_tests'].get('tests_run',0))
            write(workspace / ('verification_%02d.json' % iteration),record)
            evidence.append('candidate_verified',json.dumps({'iteration':iteration,'passed':checks['passed'],
                'sha256':digest(workspace / ('verification_%02d.json' % iteration))},sort_keys=True))
            unchanged(manifest['original_hashes'])
            current = source_hashes(candidate)
            if set(current) != set(manifest['original_hashes']) or any(current[p] != v for p,v in manifest['original_hashes'].items() if p != FILE):
                raise ValueError('Non-target files changed')
            if checks['passed']:
                report.update(status='done',ai_migration=True,accepted_copy='candidate',
                    syntax_passed=True,tests_passed=True,behavior_verified=True)
                break
            if iteration < LIMITS.max_calls:
                observed = []
                if checks['golden']['ran']:
                    observed = json.loads((workspace / checks['recording_id'] / 'observed-cases.json').read_text(encoding='utf-8'))
                previous = code; feedback = repair_feedback(checks,profile,golden,observed)
        if report['status'] != 'done': report['error'] = {'code':'php_verification_failed'}
    except (ModelUnavailable,AdapterError,SandboxError,ValueError,OSError) as exc:
        report['error'] = {'code':getattr(exc,'code','local_verification_error')}
    finally:
        client.close()
    report.update(model=client.model,model_calls=len(client.attempts),usage=[asdict(c) for c in client.calls],
                  model_attempts=[asdict(a) for a in client.attempts],budget=client.budget_snapshot(),
                  responses=session.responses if session else [],originals_unchanged=source_hashes(SOURCE)==manifest['original_hashes'],
                  chain_intact=evidence.verify(),ai_fix_loop_used=len(client.attempts)>1)
    if not report['originals_unchanged'] or not report['chain_intact']:
        report.update(status='failed',ai_migration=False,error={'code':'integrity_failed'})
    if report['status'] != 'done':
        candidate.rename(workspace / 'rejected_final'); copy_project(original,candidate)
        report.pop('accepted_copy',None); report.update(ai_migration=False,rollback=True)
        if evidence.verify(): evidence.append('rollback','Rejected PHP candidate retained; working copy restored to original.')
    if session and session.private.clean(report) != report: raise ModelUnavailable('Private report data withheld.', 'model_sensitive_response')
    artifacts.export(workspace,report,evidence)
    artifacts.verify(workspace,unchanged)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',type=Path,default=ROOT / 'backend/.tmp/meta-smoke.env')
    p.add_argument('--prepare',action='store_true')
    p.add_argument('--execute',action='store_true')
    p.add_argument('--workspace',type=Path)
    p.add_argument('--acknowledge-paid-api',action='store_true')
    args = p.parse_args(argv)
    try:
        if args.prepare and not any((args.execute,args.workspace,args.acknowledge_paid_api)):
            report,workspace = prepare(args.env_file)
            print(json.dumps({k:report[k] for k in ('status','model_calls','golden_case_count','source_php','max_reserved_cost_usd')}))
            print('Retained workspace: ' + str(workspace)); return 0
        if args.execute and args.acknowledge_paid_api and args.workspace and not args.prepare:
            report = execute(args.workspace,args.env_file,acknowledged=True)
            print(json.dumps({k:report.get(k) for k in ('status','ai_migration','model_calls','budget','error')}))
            return 0 if report['status']=='done' else 2
        raise ModelUnavailable('Choose free preparation or separately approved explicit execution.', 'approval_required')
    except (ModelUnavailable,AdapterError,SandboxError,ValueError,OSError) as exc:
        print(json.dumps({'status':'blocked','code':getattr(exc,'code','php_preparation_failed'),'notice':'No fallback; private details withheld.'})); return 2


if __name__ == '__main__': raise SystemExit(main())
