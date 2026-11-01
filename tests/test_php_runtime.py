"""Protocol failures are injected; these unit tests are not Docker evidence."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.core.evidence import Evidence
from backend.languages.base import AdapterError
from backend.php.runtime import PHPExecutor, local_images
from backend.sandbox.runner import Result


IMAGE = "sha256:" + "b"*64


class RunnerDouble:
    def __init__(self, payload=None, **changes): self.payload=payload; self.changes=changes; self.calls=[]
    def run(self,image,project,command,payload):
        self.calls.append((image,project,command,payload))
        assert command[:2] == ["php","-n"] and command[-1] == "/tools/php_harness.php"
        assert image == IMAGE and payload["action"] in {"version","lint","tests","cases","phpunit"}
        values={"image":image,"exit_code":0,"stdout":json.dumps(self.payload),"stderr":"","seconds":0.1, **self.changes}
        return Result(**values)


@pytest.mark.parametrize("changes,payload,code", [
    ({"exit_code":2}, {}, "php_harness_unavailable"), ({"timed_out":True}, {}, "php_harness_unavailable"),
    ({"output_exceeded":True}, {}, "php_harness_unavailable"), ({"stdout":"<bad>"}, {}, "php_protocol_invalid"),
    ({}, {"protocol":"proofport-php-1","php":"8.3.35","action":"version"}, "php_runtime_mismatch"),
    ({}, {"protocol":"proofport-php-1","php":"8.3.36","action":"tests"}, "php_runtime_mismatch")])
def test_runtime_failures_never_become_success(tmp_path, changes, payload, code):
    e=PHPExecutor(runner=RunnerDouble(payload,**changes),images={"8.3":IMAGE},evidence=Evidence())
    with pytest.raises(AdapterError) as caught: e.invoke(tmp_path,"8.3","version")
    assert caught.value.code==code


def test_unpinned_images_unknown_commands_and_versions_are_rejected(tmp_path):
    with pytest.raises(ValueError): PHPExecutor(runner=None,images={"8.3":"php:latest"},evidence=Evidence())
    e=PHPExecutor(runner=RunnerDouble(),images={"8.3":IMAGE},evidence=Evidence())
    for version,action in [("8.4","version"),("8.3","exec")]:
        with pytest.raises(AdapterError): e.invoke(tmp_path,version,action)
    assert not e.runner.calls


def test_no_docker_does_not_fallback_to_host():
    with pytest.raises(AdapterError) as caught: local_images(SimpleNamespace(available=lambda:False))
    assert caught.value.code == "docker_unavailable"


def test_nonempty_test_results_and_ids_required(tmp_path):
    (tmp_path/"tests").mkdir(); (tmp_path/"tests/proofport.php").write_text("<?php return [];")
    for outcomes in [[],[{"id":"same","status":"passed"}]*2,[{"id":"a","status":"skipped"}]]:
        r=RunnerDouble({"protocol":"proofport-php-1","php":"8.3.36","action":"tests","tests_run":len(outcomes),"outcomes":outcomes})
        with pytest.raises(AdapterError): PHPExecutor(runner=r,images={"8.3":IMAGE},evidence=Evidence()).tests(tmp_path,"8.3")


def test_phpunit_requires_local_dependencies_without_installing(tmp_path):
    (tmp_path/"phpunit.xml").write_text("<phpunit/>")
    runner=RunnerDouble(); e=PHPExecutor(runner=runner,images={"8.3":IMAGE},evidence=Evidence())
    with pytest.raises(AdapterError) as caught: e.tests(tmp_path,"8.3",test_runner="phpunit")
    assert caught.value.code=="phpunit_unavailable" and not runner.calls


@pytest.mark.parametrize("xml,exit_code,passed",[(b'<testsuites><testsuite><testcase classname="Unit" name="a"/></testsuite></testsuites>',0,True),
    (b'<testsuite><testcase name="a"><failure/></testcase></testsuite>',1,False)])
def test_phpunit_junit_parsing_is_not_a_real_phpunit_claim(tmp_path,xml,exit_code,passed):
    (tmp_path/"phpunit.xml").write_text("<phpunit/>")
    (tmp_path/"vendor/phpunit/phpunit").mkdir(parents=True)
    (tmp_path/"vendor/phpunit/phpunit/phpunit").write_text("<?php // unit double")
    (tmp_path/"vendor/autoload.php").write_text("<?php // unit double")
    runner=RunnerDouble({"protocol":"proofport-php-1","php":"8.3.36","action":"phpunit","exit_code":exit_code,"junit":base64.b64encode(xml).decode()})
    tests=PHPExecutor(runner=runner,images={"8.3":IMAGE},evidence=Evidence()).tests(tmp_path,"8.3",test_runner="phpunit")
    assert tests["passed"] is passed and tests["tests_run"]==1
