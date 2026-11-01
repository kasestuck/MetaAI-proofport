"""One protected eval proposal: free baseline, separately approved bounded live trial.

This is not migration. Behavior checks stay on Python 2.7; Python 3.12 syntax is
additional evidence only. B307 never becomes automatically fixed by this trial.
"""

import argparse
import ast
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4

from backend.ai import artifacts
from backend.ai.first_live import ROOT, P82_LIMITS, digest, local_settings, public_limits, suite_passed, write
from backend.ai.provider import ModelSession, SecurityLiveApproval
from backend.core.comparator import compare_cases
from backend.core.evidence import Evidence
from backend.core.projects import copy_project, linked
from backend.core.recorder import invoke, load_cases
from backend.core.security import SCANNER_IMAGE, findings_for, scan
from backend.languages.base import inventory
from backend.llm.client import LLMClient, ModelUnavailable
from backend.sandbox.runner import DockerRunner, SandboxError
from backend.security.engine import SecurityFixEngine, project_hashes
from backend.security.providers import LLMFixGenerator


SOURCE = ROOT / 'samples/legacy_shop'
CASES = ROOT / 'tests/fixtures/legacy_shop/cases.json'
FILE = 'legacy_shop/config.py'
LIMITS = P82_LIMITS
IMAGES = ('python:2.7','python:3.12-slim',SCANNER_IMAGE)


def unchanged(before):
    inventory(SOURCE)
    if project_hashes(SOURCE) != before: raise ModelUnavailable('Original sources changed.', 'source_changed')


def config_tests(text):
    nodes = [n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name == 'ConfigTests']
    if len(nodes) != 1 or nodes[0].decorator_list: raise ValueError('Expected original ConfigTests class')
    node = nodes[0]
    body = ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
    return ("import os\nimport unittest\nfrom legacy_shop import config\n"
            "HERE = os.path.dirname(os.path.abspath(__file__))\nDATA = os.path.join(HERE, '..', 'sample_data')\n\n" + body + '\n')


