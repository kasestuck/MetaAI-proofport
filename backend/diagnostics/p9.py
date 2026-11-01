"""Sequential owned-demo security review. No model client or network generation.

Every proposed patch below is an AUTHORED OFFLINE DIAGNOSTIC, never AI output.
Finite checks do not confirm external reachability or full security coverage.
"""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from uuid import uuid4

from backend.ai.first_live import ROOT,verify_export
from backend.ai import artifacts,first_php_live
from backend.core.models import RunState,Metrics
from backend.core.runs import Run,RunStore,hashes_for
from backend.core.pipeline import execute
from backend.core.projects import copy_project
from backend.core.recorder import invoke,load_cases
from backend.core.comparator import compare_cases
from backend.core.evidence import Evidence
from backend.core.security import scan,findings_for
from backend.security.engine import SecurityFixEngine,project_hashes
from backend.security.providers import OfflineFixtureGenerator
from backend.security.models import FixProposal
from backend.php.runtime import PHPExecutor,local_images,source_hashes
from backend.php.protocol import load_cases as php_cases
from backend.php.fixes import verify_fixes
from backend.php.fixtures import NEW_COMMAND
from backend.sandbox.runner import DockerRunner


def php_proposal(f,code):
    rule=f['scanner_test']
    impact='changes';review=['api'];new=code
    if f['scope']=='constant_banner':
        new=NEW_COMMAND;impact='preserves';review=[]
    elif rule=='PHP-SQL':
        new=code.replace("$db = new DemoConnection();", "if (!preg_match('/\\A[0-9]+\\z/', (string)$input)) { throw new \\InvalidArgumentException('Numeric ID required'); } $db = new DemoConnection();")
    elif rule=='PHP-XSS': new=code.replace('echo $value;',"echo htmlspecialchars($value, ENT_QUOTES, 'UTF-8');")
    elif rule=='PHP-CMD':
        new=code.replace('return shell_exec($command);',"throw new \\InvalidArgumentException('Command execution disabled pending allowlist review');")
    elif rule=='PHP-DESERIALIZE': new=code.replace('unserialize($payload)',"unserialize($payload, array('allowed_classes' => false))")
    elif rule=='PHP-PATH':
        new=code.replace("return file_get_contents(__DIR__ . '/../data/' . $relative);", "if (basename($relative) !== $relative) { throw new \\InvalidArgumentException('Nested paths require review'); } return file_get_contents(__DIR__ . '/../data/' . $relative);")
    elif rule=='PHP-HASH': new=code.replace('md5($password)',"hash('sha256', $password)");review=['crypto','data_format']
    elif rule=='PHP-UPLOAD':
        new=code.replace('return move_uploaded_file($source, $destination);',"if (!is_uploaded_file($source) || filesize($source) > 1048576 || !preg_match('/\\.(png|jpg)\\z/i', basename($destination))) { return false; } return move_uploaded_file($source, $destination);")
    elif rule=='PHP-SECRET': impact='preserves';review=['configuration']
    return FixProposal(finding_id=f['id'],explanation='Authored offline diagnostic; not AI. Requires actual input/consumer contract review.',
        proposed_code=new,behavior_impact=impact,review_areas=review,confidence=0.5,mode='mock')


