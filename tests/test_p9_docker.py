"""Small real runtime regression. No project/model code executes on the host."""
import json
from pathlib import Path

import pytest

from backend.core.recorder import invoke
from backend.sandbox.runner import DockerRunner

pytestmark=pytest.mark.docker


def test_py27_compile_does_not_prove_ast_runtime_compatibility(tmp_path):
    runner=DockerRunner()
    assert runner.available(), 'Explicit Docker regression requires running daemon'
    project=tmp_path/'project';project.mkdir()
    path=project/'evaluator.py'
    path.write_text('import ast\ndef evaluate(node):\n    return isinstance(node, (ast.Bytes, ast.NameConstant, ast.Constant))\n')
    assert invoke(runner,'python:2.7',project,'compile')['errors']==[]
    result=runner.run('python:2.7',project,['python','/tools/ast_api.py'])
    assert result.exit_code==0 and not result.timed_out
    report=json.loads(result.stdout)
    assert {e['attribute'] for e in report['errors']}=={'Bytes','NameConstant','Constant'}
    assert json.loads(runner.run('python:3.12-slim',project,['python','/tools/ast_api.py']).stdout)['errors']==[]
    path.write_text("import ast\nif hasattr(ast, 'Constant'):\n    def evaluate(node): return isinstance(node, ast.Constant)\nelse:\n    def evaluate(node): return isinstance(node, ast.Num)\n")
    assert json.loads(runner.run('python:2.7',project,['python','/tools/ast_api.py']).stdout)['errors']==[]
    assert not runner._active


def test_retained_p84_candidate_and_compact_repair_context(tmp_path,monkeypatch):
    from hashlib import sha256
    from backend.ai import artifacts,first_security_live as sec
    from backend.ai.provider import ModelSession,SecurityLiveApproval
    from backend.llm.client import LLMClient
    from backend.llm.context import measure
    root=Path(__file__).resolve().parents[1]
    saved=root/'backend/.work/p84-security-afc0c284439542fa999c2d5a8b58999d'
    if not saved.is_dir(): pytest.skip('Retained genuine P8.4 response absent; no fixture substitution')
    assert artifacts.verify(saved,sec.unchanged)
    report=json.loads((saved/'report.json').read_text())
    attempt=report['attempts'][0]
    previous=json.loads(json.loads((saved/'response_01.json').read_text())['response'])['proposed_code']
    runner=DockerRunner()
    checked=runner.run('python:2.7',saved/'attempts'/attempt['id']/'candidate',['python','/tools/ast_api.py'])
    data=json.loads(checked.stdout)
    assert checked.exit_code==0 and {e['attribute'] for e in data['errors']} >= {'Bytes','NameConstant'}
    source=(saved/'original'/sec.FILE).read_text()
    finding=report['finding'];cases=json.loads((saved/'cases.json').read_text())['cases']
    checks=attempt['checks']
    feedback={'repair_requested':True,'manual_review_required':True,'syntax':checks['syntax'],
        'golden':checks['golden'],'runtime_api':{'passed':False,'errors':data['errors']},
        'existing_tests':checks['existing_tests'],
        'failing_cases':[{'input':next(c for c in cases if c['id']==f['id']),'expected':f['expected'],'actual':f['actual']}
            for f in checks['golden']['comparisons'] if not f['matches']]}
    # Construct the actual approved protocol using a dummy credential. Replace
    # completion entirely: no SDK, transport, model, billable tokens or response.
    env=tmp_path/'unit.env'
    env.write_text('MODEL_API_KEY=unit-p9-dry-only\nMODEL_NAME=unit\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    client=LLMClient(env,mode='live',allow_live=True,limits=sec.LIMITS);seen=[]
    def no_api(system,user,**kw):
        context=json.loads(user);seen.append(measure(system,user,9216))
        assert context['source_version']==context['target_version']=='2.7'
        assert context['source']==source and context.get('context_reduction')
        assert 'NO Bytes, NameConstant or Constant' in system
        binding={k:context[k] for k in ('task','language','file','source_sha256','finding_id')}
        return json.dumps({**binding,'proposed_code':source,'explanation':'Dry protocol check; not a mitigation',
            'behavior_impact':'unknown','confidence':0.5,'review_areas':[]})
    monkeypatch.setattr(client,'complete',no_api)
    session=ModelSession(client,'python',live_approval=SecurityLiveApproval(sec.FILE,sha256(source.encode()).hexdigest(),finding['id']),compact_security=True)
    session.request('security',sec.FILE,source,previous=previous,failures=feedback,finding=finding)
    assert seen[0]['within_allowance'] and not client.attempts and client.cost_usd==0
    (tmp_path/'p84-context-check.json').write_text(json.dumps(seen[0],indent=2))
    client.close()
    assert artifacts.verify(saved,sec.unchanged)