def prepare(env_file, *, runner=None):
    settings = local_settings(env_file)
    _, files = inventory(SOURCE)
    if any(settings['MODEL_API_KEY'].encode() in p.read_bytes() for p in files):
        raise ModelUnavailable('Credential detected in project input.', 'credential_in_prompt')
    before = project_hashes(SOURCE)
    runner = runner or DockerRunner()
    if not runner.available(): raise SandboxError('Docker required; no host execution')
    images = {tag:runner.image_id(tag) for tag in IMAGES}
    workspace = ROOT / 'backend/.work' / ('p84-security-' + uuid4().hex)
    if any(linked(p) for p in (workspace,*workspace.parents)): raise ValueError('Link-free workspace required')
    original = workspace / 'original'
    for directory in ('legacy_shop','tests','sample_data'): (original / directory).mkdir(parents=True)
    for file in (FILE,'legacy_shop/__init__.py','tests/__init__.py','sample_data/shop.conf'):
        shutil.copyfile(SOURCE / file,original / file)
    test_file = SOURCE / 'tests/test_legacy_shop.py'
    (original / 'tests/test_legacy_shop.py').write_text(config_tests(test_file.read_text(encoding='utf-8')),encoding='utf-8')
    evidence = Evidence(); evidence.bind(workspace / 'preparation.log')
    evidence.append('scope','Original config.py only. Verbatim ConfigTests class with narrowed imports; full legacy_shop suite NOT run.')
    cases = [c for c in load_cases(CASES) if c['module']=='legacy_shop.config']
    if len(cases) != 9: raise ValueError('Review changed config case scope')
    source_syntax = invoke(runner,'python:2.7',original,'compile',evidence=evidence)
    target_syntax = invoke(runner,'python:3.12-slim',original,'compile',evidence=evidence)
    golden = invoke(runner,'python:2.7',original,'cases',cases,evidence)
    baseline = invoke(runner,'python:2.7',original,'tests',evidence=evidence)
    if source_syntax['errors'] or target_syntax['errors'] or not suite_passed(baseline) or baseline['tests_run'] != 1:
        raise ValueError('Config source syntax/test baseline failed')
    cross = invoke(runner,'python:3.12-slim',original,'cases',cases,evidence)
    cross_comparisons = compare_cases(golden['cases'],cross['cases'])
    probes = [{'id':'config.probe_arithmetic','module':'legacy_shop.config','steps':[{'call':'legacy_shop.config.parse_value','args':['1 + 2']}]},
              {'id':'config.probe_call','module':'legacy_shop.config','steps':[{'call':'legacy_shop.config.parse_value','args':["__import__('math').sqrt(9)"]}]}]
    probe_results = invoke(runner,'python:2.7',original,'cases',probes,evidence)
    scanned = scan(runner,original,evidence)
    _, findings = findings_for(scanned)
    chosen = [f for f in findings if f['scanner_test']=='B307' and f['file']==FILE and f['scope']=='parse_value']
    if scanned['errors'] or len(chosen) != 1: raise ValueError('Need a complete scan with one selected eval finding')
    for name,data in {'cases.json':{'cases':cases},'golden.json':golden,'source-tests.json':baseline,
                      'source-syntax.json':source_syntax,'additional-syntax.json':target_syntax,
                      'cross-runtime.json':{'recording':cross,'comparisons':cross_comparisons},
                      'contract-probes.json':{'inputs':probes,'recording':probe_results},'bandit-before.json':scanned}.items():
        write(workspace / name,data)
    unchanged(before)
    manifest = {'profile':'p8.4-eval','file':FILE,'finding':chosen[0],'model':settings['MODEL_NAME'],
        'source_sha256':sha256((original / FILE).read_text(encoding='utf-8').encode()).hexdigest(),
        'original_hashes':before,'scoped_hashes':project_hashes(original),'images':images,'limits':public_limits(LIMITS),
        'test_projection':{'class':'ConfigTests','original_sha256':digest(test_file),'full_project_suite':False}}
    write(workspace / 'prepared.json',manifest)
    report = {'phase':'preparation','operation':'security_fix','language':'python','status':'awaiting_paid_approval',
        'mode':'offline_baseline_preparation','model_calls':0,'ai_security_fix':False,'estimated_cost_usd':0,
        'finding':chosen[0],'finding_status':'open','verification_runtime':'2.7','source_python':golden['python'],
        'additional_syntax_python':target_syntax['python'],'source_tests':baseline,'golden_cases':len(cases),
        'cross_runtime_matches':sum(c['matches'] for c in cross_comparisons),'cross_runtime_total':len(cases),
        'cross_runtime_behavior_verified':all(c['matches'] for c in cross_comparisons),'migration_performed':False,
        'original_hashes':before,'originals_unchanged':True,'images':images,'isolation':'docker',
        'limits':public_limits(LIMITS),'max_reserved_cost_usd':'0.049152',
        'limitations':['Bandit finding is a potential risk; external input trust/exploitability is not established.',
            'Protected eval semantics require manual review even if finite tests pass and the warning disappears.',
            'Literal-only parsing changes existing arithmetic and accepted call/name semantics; resource limits also need review.',
            'Nine original cases and one unchanged ConfigTests test are finite coverage, not the full project suite.']}
    evidence.append('baseline_ready','Source Python 2.7 baseline and Bandit recorded; no proposal or paid request. B307 is protected.')
    artifacts.export(workspace,report,evidence,stem='baseline-report')
    artifacts.verify(workspace,unchanged,stem='baseline-report')
    return report,workspace


