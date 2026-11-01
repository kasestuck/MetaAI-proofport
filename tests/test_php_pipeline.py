"""Static orchestration and transaction unit tests. Injected checks are not execution evidence."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.core.evidence import Evidence
from backend.core.projects import copy_project
from backend.php.fixes import verify_fixes
from backend.php.pipeline import PHPJob, execute
from backend.php.protocol import load_cases
from backend.php.runtime import source_hashes


ROOT=Path(__file__).resolve().parents[1]
DEMO=ROOT/"tests/fixtures/php_shop"
PROFILES=ROOT/"tests/fixtures/php_profiles"


@pytest.fixture(autouse=True)
def no_host_or_model(monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**k:pytest.fail("No SDK in PHP offline work"))
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run",lambda *a,**k:pytest.fail("Unit test may not execute projects"))


def test_audit_reports_potential_findings_without_execution(tmp_path):
    original=source_hashes(DEMO); evidence=Evidence()
    r,a=execute(PHPJob(DEMO,operation="audit",target_version=None),evidence=evidence,artifacts=tmp_path/"audit")
    assert r["status"]=="done" and r["syntax_passed"] is r["tests_passed"] is r["behavior_verified"] is None
    assert r["isolation"]=="reduced" and not r["project_executed"] and r["model_calls"]==0
    assert len(r["security_audit"]["findings"])==10 and source_hashes(DEMO)==original
    assert json.loads((a/"report.json").read_text())["chain_intact"] and "not AI" in (a/"report.html").read_text()
    assert evidence.verify(); (a/"evidence.jsonl").write_text("{}\n"); assert not evidence.verify()


@pytest.mark.parametrize("kwargs",[{"source_version":"8.4"},{"target_version":"8.4"},{"max_iterations":True},{"operation":"shell"}])
def test_invalid_jobs_cannot_execute(kwargs,tmp_path):
    with pytest.raises(ValueError): execute(PHPJob(DEMO,**kwargs),artifacts=tmp_path/"invalid")


def test_missing_docker_retains_honest_failed_report(tmp_path,monkeypatch):
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.available",lambda self:False)
    r,a=execute(PHPJob(DEMO,cases=PROFILES/"cases.json",fixture=PROFILES/"migration.json"),artifacts=tmp_path/"failed")
    assert r["status"]=="failed" and r["error"]["code"]=="docker_unavailable"
    assert r["behavior_verified"] is None and not r["migration_performed"] and r["chain_intact"]
    assert (a/"report.json").exists() and r["originals_unchanged"]


def fake_checks(passed=True,syntax=True,golden=True):
    return {"syntax":{"ran":True,"passed":syntax},"existing_tests":{"ran":syntax,"passed":passed if syntax else None},
        "golden":{"ran":syntax,"passed":golden if syntax else None},"passed":syntax and passed and golden}


def test_transaction_unit_decisions_rollback_and_rescan(tmp_path,monkeypatch):
    copy_project(DEMO,tmp_path/"working"); working=tmp_path/"working"; before=source_hashes(DEMO)
    # Checks are doubles here. Separate Docker integration checks the same three proposals for real.
    seen=[]
    def verified(executor,candidate,*args,**kwargs):
        seen.append(candidate)
        return [fake_checks(),fake_checks(passed=False,golden=False),fake_checks(syntax=False)][len(seen)-1]
    monkeypatch.setattr("backend.php.fixes.verify",verified)
    artifacts=tmp_path/"attempts"; artifacts.mkdir(); evidence=Evidence()
    accepted,details,_=verify_fixes(working=working,original=DEMO,original_hashes=before,artifacts=artifacts,
        profile=load_cases(PROFILES/"cases.json"),golden=[],baseline_tests={},executor=None,evidence=evidence,proposals_file=PROFILES/"security.json")
    assert [a["status"] for a in details["attempts"]]==["fixed","needs_review","fix_reverted"]
    assert len(details["fixed"])==1 and len(details["findings_after"])==9
    assert accepted==seen[0] and all(p.exists() for p in seen)
    assert source_hashes(DEMO)==before and source_hashes(working)==before and evidence.verify()
    assert "sha256" not in (accepted/"src/security.php").read_text()


def test_even_warning_removal_cannot_pass_failed_golden(tmp_path,monkeypatch):
    copy_project(DEMO,tmp_path/"working"); artifacts=tmp_path/"attempts"; artifacts.mkdir()
    proposals=json.loads((PROFILES/"security.json").read_text()); proposals["proposals"]=proposals["proposals"][:1]
    p=tmp_path/"one.json"; p.write_text(json.dumps(proposals))
    monkeypatch.setattr("backend.php.fixes.verify",lambda *a,**k:fake_checks(golden=False))
    accepted,details,_=verify_fixes(working=tmp_path/"working",original=DEMO,original_hashes=source_hashes(DEMO),artifacts=artifacts,
        profile=None,golden=[],baseline_tests={},executor=None,evidence=Evidence(),proposals_file=p)
    assert not details["fixed"] and details["attempts"][0]["rolled_back"]
    assert details["attempts"][0]["security_rescan"]["target_removed"]
    assert accepted==tmp_path/"working"


def test_partial_security_rescan_cannot_authorize_patch(tmp_path,monkeypatch):
    from backend.php.security import scan_php
    copy_project(DEMO,tmp_path/"working"); artifacts=tmp_path/"attempts"; artifacts.mkdir()
    proposals=json.loads((PROFILES/"security.json").read_text()); proposals["proposals"]=proposals["proposals"][:1]
    p=tmp_path/"one.json"; p.write_text(json.dumps(proposals))
    monkeypatch.setattr("backend.php.fixes.verify",lambda *a,**k:fake_checks())
    def partial(source,evidence=None):
        result=scan_php(source,evidence)
        if source.name=="project": result.update(coverage="partial",errors=[{"code":"unit_parse_error"}])
        return result
    monkeypatch.setattr("backend.php.fixes.scan_php",partial)
    accepted,details,_=verify_fixes(working=tmp_path/"working",original=DEMO,original_hashes=source_hashes(DEMO),artifacts=artifacts,
        profile=None,golden=[],baseline_tests={},executor=None,evidence=Evidence(),proposals_file=p)
    assert accepted==tmp_path/"working" and not details["fixed"]
    assert any("coverage" in reason for reason in details["attempts"][0]["reasons"])
