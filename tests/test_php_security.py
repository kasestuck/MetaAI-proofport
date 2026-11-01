"""Limited scanner assertions, not exploit verification."""

import json
from pathlib import Path

import pytest

from backend.core.evidence import Evidence
from backend.languages.base import AdapterError
from backend.php.fixtures import OLD_COMMAND, NEW_COMMAND, constant_command_policy, load_manifest, apply_candidate
from backend.php.runtime import source_hashes
from backend.php.security import RULES, scan_php


ROOT = Path(__file__).resolve().parents[1]


def test_demo_eight_risk_categories_are_potential_and_source_unchanged():
    source = ROOT / "tests/fixtures/php_shop"; before = source_hashes(source); evidence = Evidence()
    scanned = scan_php(source, evidence)
    assert len(scanned["findings"]) == 10
    assert {f["scanner_test"] for f in scanned["findings"]} == set(RULES)
    assert len({f["id"] for f in scanned["findings"]}) == 10
    assert not scanned["confirmed_findings"] and not scanned["project_executed"]
    assert all(f["status"] == "open" and f["verification_status"] == "potential_risk_not_confirmed" and f["cwe"]["id"] for f in scanned["findings"])
    assert source_hashes(source) == before and evidence.verify()
    assert "fake-demo-placeholder" not in json.dumps(scanned)


def test_comments_literal_text_and_escaped_echo_are_not_sinks(tmp_path):
    (tmp_path / "a.php").write_text("<?php /* system($_GET['x']); */ $text='unserialize($x)'; echo htmlspecialchars($text); // md5($password)\n")
    assert not scan_php(tmp_path)["findings"]


def test_secret_values_are_not_exported_and_ids_are_stable(tmp_path):
    p=tmp_path/"a.php"; p.write_text("<?php function f() { $api_key='fake-unit-private'; return $api_key; }")
    first=scan_php(tmp_path); assert first["findings"][0]["scanner_test"] == "PHP-SECRET"
    assert "fake-unit-private" not in json.dumps(first)
    p.write_text("\n\n"+p.read_text())
    assert scan_php(tmp_path)["findings"][0]["id"] == first["findings"][0]["id"]


def test_tests_excluded_and_syntax_unknown_in_static_audit(tmp_path):
    (tmp_path/"a.php").write_text("<?php function a() { return 1; }")
    (tmp_path/"tests").mkdir(); (tmp_path/"tests/test.php").write_text("<?php system($_GET['x']);")
    r=scan_php(tmp_path); assert r["findings"] == [] and r["coverage"] == "limited_lexical"
    assert "syntax_passed" not in r


def test_fixture_is_source_bound_and_does_not_modify_original(tmp_path):
    from backend.core.projects import copy_project
    source=ROOT/"tests/fixtures/php_shop"; before=source_hashes(source)
    manifest=load_manifest(ROOT/"tests/fixtures/php_profiles/migration.json",source)
    copy_project(source,tmp_path/"copy"); apply_candidate(manifest,tmp_path/"copy",0)
    assert source_hashes(source)==before and source_hashes(tmp_path/"copy")!=before
    with pytest.raises(ValueError): load_manifest(ROOT/"tests/fixtures/php_profiles/migration.json",tmp_path/"copy")
    with pytest.raises(ValueError): apply_candidate(manifest,tmp_path/"copy",1)


def test_warning_disappearance_or_model_confidence_cannot_authorize_a_patch():
    good={"policy":"constant_argv","behavior_impact":"preserves","review_areas":[]}
    assert constant_command_policy(OLD_COMMAND,NEW_COMMAND,good)
    assert not constant_command_policy(OLD_COMMAND,NEW_COMMAND+"\n",good)
    assert not constant_command_policy(OLD_COMMAND,NEW_COMMAND,{**good,"review_areas":["configuration"]})
    assert not constant_command_policy(OLD_COMMAND,NEW_COMMAND,{"confidence":1.0,"behavior_impact":"preserves"})


def test_composer_credentials_and_mixed_project_cannot_enter_executor(tmp_path):
    (tmp_path/"a.php").write_text("<?php echo 1;")
    (tmp_path/"auth.json").write_text('{"unit":"private"}')
    with pytest.raises(AdapterError): source_hashes(tmp_path)
