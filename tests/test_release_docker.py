"""Two bounded rechecks of genuine saved candidates; no model requests."""
import json

import pytest

from backend import release
from backend.core.comparator import compare_cases
from backend.core.recorder import invoke,load_cases
from backend.core.projects import copy_project
from backend.core.evidence import Evidence
from backend.php.runtime import PHPExecutor,local_images
from backend.php.protocol import load_cases as php_cases
from backend.php.verification import verify
from backend.sandbox.runner import DockerRunner

pytestmark=pytest.mark.docker


@pytest.fixture(autouse=True)
def no_meta(monkeypatch):
    def forbidden(*a,**kw): pytest.fail('Release rechecks may not call a model')
    monkeypatch.setattr('backend.llm.client.OpenAI',forbidden)
    monkeypatch.setattr('backend.llm.client.LLMClient.complete',forbidden)


@pytest.mark.parametrize('kind',['python','php'])
def test_saved_genuine_target_still_passes(kind,tmp_path):
    entry=release.SAVED[kind];folder=release.ROOT/'backend/.work'/entry[0]
    if not folder.exists(): pytest.skip('Historical local proof absent; no fixture substitute')
    release.verify_recording(kind,folder,release.ROOT/entry[1])
    runner=DockerRunner();assert runner.available()
    candidate=tmp_path/'candidate';copy_project(folder/'candidate',candidate)
    if kind=='python':
        cases=load_cases(folder/'cases.json');golden=json.loads((folder/'golden.json').read_text())['cases']
        assert invoke(runner,'python:3.12-slim',candidate,'compile')['errors']==[]
        actual=invoke(runner,'python:3.12-slim',candidate,'cases',cases)['cases']
        comparisons=compare_cases(golden,actual);tests=invoke(runner,'python:3.12-slim',candidate,'tests')
        assert len(comparisons)==31 and all(c['matches'] for c in comparisons)
        assert tests['tests_run']==3 and all(t['status']=='passed' for t in tests['outcomes'])
    else:
        executor=PHPExecutor(runner=runner,images=local_images(runner),evidence=Evidence())
        checks=verify(executor,candidate,'8.3',profile=php_cases(folder/'cases.json'),
            golden=json.loads((folder/'golden.json').read_text()),baseline_tests=json.loads((folder/'source-tests.json').read_text()))
        assert checks['passed'] and checks['golden']['matched']==checks['golden']['total']==22
        assert checks['existing_tests']['tests_run']==9
    assert not runner._active
    release.verify_recording(kind,folder,release.ROOT/entry[1])
