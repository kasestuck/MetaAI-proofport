"""Judge policy/unit tests use explicit doubles, never host project execution."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from backend import judge_suite as judge


class MissingDocker:
    _images={}
    def available(self): return False
    def image_id(self,*a): raise AssertionError('Unavailable daemon must not be queried')
    def run(self,*a): raise AssertionError('No host/container execution in unit test')


def setup(root,*,images=None,source=None):
    name=judge.IDS[0];folder=root/'judge_tests'/name;folder.mkdir(parents=True)
    project=folder/'project';project.mkdir();(project/'demo.py').write_text('def add(a,b): return a+b\n')
    config={'id':name,'worker':'python_migration','source':source or 'judge_tests/'+name+'/project','language':'python',
        'operation':'migration','source_version':'2.7','target_version':'3.12','required_images':images or ['python:2.7'],'expected_status':'PASS'}
    (folder/'scenario.json').write_text(json.dumps(config))
    return name


def test_missing_docker_is_required_skip_not_success_and_guard_is_restored(tmp_path):
    import backend.llm.client as llm
    sdk,complete=llm.OpenAI,llm.LLMClient.complete
    name=setup(tmp_path)
    summary,path=judge.run_suite((name,),runner=MissingDocker(),root=tmp_path)
    assert summary['counts']=={'PASS':0,'FAIL':0,'SKIP':1,'NEEDS_REVIEW':0}
    assert summary['mandatory_checks_passed'] is False and summary['model_calls']==0
    assert llm.OpenAI is sdk and llm.LLMClient.complete is complete
    assert judge.verify_summary(path)==summary


def test_saved_judge_receipt_detects_tampering(tmp_path):
    name=setup(tmp_path);_,path=judge.run_suite((name,),runner=MissingDocker(),root=tmp_path)
    (path.parent/'01/result.json').write_text('{}')
    with pytest.raises(ValueError,match='bytes differ'): judge.verify_summary(path)


@pytest.mark.parametrize('source',['../secret','backend/.tmp/private','/outside','tests/test_api.py','judge_tests/../private'])
def test_fixture_references_cannot_escape_owned_inputs(tmp_path,source):
    with pytest.raises(ValueError): judge.reference(source,tmp_path)


def test_browser_style_arbitrary_image_options_cannot_be_executed(tmp_path):
    name=setup(tmp_path,images=['attacker:latest'])
    summary,_=judge.run_suite((name,),runner=MissingDocker(),root=tmp_path)
    assert summary['scenarios'][0]['status']=='FAIL' and not summary['mandatory_checks_passed']


def test_absent_source_fails_without_invented_hashes(tmp_path):
    name=setup(tmp_path,source='judge_tests/absent')
    summary,_=judge.run_suite((name,),runner=MissingDocker(),root=tmp_path)
    assert summary['scenarios'][0]['status']=='FAIL'
    assert 'source_sha256' not in summary['scenarios'][0]


@pytest.mark.parametrize('status,checks,expected',[
    ('PASS',[{'required':True,'passed':True}],True),
    ('NEEDS_REVIEW',[{'required':True,'passed':True}],True),
    ('SKIP',[{'required':True,'passed':True}],False),
    ('PASS',[],False),('PASS',[{'required':False,'passed':True}],False),
    ('PASS',[{'required':True,'passed':1}],False),
])
def test_exit_policy_includes_required_checks_and_expected_review(status,checks,expected):
    assert judge.suite_passed([{'status':status,'checks':checks}]) is expected


def test_empty_or_inconsistent_test_suites_cannot_pass():
    assert not judge.passing_tests({'tests_run':1,'outcomes':[]})
    assert not judge.passing_tests({'tests_run':0,'outcomes':[]})
    assert not judge.passing_tests({'tests_run':2,'outcomes':[{'id':'a','status':'passed'}]*2})


def test_exactly_ten_declared_scenarios_list_without_execution():
    root=Path(__file__).resolve().parents[1]
    folders={p.name for p in (root/'judge_tests').iterdir() if p.is_dir() and p.name[:2].isdigit()}
    assert folders==set(judge.IDS)
    completed=subprocess.run([sys.executable,str(root/'judge_tests/runner.py'),'--list'],capture_output=True,check=True,text=True)
    assert len(completed.stdout.splitlines())==10
