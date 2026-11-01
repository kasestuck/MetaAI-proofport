"""Decision/rollback unit checks with explicit fake verification, not Docker proof."""

from pathlib import Path

import pytest

from backend.core.evidence import Evidence
from backend.core.projects import copy_project
from backend.php.fixtures import NEW_COMMAND
from backend.php.fixes import verify_fixes
from backend.php.runtime import source_hashes
from backend.security.engine import SecurityFixEngine, project_hashes
from backend.security.models import FixProposal


ROOT=Path(__file__).resolve().parents[1]
OLD="import subprocess\ndef output():\n    return subprocess.check_output('/usr/bin/printf fixture', shell=True)\n"
NEW=OLD.replace("'/usr/bin/printf fixture', shell=True","['/usr/bin/printf', 'fixture'], shell=False")


def checks(passed=True):
    return {"syntax":{"ran":True,"passed":True},"golden":{"ran":True,"passed":passed},
            "existing_tests":{"ran":True,"passed":True},"passed":passed}


def test_python_behavior_failure_is_review_and_rollback_even_with_warning_removed(tmp_path,monkeypatch):
    original=tmp_path/"original"; working=tmp_path/"working"; original.mkdir(); working.mkdir()
    for root in (original,working): (root/"a.py").write_text(OLD)
    artifacts=tmp_path/"attempts"; artifacts.mkdir()
    engine=SecurityFixEngine(runner=None,working=working,original=original,original_hashes=project_hashes(original),artifacts=artifacts,
        cases=[{"id":"one","module":"a","steps":[{"call":"a.output"}]}],golden=[{"id":"one"}],existing_tests={"tests_run":1,"outcomes":[{"id":"unit","status":"passed"}]},evidence=Evidence())
    monkeypatch.setattr(engine,"_verify",lambda project:checks(False))
    monkeypatch.setattr("backend.security.engine.scan",lambda *a:{"results":[],"errors":[]})
    finding={"id":"one","file":"a.py","scanner_test":"B602","line":3,"scope":"output"}
    proposal=FixProposal(finding_id="one",explanation="Mock response",proposed_code=NEW,behavior_impact="preserves",confidence=1,mode="mock")
    attempt=engine._attempt(finding,proposal,{"results":[],"errors":[]})
    assert attempt["status"]=="needs_review" and attempt["rolled_back"] and not attempt["applied"]
    assert attempt["target_warning_removed"] and (working/"a.py").read_text()==OLD
    assert engine.evidence.verify() and (original/"a.py").read_text()==OLD


def test_php_behavior_failure_requires_review_and_preserves_previous_copy(tmp_path,monkeypatch):
    source=ROOT/"tests/fixtures/php_shop"; working=tmp_path/"working"; copy_project(source,working)
    before=source_hashes(source); artifacts=tmp_path/"attempts"; artifacts.mkdir(); calls=[]
    def verify(*args,**kwargs): calls.append(True); return checks(len(calls)==1)
    monkeypatch.setattr("backend.php.fixes.verify",verify)
    class Generator:
        mode="mock"
        def generate(self,finding,source):
            if finding["scope"]!="constant_banner": return None
            return FixProposal(finding_id=finding["id"],explanation="Mock response",proposed_code=NEW_COMMAND,
                behavior_impact="preserves",confidence=1,mode="mock")
    accepted,result,_=verify_fixes(working=working,original=source,original_hashes=before,artifacts=artifacts,
        profile=None,golden=[],baseline_tests={},executor=None,evidence=Evidence(),generator=Generator())
    assert accepted==working and len(result["needs_review"])==1 and not result["fixed"]
    assert result["attempts"][0]["rolled_back"] and result["attempts"][0]["security_rescan"]["target_removed"]
    assert source_hashes(working)==source_hashes(source)==before


def test_private_redaction_requires_review_for_ambiguous_short_secret():
    from backend.ai.provider import PrivateContext
    from backend.llm.client import ModelUnavailable
    with pytest.raises(ModelUnavailable) as error: PrivateContext().protect("PASSWORD='x'\n")
    assert error.value.code=="needs_review"
