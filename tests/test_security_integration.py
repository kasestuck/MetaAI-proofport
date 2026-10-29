from copy import deepcopy
import json
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.evidence import Evidence
from backend.core.recorder import invoke, load_cases
from backend.security.engine import SecurityFixEngine, project_hashes
from backend.security.providers import OfflineFixtureGenerator
from backend.sandbox.runner import DockerRunner


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "tests/fixtures/security_subject"
FIXTURES = ROOT / "tests/fixtures/security"


@pytest.fixture(autouse=True)
def forbid_model_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("P2 may not spend API credits")
    monkeypatch.setattr("backend.llm.client.OpenAI", forbidden)
    monkeypatch.setattr("backend.llm.client.LLMClient.complete", forbidden)


@pytest.fixture(scope="module")
def real_baseline():
    runner = DockerRunner()
    assert runner.available(), "Real Docker is required for enabled P2 tests"
    cases = load_cases(SUBJECT / "cases.json")
    golden = invoke(runner, "python:3.12-slim", SUBJECT, "cases", cases)["cases"]
    tests = invoke(runner, "python:3.12-slim", SUBJECT, "tests")
    assert tests["tests_run"] == 2 and all(t["status"] == "passed" for t in tests["outcomes"])
    return cases, golden, tests, project_hashes(SUBJECT)


def setup_engine(tmp_path, real_baseline, safe=False, original=None):
    cases, golden, tests, original_hashes = real_baseline
    working = tmp_path / "accepted"
    shutil.copytree(SUBJECT, working)
    if safe:
        path = working / "commands.py"
        path.write_text(path.read_text().replace("subprocess.check_output('/usr/bin/printf fixture', shell=True)", "subprocess.check_output(['/usr/bin/printf', 'fixture'], shell=False)"))
    evidence = Evidence()
    evidence.bind(tmp_path / "evidence.log")
    engine = SecurityFixEngine(runner=DockerRunner(), working=working, original=original or SUBJECT,
                               original_hashes=original_hashes, artifacts=tmp_path / "attempts",
                               cases=deepcopy(cases), golden=deepcopy(golden), existing_tests=deepcopy(tests), evidence=evidence)
    return engine, working, evidence


def test_successful_fixture_hardening_runs_all_checks(real_baseline, tmp_path):
    engine, working, evidence = setup_engine(tmp_path, real_baseline)
    before = project_hashes(working)
    result = engine.run(OfflineFixtureGenerator(FIXTURES / "constant_command_fix.json"))
    assert result["status"] == "verified", result
    assert len(result["fixed"]) == 1
    attempt = result["attempts"][0]
    assert attempt["status"] == "fixed" and attempt["applied"] and not attempt["rolled_back"]
    assert all(attempt["checks"][name]["ran"] and attempt["checks"][name]["passed"] for name in ("syntax", "golden", "existing_tests"))
    assert attempt["checks"]["golden"]["matched"] == attempt["checks"]["golden"]["total"] == 3
    assert attempt["checks"]["existing_tests"]["tests_run"] == 2
    assert attempt["rescan"]["ran"] and attempt["rescan"]["passed"]
    assert attempt["target_warning_removed"]
    assert project_hashes(working) != before
    assert result["original_unchanged"] and project_hashes(SUBJECT) == real_baseline[3]
    assert result["mode"] == "fixture" and result["ai_generated"] is False
    assert all(finding["scanner_test"] != "B602" for finding in result["findings_after"])
    assert any(finding["scanner_test"] == "B603" and finding["status"] == "false_positive" for finding in result["findings_after"])
    assert evidence.verify() and result["evidence_chain_intact"]
    assert any(event["type"] == "security_fix" for event in evidence.since(0))
    assert engine.artifacts.joinpath(attempt["id"], "attempt.json").is_file()


