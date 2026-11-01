"""Regression checks for confirmed P9 defects. No external model/network calls."""
import json
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.ai.provider import ModelSession,SecurityLiveApproval
from backend.ai.first_security_live import LIMITS
from backend.core.evidence import Evidence
from backend.llm.client import LLMClient,ModelUnavailable
from backend.llm.context import measure
from backend.php.security import scan_php


def test_local_api_rejects_dns_rebinding_and_foreign_origins(project,monkeypatch):
    monkeypatch.setattr('backend.api.main.docker_available',lambda:False)
    with TestClient(create_app(project)) as c:
        assert c.get('/api/health',headers={'Host':'attacker.example'}).status_code==400
        assert c.post('/api/runs',json={'source_path':'samples/legacy_shop'},headers={'Origin':'https://attacker.example'}).status_code==403
        assert c.get('/api/v1/projects',headers={'Origin':'null'}).status_code==403
        assert c.get('/api/health',headers={'Origin':'http://testserver'}).status_code==200
        assert c.get('/api/health').headers['x-content-type-options']=='nosniff'


@pytest.mark.parametrize('code',["echo $unsafe . htmlspecialchars($safe);","echo htmlspecialchars($safe), $unsafe;","print $unsafe . htmlentities($safe);"])
def test_php_sanitizer_elsewhere_does_not_hide_xss(tmp_path,code):
    (tmp_path/'a.php').write_text('<?php '+code)
    assert any(f['scanner_test']=='PHP-XSS' for f in scan_php(tmp_path)['findings'])


def test_input_rejection_stops_without_fake_attempt_or_spend(tmp_path):
    env=tmp_path/'u.env'; env.write_text('MODEL_API_KEY=unit-'+uuid4().hex+'\nMODEL_NAME=unit\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    c=LLMClient(env,mode='live',allow_live=True,limits=LIMITS)
    with pytest.raises(ModelUnavailable): c.complete('system','x'*10000)
    snapshot=c.budget_snapshot()
    assert snapshot['stopped'] and snapshot['preflight_rejection']=='input_budget_exceeded'
    assert snapshot['input_check']['method']=='utf8_bytes_plus_framing_not_provider_tokenizer'
    assert not c.attempts and c.cost_usd==0
    c.close()


def test_excessively_nested_replay_fails_with_safe_model_error(tmp_path):
    from backend.llm.replay import ReplayResponses
    replay=tmp_path/'replay.json';replay.write_text('['*2000+'0'+']'*2000)
    with pytest.raises(ModelUnavailable) as error: ReplayResponses(replay)
    assert error.value.code=='model_replay_unavailable'


def test_large_security_retry_retains_original_and_explicitly_labels_excerpts(tmp_path):
    env=tmp_path/'u.env';env.write_text('MODEL_API_KEY=unit-'+uuid4().hex+'\nMODEL_NAME=unit\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    source='def parse_value(raw):\n    return eval(raw)\n'
    from hashlib import sha256
    finding={'id':'B307-'+'a'*24,'file':'legacy_shop/config.py','scope':'parse_value','scanner_test':'B307'}
    seen=[]
    def response(request):
        seen.append(json.loads(request.content));ctx=json.loads(seen[-1]['messages'][1]['content'])
        patch={k:ctx[k] for k in ('task','language','file','source_sha256','finding_id')}
        patch.update(explanation='Protocol test, not a mitigation',proposed_code=source,behavior_impact='unknown',confidence=0.5,review_areas=[])
        return httpx2.Response(200,json={'id':'unit','object':'chat.completion','created':1,'model':'unit',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(patch)}}],
            'usage':{'prompt_tokens':100,'completion_tokens':80,'total_tokens':180}})
    c=LLMClient(env,mode='live',allow_live=True,limits=LIMITS,http_client=httpx2.Client(transport=httpx2.MockTransport(response)))
    e=Evidence();s=ModelSession(c,'python',evidence=e,compact_security=True,
        live_approval=SecurityLiveApproval(finding['file'],sha256(source.encode()).hexdigest(),finding['id']))
    previous='def f():\n    return ast.Bytes\n'+'# irrelevant long comment\n'*500
    s.request('security',finding['file'],source,previous=previous,failures={'syntax':{'passed':True},'repair_requested':True},finding=finding)
    ctx=json.loads(seen[0]['messages'][1]['content'])
    assert ctx['source']==source and ctx['previous'] is None
    assert ctx['previous_excerpt']['mode']=='diagnostic_excerpts_not_complete_candidate'
    assert ctx['previous_excerpt']['sha256']==sha256(previous.encode()).hexdigest()
    assert ctx['context_reduction'] and measure(seen[0]['messages'][0]['content'],seen[0]['messages'][1]['content'],9216)['within_allowance']
    assert e.verify() and len(c.calls)==1;c.close()