def validate_prepared(workspace, runner):
    workspace = Path(workspace).absolute()
    if workspace.parent != ROOT / 'backend/.work' or not workspace.name.startswith('p84-security-'):
        raise ValueError('Expected retained security preparation workspace')
    artifacts.verify(workspace,unchanged,stem='baseline-report')
    m = json.loads((workspace / 'prepared.json').read_text(encoding='utf-8'))
    if m['profile'] != 'p8.4-eval' or m['file'] != FILE or m['limits'] != public_limits(LIMITS) or m['model'] != 'muse-spark-1.3':
        raise ValueError('Prepared scope or financial limits changed')
    if project_hashes(workspace / 'original') != m['scoped_hashes']: raise ValueError('Scoped baseline changed')
    if load_cases(workspace / 'cases.json') != [c for c in load_cases(CASES) if c['module']=='legacy_shop.config']:
        raise ValueError('Golden inputs changed')
    selected = m['finding']
    if selected['scanner_test'] != 'B307' or selected['file'] != FILE or selected['scope'] != 'parse_value':
        raise ValueError('Finding binding changed')
    if sha256((workspace / 'original' / FILE).read_text(encoding='utf-8').encode()).hexdigest() != m['source_sha256']:
        raise ValueError('Model source binding changed')
    if not runner.available() or {tag:runner.image_id(tag) for tag in IMAGES} != m['images']:
        raise ValueError('Required local images changed or Docker unavailable')
    unchanged(m['original_hashes'])
    return m