@pytest.mark.parametrize("kind,expected", [("syntax", "fix_reverted"), ("behavior", "fix_reverted"), ("api", "needs_review"), ("warning_evasion", "needs_review")])
def test_invalid_or_incompatible_fixes_are_not_committed(real_baseline, tmp_path, kind, expected):
    engine, working, evidence = setup_engine(tmp_path, real_baseline)
    base = OfflineFixtureGenerator(FIXTURES / "constant_command_fix.json")
    class ChangedFixture:
        def generate(self, finding, source):
            proposal = base.generate(finding, source)
            if proposal is None:
                return None
            code = proposal.proposed_code
            if kind == "syntax":
                code = "def invalid(\n"
            elif kind == "behavior":
                code = code.replace("'fixture'", "'WRONG'")
            elif kind == "api":
                code = code.replace("def constant_output():", "def constant_output(new_arg=None):")
            else:
                code = source.replace("shell=True", "**{'shell': True}")
            return proposal.model_copy(update={"proposed_code": code})
    before = project_hashes(working)
    result = engine.run(ChangedFixture())
    assert result["status"] == "verified", result
    attempt = result["attempts"][0]
    assert attempt["status"] == expected
    assert attempt["rolled_back"] and not attempt["applied"]
    assert not result["fixed"] and project_hashes(working) == before
    assert result["original_unchanged"] and evidence.verify()
    assert attempt["rescan"]["ran"]
    if kind == "syntax":
        assert not attempt["checks"]["syntax"]["passed"]
        assert not attempt["checks"]["golden"]["ran"]
        assert attempt["rescan"]["errors"]
    elif kind == "behavior":
        assert not attempt["checks"]["golden"]["passed"]
        assert not attempt["checks"]["existing_tests"]["passed"]
        assert attempt["target_warning_removed"]  # Disappearing warning is insufficient.
    else:
        assert attempt["checks"]["golden"]["passed"] and attempt["checks"]["existing_tests"]["passed"]
    assert any(event["type"] == "fix_reverted" for event in evidence.since(0))


def test_false_positive_needs_independent_context_not_confidence(real_baseline, tmp_path):
    engine, working, evidence = setup_engine(tmp_path, real_baseline, safe=True)
    before = project_hashes(working)
    result = engine.run(OfflineFixtureGenerator(FIXTURES / "constant_argv_triage.json"))
    assert result["status"] == "verified", result
    attempt = result["attempts"][0]
    assert attempt["status"] == "false_positive"
    assert not attempt["applied"] and not attempt["target_warning_removed"]
    assert attempt["checks"]["golden"]["passed"] and attempt["checks"]["existing_tests"]["passed"]
    assert project_hashes(working) == before and evidence.verify()


def test_unsupported_false_positive_claim_remains_open(real_baseline, tmp_path):
    engine, working, evidence = setup_engine(tmp_path, real_baseline)
    base = OfflineFixtureGenerator(FIXTURES / "constant_command_fix.json")
    class UnfoundedFixture:
        def generate(self, finding, source):
            result = base.generate(finding, source)
            return result.model_copy(update={"disposition": "false_positive", "proposed_code": None}) if result else None
    before = project_hashes(working)
    result = engine.run(UnfoundedFixture())
    assert result["attempts"][0]["status"] == "open"
    assert project_hashes(working) == before and evidence.verify()


@pytest.mark.parametrize("fault", ["log", "late_original_change"])
def test_integrity_failure_rolls_back_an_otherwise_accepted_patch(real_baseline, tmp_path, fault):
    original_clone = tmp_path / "original_clone"
    shutil.copytree(SUBJECT, original_clone)
    engine, working, evidence = setup_engine(tmp_path, real_baseline, original=original_clone)
    verify = engine._verify
    calls = 0
    def verified_then_tampered(project):
        nonlocal calls
        result = verify(project)  # Real Docker compilation, golden execution and tests.
        calls += 1
        if calls == 3 and fault == "log":  # Final accepted-project check, after an actual successful fix.
            evidence.path.write_text(evidence.path.read_text().replace('"sandbox_run"', '"tampered_run"', 1))
        return result
    engine._verify = verified_then_tampered
    original_ok = engine._original_ok
    hash_checks = 0
    def checked_then_changed():
        nonlocal hash_checks
        hash_checks += 1
        if hash_checks == 5 and fault == "late_original_change":
            # External edit of a disposable fixture clone, never legacy_shop.
            path = original_clone / "cases.json"
            path.write_text(path.read_text() + "\n")
        return original_ok()  # Real SHA-256 comparison, never a fabricated result.
    engine._original_ok = checked_then_changed
    before = project_hashes(working)
    result = engine.run(OfflineFixtureGenerator(FIXTURES / "constant_command_fix.json"))
    assert result["status"] == "failed"
    assert not result["fixed"]
    assert evidence.verify() is (fault != "log")
    assert result["original_unchanged"] is (fault == "log")
    assert result["attempts"][0]["status"] == "fix_reverted"
    assert result["attempts"][0]["rolled_back"] and not result["attempts"][0]["applied"]
    assert project_hashes(working) == before
    assert result["accepted_project_hashes"] == result["baseline_project_hashes"]


