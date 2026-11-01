"""P8.4 protocol/decision tests use fake execution and in-memory HTTP only."""

from dataclasses import replace
from hashlib import sha256
import json
import shutil

import httpx2
import pytest

from backend.ai import artifacts, first_security_live as sec
from backend.ai.provider import ModelSession, SecurityLiveApproval
from backend.core.security import findings_for
from backend.llm.client import LLMClient, ModelUnavailable


KEY='unit-security-model-key'


def scan_data():
    return {'errors':[],'results':[{'filename':sec.FILE,'line_number':7,'test_id':'B307','scope':'parse_value',
        'issue_confidence':'HIGH','issue_severity':'MEDIUM','issue_text':'Potential eval risk',
        'issue_cwe':{'id':78},'col_offset':15}]}


@pytest.fixture
def ready(tmp_path,monkeypatch):
    source=tmp_path/'shop'; shutil.copytree(sec.SOURCE,source)
    monkeypatch.setattr(sec,'ROOT',tmp_path); monkeypatch.setattr(sec,'SOURCE',source)
    monkeypatch.setattr(sec,'local_settings',lambda env:{'MODEL_API_KEY':KEY,'MODEL_NAME':'muse-spark-1.3','MODEL_BASE_URL':'https://api.meta.ai/v1'})
    class Runner:
        def available(self): return True
        def image_id(self,tag): return 'sha256:'+sha256(tag.encode()).hexdigest()
    def invoke(runner,image,project,action,cases=None,evidence=None):
        if evidence: evidence.append('unit_fake_run',action)
        version=[2,7,18] if image=='python:2.7' else [3,12,16]
        if action=='compile': return {'python':version,'errors':[]}
        if action=='tests': return {'python':version,'tests_run':1,'outcomes':[{'id':'ConfigTests.test_load','status':'passed'}]}
        results=[]
        for c in cases:
            value={'t':'int','v':0}
            if c['id']=='config.parse_6' and version[0]==3: value={'t':'float','v':'0.5'}
            results.append({'id':c['id'],'module':c['module'],'steps':[{'value':value,'stdout':'','stderr':''}]})
        return {'python':version,'cases':results}
    monkeypatch.setattr(sec,'invoke',invoke)
    monkeypatch.setattr(sec,'scan',lambda *a:scan_data())
    monkeypatch.setattr('backend.security.engine.scan',lambda *a:scan_data())
    env=tmp_path/'unit.env'
    env.write_text('MODEL_API_KEY='+KEY+'\nMODEL_NAME=muse-spark-1.3\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    runner=Runner(); report,workspace=sec.prepare(env,runner=runner)
    return env,workspace,report,runner


def model(env,seen,failure=None):
    def response(request):
        payload=json.loads(request.content); seen.append(payload)
        if failure=='timeout': raise httpx2.ReadTimeout(KEY,request=request)
        context=json.loads(payload['messages'][1]['content'])
        patch={k:context[k] for k in ('task','language','file','source_sha256','finding_id')}
        # Deliberately unchanged eval; not a prepared working security fix.
        patch.update(proposed_code=context['source'],explanation='Unit-only proposal; no mitigation claimed',behavior_impact='preserves',confidence=0.5,review_areas=[])
        text='{broken' if failure=='json' else json.dumps(patch)
        return httpx2.Response(200,json={'id':'unit','object':'chat.completion','created':1,'model':'muse-spark-1.3',
            'choices':[{'index':0,'finish_reason':'length' if failure=='length' else 'stop','message':{'role':'assistant','content':text}}],
            'usage':{'prompt_tokens':100,'completion_tokens':80,'total_tokens':180}})
    return LLMClient(env,mode='live',allow_live=True,limits=sec.LIMITS,
        http_client=httpx2.Client(transport=httpx2.MockTransport(response),trust_env=False))


def checks(passed=True):
    return {'syntax':{'ran':True,'passed':True},'golden':{'ran':True,'passed':passed,'comparisons':[]},
        'existing_tests':{'ran':True,'passed':True,'tests_run':1,'outcomes':[{'id':'ConfigTests.test_load','status':'passed'}]}}


def test_preparation_is_honest_about_eval_and_runtime(ready):
    env,workspace,r,runner=ready
    assert r['model_calls']==0 and not r['ai_security_fix']
    assert r['golden_cases']==9 and r['source_tests']['tests_run']==1
    assert r['verification_runtime']=='2.7' and not r['cross_runtime_behavior_verified']
    assert r['finding']['scanner_test']=='B307' and r['finding']['cwe']['id']==78
    assert sec.validate_prepared(workspace,runner)['limits']==sec.public_limits(sec.LIMITS)
    assert artifacts.verify(workspace,sec.unchanged,stem='baseline-report')


def test_no_paid_acknowledgment_blocks_before_marker(ready):
    env,workspace,_,runner=ready
    with pytest.raises(ModelUnavailable): sec.execute(workspace,env,runner=runner)
    assert not (workspace/'execution_started.json').exists()


def test_protected_finding_cannot_be_declared_fixed_with_passing_checks(ready,monkeypatch):
    env,workspace,_,runner=ready; seen=[]
    monkeypatch.setattr(sec.SecurityFixEngine,'_verify',lambda *a:checks())
    report=sec.execute(workspace,env,acknowledged=True,runner=runner,client=model(env,seen))
    assert report['status']==report['finding_status']=='needs_review' and not report['ai_security_fix']
    assert report['model_calls']==1 and report['working_copy_unchanged']
    assert report['attempts'][0]['rolled_back'] and not report['attempts'][0]['applied']
    context=json.loads(seen[0]['messages'][1]['content'])
    assert context['task']=='security' and context['source_version']==context['target_version']=='2.7'
    assert context['finding']['id']==report['finding']['id'] and 'literal_eval alone' in seen[0]['messages'][0]['content']
    assert artifacts.verify(workspace,sec.unchanged)
    assert KEY not in json.dumps(report)


def test_failed_checks_allow_only_two_attempts_and_restore_copy(ready,monkeypatch):
    env,workspace,_,runner=ready; seen=[]
    monkeypatch.setattr(sec.SecurityFixEngine,'_verify',lambda *a:checks(False))
    report=sec.execute(workspace,env,acknowledged=True,runner=runner,client=model(env,seen))
    assert report['model_calls']==len(seen)==2 and report['status']=='needs_review'
    assert report['working_copy_unchanged'] and all(not a['applied'] for a in report['attempts'])
    assert json.loads(seen[1]['messages'][1]['content'])['failures']['repair_requested']
    with pytest.raises(FileExistsError): sec.execute(workspace,env,acknowledged=True,runner=runner)


@pytest.mark.parametrize('failure',['timeout','json','length'])
def test_provider_errors_never_retry(ready,failure):
    env,workspace,_,runner=ready; seen=[]
    report=sec.execute(workspace,env,acknowledged=True,runner=runner,client=model(env,seen,failure))
    assert report['status']=='failed' and report['model_calls']==len(seen)==1
    assert not report['ai_security_fix'] and report['working_copy_unchanged']
    assert KEY not in json.dumps(report) and artifacts.verify(workspace,sec.unchanged)


@pytest.mark.parametrize('file',['golden.json','prepared.json','original/legacy_shop/config.py','baseline-report.html'])
def test_tampering_blocks_before_client(ready,file):
    env,workspace,_,runner=ready
    with (workspace/file).open('a') as stream: stream.write('changed')
    with pytest.raises(ValueError): sec.execute(workspace,env,acknowledged=True,runner=runner)
    assert not (workspace/'execution_started.json').exists()


def test_security_scope_cannot_migrate_or_select_another_finding(ready):
    env,workspace,report,runner=ready; seen=[];client=model(env,seen)
    source=(workspace/'original'/sec.FILE).read_text()
    approval=SecurityLiveApproval(sec.FILE,sha256(source.encode()).hexdigest(),report['finding']['id'])
    session=ModelSession(client,'python',live_approval=approval)
    with pytest.raises(ModelUnavailable): session.request('translate',sec.FILE,source)
    with pytest.raises(ModelUnavailable): session.request('security',sec.FILE,source,finding={'id':'wrong'})
    client.limits=replace(sec.LIMITS,max_calls=3)
    with pytest.raises(ModelUnavailable): ModelSession(client,'python',live_approval=approval)
    assert not seen;client.close()