@pytest.mark.parametrize('final_error',[False,True])
def test_php_crlf_binding_and_final_scan_rollback(tmp_path,monkeypatch,final_error):
    from backend.php import fixes
    from backend.php.fixtures import OLD_COMMAND,NEW_COMMAND
    from backend.php.runtime import source_hashes
    from backend.core.projects import copy_project
    from backend.security.models import FixProposal
    source=Path(__file__).parent/'fixtures/php_shop'
    working=tmp_path/'w';copy_project(source,working)
    (working/'src/commands.php').write_bytes(OLD_COMMAND.replace('\n','\r\n').encode())
    artifact=tmp_path/'a';artifact.mkdir();versions=[]
    def verified(executor,project,version,**kw):
        versions.append(version)
        return {'passed':True,'syntax':{'ran':True,'passed':True},'golden':{'ran':True,'passed':True},'existing_tests':{'ran':True,'passed':True}}
    monkeypatch.setattr(fixes,'verify',verified)
    original_scan=fixes.scan_php;calls=[]
    def scanned(*a,**kw):
        calls.append(1);data=original_scan(*a,**kw)
        if final_error and len(calls)==4: data.update(errors=['unit-final-coverage-error'],coverage='partial')
        return data
    monkeypatch.setattr(fixes,'scan_php',scanned)
    class Generator:
        mode='mock'
        def generate(self,finding,code):
            if finding['scope']!='constant_banner': return None
            return FixProposal(finding_id=finding['id'],explanation='Unit-only proposal',proposed_code=NEW_COMMAND,
                               behavior_impact='preserves',confidence=1,mode='mock')
    accepted,report,_=fixes.verify_fixes(working=working,original=source,original_hashes=source_hashes(source),
        artifacts=artifact,profile=None,golden=[],baseline_tests={},executor=None,evidence=Evidence(),generator=Generator(),
        verification_versions=('7.4','8.3'))
    assert set(versions)=={'7.4','8.3'} and len(versions)==6
    assert report['verified'] is (not final_error)
    if final_error:
        assert accepted==working and not report['fixed']
        assert report['attempts'][0]['status']=='fix_reverted' and not report['attempts'][0]['applied']
    else: assert accepted!=working and len(report['fixed'])==1
    saved=json.loads((artifact/'attempt_01/attempt.json').read_text())
    assert saved['status']==report['attempts'][0]['status']


def test_direct_python_attempt_redacts_secret_diff_and_saved_record(tmp_path,monkeypatch):
    from backend.security.engine import SecurityFixEngine,project_hashes
    from backend.security.models import FixProposal
    secret='unit-private-'+uuid4().hex
    code='PASSWORD = '+repr(secret)+'\n'
    original=tmp_path/'o';working=tmp_path/'w';artifact=tmp_path/'a'
    for folder in (original,working,artifact): folder.mkdir()
    for folder in (original,working): (folder/'a.py').write_text(code)
    engine=SecurityFixEngine(runner=None,working=working,original=original,original_hashes=project_hashes(original),artifacts=artifact,
        cases=[{'id':'one','module':'a','steps':[{'call':'a.run'}]}],golden=[{'id':'one'}],
        existing_tests={'tests_run':1,'outcomes':[{'id':'unit','status':'passed'}]},evidence=Evidence())
    monkeypatch.setattr(engine,'_verify',lambda p:{s:{'passed':False} for s in ('syntax','golden','existing_tests')})
    monkeypatch.setattr('backend.security.engine.scan',lambda *a:{'results':[],'errors':[]})
    scan={'results':[{'filename':'a.py','line_number':1,'test_id':'B105','scope':'<module>',
        'issue_confidence':'HIGH','issue_severity':'LOW','issue_text':'Possible secret'}],'errors':[]}
    from backend.core.security import findings_for
    finding=findings_for(scan)[1][0]
    proposal=FixProposal(finding_id=finding['id'],explanation='Unit diagnostic only',proposed_code='PASSWORD = None\n',
        behavior_impact='changes',confidence=0.5,mode='mock')
    attempt=engine._attempt(finding,proposal,scan)
    assert secret not in json.dumps(attempt) and '[REDACTED]' in attempt['diff']
    assert secret not in (artifact/attempt['id']/'attempt.json').read_text()
    assert not attempt['applied'] and project_hashes(original)==project_hashes(working)


def test_security_request_describes_verified_runtime_not_migration_pair(monkeypatch):
    c=LLMClient(mode='mock',limits=LIMITS);seen=[]
    def complete(system,user,**kw):
        ctx=json.loads(user);seen.append(ctx)
        patch={k:ctx[k] for k in ('task','language','file','source_sha256','finding_id')}
        return json.dumps({**patch,'proposed_code':ctx['source'],'explanation':'Unit protocol check',
            'behavior_impact':'unknown','confidence':0.5,'review_areas':[]})
    monkeypatch.setattr(c,'complete',complete)
    finding={'id':'one','scanner_test':'B307','scope':'parse_value'}
    ModelSession(c,'python').request('security','legacy_shop/config.py','def parse_value(x): return eval(x)\n',finding=finding)
    ModelSession(c,'php').request('security','src/a.php','<?php echo $a;\n',finding={'id':'two','scanner_test':'PHP-XSS'})
    assert [(x['source_version'],x['target_version']) for x in seen]==[('3.12','3.12'),('8.3','8.3')]
    c.close()


def test_catalog_profile_availability_uses_preflight_path_policy(tmp_path,monkeypatch):
    from backend.core.control import ControlPlane
    from backend.core.control_models import ControlError
    class Projects:
        def snapshot(self): return []
    control=ControlPlane(tmp_path,None,Projects())
    relative=control.CASES['legacy_shop_golden'][1];profile=tmp_path/relative
    profile.parent.mkdir(parents=True);profile.write_text('{}')
    assert next(p for p in control.catalog()['cases_profiles'] if p['id']=='legacy_shop_golden')['available']
    monkeypatch.setattr('backend.core.control.linked',lambda path:path==profile)
    assert not next(p for p in control.catalog()['cases_profiles'] if p['id']=='legacy_shop_golden')['available']
    with pytest.raises(ControlError): control.profile(control.CASES,'legacy_shop_golden','legacy_shop','cases_profile_id')