def test_acceptance_log_write_failure_rolls_back_committed_bytes(real_baseline, tmp_path):
    engine, working, evidence = setup_engine(tmp_path, real_baseline)
    append = evidence.append
    def fail_acceptance(event_type, detail, module=None):
        if event_type == "security_fix":
            raise OSError("Injected acceptance-log storage failure")
        return append(event_type, detail, module)
    evidence.append = fail_acceptance
    before = project_hashes(working)
    result = engine.run(OfflineFixtureGenerator(FIXTURES / "constant_command_fix.json"))
    assert result["status"] == "verified", result  # Restored baseline, not a successful fix.
    assert result["attempts"][0]["status"] == "fix_reverted"
    assert not result["attempts"][0]["applied"] and result["attempts"][0]["rolled_back"]
    assert not result["fixed"] and project_hashes(working) == before
    assert evidence.verify()


def test_legacy_shop_security_proposals_keep_behavior_and_configuration_for_review(monkeypatch):
    source = ROOT / "samples/legacy_shop"
    before = project_hashes(source)
    monkeypatch.setenv("PROOFPORT_PIPELINE", "fixtures")
    monkeypatch.setenv("PROOFPORT_CASES_FILE", str(ROOT / "tests/fixtures/legacy_shop/cases.json"))
    monkeypatch.setenv("PROOFPORT_FIXTURE_FILE", str(ROOT / "tests/fixtures/legacy_shop/patches.json"))
    monkeypatch.setenv("PROOFPORT_SECURITY_FIXTURES", str(FIXTURES / "legacy_shop_fixes.json"))
    with TestClient(create_app(ROOT, step_seconds=0.001)) as client:
        response = client.post("/api/runs", json={"source_path": "samples/legacy_shop", "max_iterations": 1})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = client.get(f"/api/runs/{run_id}").json()
            if client.app.state.runs.active is None:
                break
            time.sleep(0.05)
        assert state["status"] == "done", state
        assert state["metrics"]["tokens_in"] == state["metrics"]["tokens_out"] == state["metrics"]["cost_usd"] == 0
        assert state["metrics"]["tests_passed"] == state["metrics"]["tests_total"] == 100
        assert state["security"]["before"] == state["security"]["after"] == 8
        assert set(state) == {"status", "phase", "isolation", "modules", "security", "hashes", "metrics", "chain_intact"}
        data = client.get(f"/api/runs/{run_id}/report?format=json").json()
        security = data["verification"]["security_fix"]
        assert security["mode"] == "fixture" and security["status"] == "verified"
        assert len(security["attempts"]) == 4
        assert len(security["needs_review"]) == 5  # Four proposals plus the existing MD5 review item.
        assert not security["fixed"]
        assert all(attempt["status"] == "needs_review" and attempt["rolled_back"] and not attempt["applied"] for attempt in security["attempts"])
        assert all(attempt["checks"]["syntax"]["passed"] and attempt["rescan"]["ran"] for attempt in security["attempts"])
        tests = {finding["id"]: finding["scanner_test"] for finding in security["findings_before"]}
        attempts = {tests[attempt["finding_id"]]: attempt for attempt in security["attempts"]}
        assert attempts["B602"]["checks"]["golden"]["passed"]  # Passing samples do not authorize shell contract changes.
        assert not attempts["B307"]["checks"]["golden"]["passed"]
        assert not attempts["B608"]["checks"]["golden"]["passed"]
        assert not attempts["B105"]["checks"]["golden"]["passed"]
        assert "[REDACTED]" in attempts["B105"]["diff"]
        assert security["original_unchanged"] and security["evidence_chain_intact"] and state["chain_intact"]
        html = client.get(f"/api/runs/{run_id}/report?format=html").text
        assert "Security verification (fixture)" in html and "Findings before fixes" in html and "Code changes (redacted)" in html
        assert "CWE-89" in html and "needs_review" in html
        run = client.app.state.runs.get(run_id)
        assert run.workspace.joinpath("security_attempts/security_report.json").is_file()
        for finding in security["decisions"]:
            assert finding["cwe"] and finding["confidence"] and finding["proposed_fix"]
    assert project_hashes(source) == before