def execute(workspace, env_file, *, acknowledged=False, runner=None, client=None):
    if acknowledged is not True: raise ModelUnavailable('Separate paid permission is required.', 'approval_required')
    settings = local_settings(env_file)
    runner = runner or DockerRunner(); workspace = Path(workspace).absolute()
    m = validate_prepared(workspace,runner)
    write(workspace / 'execution_started.json',{'manifest_sha256':digest(workspace / 'prepared.json'),
        'limits':public_limits(LIMITS),'finding_id':m['finding']['id'],'runtime':'2.7'})
    evidence = Evidence(); evidence.bind(workspace / 'evidence.log')
    evidence.append('prepared_baseline',digest(workspace / 'prepared.json'))
    original = workspace / 'original'; working = workspace / 'working'; copy_project(original,working)
    cases = load_cases(workspace / 'cases.json')
    golden = json.loads((workspace / 'golden.json').read_text(encoding='utf-8'))['cases']
    baseline = json.loads((workspace / 'source-tests.json').read_text(encoding='utf-8'))
    before_scan = json.loads((workspace / 'bandit-before.json').read_text(encoding='utf-8'))
    source = (working / FILE).read_text(encoding='utf-8')
    report = {'phase':'execution','operation':'security_fix','language':'python','mode':'live',
        'status':'failed','finding':m['finding'],'finding_status':'open','ai_security_fix':False,
        'original_hashes':m['original_hashes'],'attempts':[],'verification_runtime':'2.7',
        'additional_syntax_runtime':'3.12','golden_cases':len(cases),'source_tests':baseline,
        'limits':public_limits(LIMITS),'images':m['images'],'isolation':'docker'}
    client = client or LLMClient(env_file,mode='live',allow_live=True,limits=LIMITS)
    session = None
    try:
        if (client.mode != 'live' or client.limits != LIMITS or client.model != settings['MODEL_NAME']
                or client.base_url != settings['MODEL_BASE_URL'] or client._api_key != settings['MODEL_API_KEY']
                or client._price_in != Decimal('1.25') or client._price_out != Decimal('4.25')):
            raise ModelUnavailable('Unexpected security client/configuration.', 'live_not_authorized')
        session = ModelSession(client,'python',evidence=evidence,response_dir=workspace,
            live_approval=SecurityLiveApproval(FILE,m['source_sha256'],m['finding']['id']))
        generator = LLMFixGenerator(session=session,rules=('B307',),scopes=('parse_value',),max_proposals=2)
        engine = SecurityFixEngine(runner=runner,working=working,original=SOURCE,original_hashes=m['original_hashes'],
            artifacts=workspace / 'attempts',cases=cases,golden=golden,existing_tests=baseline,evidence=evidence,
            runtime_version='2.7',extra_syntax_versions=('3.12',),live_session=session)
        engine.artifacts.mkdir()
        previous = feedback = None
        for iteration in range(1,3):
            unchanged(m['original_hashes'])
            proposal = generator.generate(m['finding'],source,previous=previous,failures=feedback)
            attempt = engine._attempt(m['finding'],proposal,before_scan)
            report['attempts'].append(attempt)
            if attempt['applied']: raise ValueError('Protected eval must never be auto-accepted')
            report.update(finding_status=attempt['status'],status='needs_review' if attempt['status']=='needs_review' else 'failed')
            checks = attempt.get('checks',{})
            if all(checks.get(stage,{}).get('passed') is True for stage in ('syntax','golden','existing_tests')):
                break  # Policy review is not solved by another paid request.
            if iteration < 2:
                previous = proposal.proposed_code
                feedback = {'syntax':checks.get('syntax'),
                    'existing_tests':{'passed':checks.get('existing_tests',{}).get('passed')},
                    'golden':{'passed':checks.get('golden',{}).get('passed')},
                    'failing_cases':[{'input':next(c for c in cases if c['id']==f['id']),
                                     'expected':f.get('expected'),'actual':f.get('actual')}
                                    for f in checks.get('golden',{}).get('comparisons',[]) if not f['matches']],
                    'repair_requested':True,'manual_review_required':True}
    except (ModelUnavailable,SandboxError,ValueError,OSError) as exc:
        report['error'] = {'code':getattr(exc,'code','security_verification_failed')}
    finally:
        client.close()
    if project_hashes(working) != m['scoped_hashes']:
        working.rename(workspace / 'rejected_final'); copy_project(original,working)
    report.update(model=client.model,model_calls=len(client.attempts),usage=[asdict(c) for c in client.calls],
        model_attempts=[asdict(a) for a in client.attempts],budget=client.budget_snapshot(),
        ai_proposal_generated=bool(session and session.responses),originals_unchanged=project_hashes(SOURCE)==m['original_hashes'],
        working_copy_unchanged=project_hashes(working)==m['scoped_hashes'],rollback=bool(report['attempts']))
    if not report['originals_unchanged'] or not evidence.verify():
        report.update(status='failed',finding_status='fix_reverted',error={'code':'integrity_failed'})
    if session and session.private.clean(report) != report: raise ModelUnavailable('Private report withheld.', 'model_sensitive_response')
    artifacts.export(workspace,report,evidence)
    artifacts.verify(workspace,unchanged)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',type=Path,default=ROOT / 'backend/.tmp/meta-smoke.env')
    p.add_argument('--prepare',action='store_true'); p.add_argument('--execute',action='store_true')
    p.add_argument('--workspace',type=Path); p.add_argument('--acknowledge-paid-api',action='store_true')
    args = p.parse_args(argv)
    try:
        if args.prepare and not any((args.execute,args.workspace,args.acknowledge_paid_api)):
            report,workspace = prepare(args.env_file)
            print(json.dumps({k:report[k] for k in ('status','finding','source_python','golden_cases','model_calls','max_reserved_cost_usd')}))
            print('Retained workspace: '+str(workspace)); return 0
        if args.execute and args.acknowledge_paid_api and args.workspace and not args.prepare:
            report = execute(args.workspace,args.env_file,acknowledged=True)
            print(json.dumps({k:report.get(k) for k in ('status','finding_status','ai_security_fix','model_calls','budget','error')}))
            return 0 if report['status']=='needs_review' else 2
        raise ModelUnavailable('Choose free preparation or separately approved explicit execution.', 'approval_required')
    except (ModelUnavailable,SandboxError,ValueError,OSError) as exc:
        print(json.dumps({'status':'blocked','code':getattr(exc,'code','security_preparation_failed'),'notice':'Private details withheld; no fallback.'})); return 2


if __name__ == '__main__': raise SystemExit(main())