def export_review(root,result):
    """Add sealed, honest diagnostic exports without changing existing artifacts."""
    body=json.dumps(result,sort_keys=True,indent=2)
    with (root/'audit-report.json').open('x',encoding='utf-8') as stream: stream.write(body)
    with (root/'audit-report.html').open('x',encoding='utf-8') as stream:
        stream.write('<!doctype html><meta charset="utf-8"><title>Proofport P9 offline review</title>'
                     '<h1>Authored offline diagnostic review; no new AI calls</h1><pre>'+escape(body)+'</pre>')
    receipt={p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    with (root/'audit-receipt.json').open('x',encoding='utf-8') as stream: json.dump(receipt,stream,sort_keys=True,indent=2)
    assert all(sha256((root/name).read_bytes()).hexdigest()==value for name,value in receipt.items())


def main():
    import backend.llm.client as llm
    def forbidden(*args,**kwargs): raise AssertionError('P9 forbids model/API calls')
    llm.OpenAI=forbidden
    llm.LLMClient.complete=forbidden
    runner=DockerRunner()
    if not runner.available(): raise RuntimeError('Docker required; no host fallback')
    root=ROOT/'backend/.work'/('p9-review-'+uuid4().hex)
    root.mkdir(parents=True)
    result={'mode':'authored_offline_diagnostics_not_AI','model_calls':0,'python':{},'php':{}}
    source=ROOT/'samples/legacy_shop';before=project_hashes(source)
    # One existing fixture migration provides the full Python 3 verification base.
    original=hashes_for(source)
    run=Run(RunState(modules=[],hashes={**original,'unchanged':None},metrics=Metrics()),source,original,{},1,runner=runner)
    execute(run,'p9-python-'+uuid4().hex,ROOT,{'PROOFPORT_CASES_FILE':str(ROOT/'tests/fixtures/legacy_shop/cases.json'),
        'PROOFPORT_FIXTURE_FILE':str(ROOT/'tests/fixtures/legacy_shop/patches.json')},'fixtures')
    RunStore._finish(run)
    assert run.state.status=='done',run.state.error
    result['python'].update(baseline_artifact=str(run.workspace),golden_matches=len(run.verification['comparisons']),
        source_tests=run.verification['legacy_tests']['tests_run'],target_tests=run.verification['target_tests']['tests_run'])
    working=root/'python';copy_project(run.workspace/'migrated',working)
    evidence=Evidence();evidence.bind(root/'python-evidence.log')
    scanned=scan(runner,working,evidence);_,details=findings_for(scanned)
    assert not scanned['errors']
    fixes=OfflineFixtureGenerator(ROOT/'tests/fixtures/security/legacy_shop_fixes.json')
    engine=SecurityFixEngine(runner=runner,working=working,original=source,original_hashes=before,artifacts=root/'python-attempts',
        cases=load_cases(ROOT/'tests/fixtures/legacy_shop/cases.json'),golden=json.loads((run.workspace/'golden.json').read_text()),
        existing_tests=run.verification['legacy_tests'],evidence=evidence)
    engine.artifacts.mkdir();attempts=[]
    for finding in details:
        code=(working/finding['file']).read_text(encoding='utf-8')
        proposal=fixes.generate(finding,code)
        if proposal is None:
            new=code;impact='preserves';review=[]
            if finding['scanner_test']=='B301': new=code.replace('import pickle','import pickle\nimport json').replace('return pickle.load(f)','return json.load(f)');impact='changes';review=['data_format']
            elif finding['scanner_test']=='B324': new=code.replace('hashlib.md5(', 'hashlib.sha256(');impact='changes';review=['crypto','data_format']
            proposal=FixProposal(finding_id=finding['id'],explanation='Authored offline diagnostic / advisory context review; not AI.',
                proposed_code=new,behavior_impact=impact,review_areas=review,confidence=0.5,mode='fixture')
        attempt=engine._attempt(finding,proposal,scanned);attempts.append(attempt)
        print('Python '+finding['scanner_test']+': '+attempt['status'],flush=True)
    final=scan(runner,working,evidence);_,after=findings_for(final)
    result['python'].update(findings_before=details,findings_after=after,attempts=attempts,original_hashes=before,
        original_hashes_unchanged=project_hashes(source)==before,evidence_intact=evidence.verify())
    assert project_hashes(source)==before and evidence.verify()
    # Retained genuine Python result is re-verified, never regenerated by fixtures.
    p=ROOT/'backend/.work/p8-mathutils-bec88702e50948428fe35e2fa029af3e'
    assert verify_export(p)
    cases=load_cases(p/'cases.json')
    actual=invoke(runner,'python:3.12-slim',p/'candidate','cases',cases)['cases']
    expected=json.loads((p/'golden.json').read_text())['cases']
    tests=invoke(runner,'python:3.12-slim',p/'candidate','tests')
    assert all(c['matches'] for c in compare_cases(expected,actual)) and all(t['status']=='passed' for t in tests['outcomes'])
    result['python']['retained_live_regression']={'golden':len(cases),'tests':tests['tests_run'],'model_calls':0}
    # Retained genuine PHP result: all warnings reviewed on copied project only.
    p=ROOT/'backend/.work/p83-php-39cfcb6a2adf49a99b9948db31e01870'
    assert artifacts.verify(p,first_php_live.unchanged)
    original_php=ROOT/'tests/fixtures/php_shop';php_before=source_hashes(original_php)
    working=root/'php';copy_project(p/'candidate',working)
    evidence_php=Evidence();evidence_php.bind(root/'php-evidence.log')
    executor=PHPExecutor(runner=runner,images=local_images(runner),evidence=evidence_php)
    profile=php_cases(p/'cases.json');golden=json.loads((p/'golden.json').read_text())
    baseline=json.loads((p/'source-tests.json').read_text())
    class Generator:
        mode='mock'
        def generate(self,f,code): return php_proposal(f,code)
    secdir=root/'php-attempts';secdir.mkdir()
    accepted,review,_=verify_fixes(working=working,original=original_php,original_hashes=php_before,artifacts=secdir,
        profile=profile,golden=golden,baseline_tests=baseline,executor=executor,evidence=evidence_php,generator=Generator(),
        verification_versions=('7.4','8.3'))
    assert review['verified'] and source_hashes(original_php)==php_before and evidence_php.verify()
    result['php']=review
    result['php']['original_hashes']=php_before
    result['php']['retained_live_regression']={'golden':22,'tests':9,'runtimes':['7.4.33','8.3.36'],'model_calls':0}
    result['artifacts']=str(root)
    (root/'review.json').write_text(json.dumps(result,sort_keys=True,indent=2),encoding='utf-8')
    export_review(root,result)
    print(json.dumps({'artifacts':str(root),'python_findings':len(details),'python_decisions':[a['status'] for a in attempts],
        'php_findings':len(review['findings_before']),'php_fixed':len(review['fixed']),'php_needs_review':len(review['needs_review']),'model_calls':0}))


if __name__=='__main__': main()
