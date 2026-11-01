"""Explicit fake PHP execution/in-memory HTTP; no real model or host PHP."""

import base64
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4

import httpx2
import pytest

from backend.ai import artifacts, first_php_live as php
from backend.ai.provider import ModelSession, PHPModuleLiveApproval, StructuredTranslator
from backend.llm.client import LLMClient, ModelUnavailable
from backend.php.protocol import compare


KEY='unit-only-php-key'


def outcome(case):
    result={'id':case['id'],'status':case['expected_status'],'stdout':'','warnings':[],'deprecations':[]}
    if result['status']=='return': result['value']={'type':'int','value':'1'}
    else: result['error']={'class':'RuntimeException','message':{'type':'bytes','base64':base64.b64encode(b'unit').decode()},'code':{'type':'int','value':'0'}}
    return result


@pytest.fixture
def ready(tmp_path,monkeypatch):
    source=tmp_path/'php_shop'; shutil.copytree(php.SOURCE,source)
    monkeypatch.setattr(php,'ROOT',tmp_path); monkeypatch.setattr(php,'SOURCE',source)
    settings={'MODEL_API_KEY':KEY,'MODEL_NAME':'muse-spark-1.3','MODEL_BASE_URL':'https://api.meta.ai/v1'}
    monkeypatch.setattr(php,'local_settings',lambda env:settings)
    images={'7.4':'sha256:'+'1'*64,'8.3':'sha256:'+'2'*64}
    monkeypatch.setattr(php,'local_images',lambda runner:dict(images))
    class Executor:
        def __init__(self,**kw): pass
        def lint(self,project,version): return {'ran':True,'passed':version=='7.4','php':'7.4.33' if version=='7.4' else '8.3.36','files':[{'file':php.FILE,'passed':version=='7.4'}]}
        def tests(self,*a): return {'tests_run':9,'passed':True,'php':'7.4.33','outcomes':[{'id':'unit-'+str(i),'status':'passed'} for i in range(9)]}
        def cases(self,project,version,profile): return [outcome(c) for c in profile['cases']]
        def invoke(self,*a): return {'protocol':'proofport-php-1','action':'version','php':'8.3.36'}
    monkeypatch.setattr(php,'PHPExecutor',Executor)
    monkeypatch.setattr('backend.sandbox.runner.DockerRunner.run',lambda *a,**k:pytest.fail('No unit/host project execution'))
    env=tmp_path/'unit.env'
    env.write_text('MODEL_API_KEY='+KEY+'\nMODEL_NAME=muse-spark-1.3\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    report,workspace=php.prepare(env,runner=object())
    return env,workspace,report


def client(env,seen,*,failure=None):
    def respond(request):
        seen.append(json.loads(request.content))
        if failure=='timeout': raise httpx2.ReadTimeout(KEY,request=request)
        context=json.loads(seen[-1]['messages'][1]['content'])
        patch={k:context[k] for k in ('task','language','file','source_sha256','finding_id')}
        patch.update(explanation='Unit response only; original PHP is deliberately NOT migrated',proposed_code=context['source'],behavior_impact='preserves',confidence=0.5,review_areas=[])
        content=json.dumps(patch) if failure!='bad_json' else '{"incomplete":'
        return httpx2.Response(200,json={'id':'unit','object':'chat.completion','created':1,'model':'muse-spark-1.3',
            'choices':[{'index':0,'finish_reason':'length' if failure=='truncated' else 'stop','message':{'role':'assistant','content':content}}],
            'usage':{'prompt_tokens':100,'completion_tokens':80,'total_tokens':180}})
    return LLMClient(env,mode='live',allow_live=True,limits=php.LIMITS,
        http_client=httpx2.Client(transport=httpx2.MockTransport(respond),trust_env=False))


def verifier(*,passes=True,syntax=True):
    def verify(executor,project,version,*,profile,golden,baseline_tests):
        observed=json.loads(json.dumps(golden))
        if not passes: observed[0]['value']={'type':'int','value':'2'}
        folder=project.parent/('v'+uuid4().hex[:8]); folder.mkdir()
        (folder/'observed-cases.json').write_text(json.dumps(observed))
        return {'passed':passes and syntax,'syntax':{'ran':True,'passed':syntax},
            'existing_tests':{'ran':syntax,**baseline_tests,'passed':True if syntax else None},
            'golden':{'ran':syntax,'passed':passes if syntax else None,'comparisons':compare(profile,golden,observed) if syntax else []},
            'recording_id':folder.name}
    return verify


def test_preparation_records_baseline_without_sdk(ready):
    env,workspace,report=ready
    assert report['model_calls']==0 and not report['ai_migration']
    assert report['golden_case_count']==22 and report['module_golden_cases']==5
    assert report['source_tests']['tests_run']==9 and report['source_tests']['passed']
    assert report['target_runtime']['php']=='8.3.36' and not report['target_original_syntax']['passed']
    assert report['syntax_passed'] is report['tests_passed'] is report['behavior_verified'] is None
    assert artifacts.verify(workspace,php.unchanged,stem='baseline-report')
    assert not (workspace/'execution_started.json').exists()


def test_acknowledgment_required_before_any_marker(ready):
    env,workspace,_=ready
    with pytest.raises(ModelUnavailable): php.execute(workspace,env)
    assert not (workspace/'execution_started.json').exists()


def test_mocked_success_saves_wire_diagnostics_and_reports(ready,monkeypatch):
    env,workspace,_=ready; seen=[]
    monkeypatch.setattr(php,'verify',verifier())
    report=php.execute(workspace,env,acknowledged=True,runner=object(),client=client(env,seen))
    assert report['status']=='done' and report['model_calls']==1
    assert report['model_attempts'][0]['finish_reason']=='stop' and report['model_attempts'][0]['json_object_valid']
    assert report['originals_unchanged'] and artifacts.verify(workspace,php.unchanged)
    assert KEY not in (workspace/'report.json').read_text()
    context=json.loads(seen[0]['messages'][1]['content'])
    assert context['language']=='php' and context['file']==php.FILE
    assert 'each()' in seen[0]['messages'][0]['content'] and 'curly-brace' in seen[0]['messages'][0]['content']


@pytest.mark.parametrize('syntax',[True,False])
def test_repair_is_bounded_to_two_calls_and_rolls_back(ready,monkeypatch,syntax):
    env,workspace,_=ready; seen=[]
    monkeypatch.setattr(php,'verify',verifier(passes=False,syntax=syntax))
    report=php.execute(workspace,env,acknowledged=True,runner=object(),client=client(env,seen))
    assert report['status']=='failed' and report['model_calls']==len(seen)==2 and report['rollback']
    assert (workspace/'candidate'/php.FILE).read_bytes()==(workspace/'original'/php.FILE).read_bytes()
    context=json.loads(seen[1]['messages'][1]['content'])
    assert context['previous'] and context['failures']['repair_requested']
    if syntax: assert context['failures']['failing_cases'][0]['expected'] != context['failures']['failing_cases'][0]['actual']
    with pytest.raises(FileExistsError): php.execute(workspace,env,acknowledged=True,runner=object())


@pytest.mark.parametrize('failure',['timeout','bad_json','truncated'])
def test_bad_provider_response_never_retries_or_accepts(ready,failure):
    env,workspace,_=ready; seen=[]
    report=php.execute(workspace,env,acknowledged=True,runner=object(),client=client(env,seen,failure=failure))
    assert report['status']=='failed' and report['model_calls']==len(seen)==1 and report['rollback']
    assert not report['ai_migration'] and artifacts.verify(workspace,php.unchanged)
    assert KEY not in json.dumps(report)


@pytest.mark.parametrize('file',['golden.json','cases.json','original/src/legacy.php','baseline-report.html','prepared.json'])
def test_tampered_baseline_blocks_before_client(ready,file):
    env,workspace,_=ready
    with (workspace/file).open('a') as stream: stream.write('changed')
    with pytest.raises(ValueError): php.execute(workspace,env,acknowledged=True,runner=object())
    assert not (workspace/'execution_started.json').exists()


def test_php_approval_rejects_wrong_scope_security_and_larger_budget(ready):
    env,workspace,_=ready; seen=[]; c=client(env,seen)
    source=(workspace/'original'/php.FILE).read_text()
    approval=PHPModuleLiveApproval(php.FILE,sha256(source.encode()).hexdigest())
    with pytest.raises(ModelUnavailable): ModelSession(c,'php')
    session=ModelSession(c,'php',live_approval=approval)
    with pytest.raises(ModelUnavailable): session.request('security',php.FILE,source,finding={'id':'one'})
    with pytest.raises(ModelUnavailable): session.request('translate','src/math.php',source)
    c.limits=replace(php.LIMITS,max_calls=3)
    with pytest.raises(ModelUnavailable): ModelSession(c,'php',live_approval=approval)
    assert not seen and not c.attempts; c.close()


def test_exact_php_budget_is_below_cap():
    from decimal import Decimal
    limits=php.LIMITS
    assert (limits.max_calls,limits.max_input_tokens,limits.max_output_tokens,limits.max_total_tokens,limits.timeout_seconds)==(2,9216,3072,24576,30)
    assert limits.max_cost_usd==Decimal('0.05')
    assert 2*(9216*Decimal('1.25')+3072*Decimal('4.25'))/1000000==Decimal('0.049152')


@pytest.mark.parametrize('change',[{'max_input_tokens':9217},{'max_output_tokens':3073},{'max_total_tokens':24577},{'max_cost_usd':'0.051'}])
def test_php_approval_rejects_budget_increases(ready,change):
    env,workspace,_=ready; seen=[]; c=client(env,seen)
    c.limits=replace(php.LIMITS,**change)
    source=(workspace/'original'/php.FILE).read_text()
    with pytest.raises(ModelUnavailable):
        ModelSession(c,'php',live_approval=PHPModuleLiveApproval(php.FILE,sha256(source.encode()).hexdigest()))
    assert not seen; c.close()


def test_fix_can_pass_second_offline_verification(ready,monkeypatch):
    env,workspace,_=ready; seen=[]; count=[]
    def check(*a,**kw):
        count.append(1)
        return verifier(passes=len(count)==2)(*a,**kw)
    monkeypatch.setattr(php,'verify',check)
    report=php.execute(workspace,env,acknowledged=True,runner=object(),client=client(env,seen))
    assert report['status']=='done' and report['model_calls']==2 and report['ai_fix_loop_used']
    assert artifacts.verify(workspace,php.unchanged)


def test_changed_original_blocks_before_client(ready):
    env,workspace,_=ready
    with (php.SOURCE/php.FILE).open('a') as stream: stream.write('\n// unit copy only\n')
    with pytest.raises(ModelUnavailable): php.execute(workspace,env,acknowledged=True,runner=object())
    assert not (workspace/'execution_started.json').exists()


@pytest.mark.parametrize('file',['report.html','evidence.log','response_01.json'])
def test_export_detects_artifact_tampering(ready,monkeypatch,file):
    env,workspace,_=ready; monkeypatch.setattr(php,'verify',verifier())
    php.execute(workspace,env,acknowledged=True,runner=object(),client=client(env,[]))
    with (workspace/file).open('a') as stream: stream.write('changed')
    with pytest.raises(ValueError): artifacts.verify(workspace,php.unchanged)


def test_php_repair_replays_exact_context_without_claiming_fix(ready,tmp_path):
    env,workspace,_=ready; captured=[]
    source=(workspace/'original'/php.FILE).read_text()
    def response(system,user):
        captured.append((system,user)); ctx=json.loads(user)
        data={k:ctx[k] for k in ('task','language','file','source_sha256','finding_id')}
        data.update(explanation='Offline replay only; original code remains incompatible',proposed_code=source,behavior_impact='preserves',confidence=0.5,review_areas=[])
        return json.dumps(data)
    feedback={'syntax':{'passed':False},'golden':{'passed':None},'existing_tests':{'passed':None},'repair_requested':True}
    c=LLMClient(env,mode='mock',limits=php.LIMITS,mock_responder=response)
    translator=StructuredTranslator(ModelSession(c,'php',case_feedback=True))
    assert translator.translate(php.FILE,source,source,feedback)==source
    s,u=captured[0]
    recording=tmp_path/'replay.json'
    recording.write_text(json.dumps({'mode':'explicit_model_response_replay_not_live','responses':[{'prompt_hash':c.attempts[0].prompt_hash,'response':response(s,u)}]}))
    replay=LLMClient(env,mode='replay',limits=php.LIMITS,replay_file=recording)
    assert StructuredTranslator(ModelSession(replay,'php',case_feedback=True)).translate(php.FILE,source,source,feedback)==source
    assert replay.cost_usd==0; replay.close(); c.close()
