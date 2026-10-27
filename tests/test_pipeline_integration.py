import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.runs import hashes_for
from backend.core.translator import FixtureTranslator
from backend.sandbox.runner import DockerRunner


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "samples/legacy_shop"


@pytest.fixture
def real_settings(monkeypatch):
    assert SOURCE.is_dir(), "Unpack the original legacy_shop under samples/legacy_shop"
    assert DockerRunner().available(), "Real Docker is required"
    monkeypatch.setenv("PROOFPORT_PIPELINE", "fixtures")
    monkeypatch.setenv("PROOFPORT_CASES_FILE", str(ROOT / "tests/fixtures/legacy_shop/cases.json"))
    monkeypatch.setenv("PROOFPORT_FIXTURE_FILE", str(ROOT / "tests/fixtures/legacy_shop/patches.json"))
    return monkeypatch


def run_pipeline():
    client = TestClient(create_app(ROOT, step_seconds=0.001))
    return client


def await_result(client, run_id):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        state = response.json()
        if state["status"] in {"done", "failed"}:
            # Wait for report persistence and worker cleanup, not just status assignment.
            if client.app.state.runs.active is None:
                return state
        time.sleep(0.05)
    pytest.fail("Real Docker pipeline did not finish within 90 seconds")


def test_real_fixture_pipeline_api_reports_and_originals(real_settings):
    original_hashes = hashes_for(SOURCE)
    with run_pipeline() as client:
        response = client.post("/api/runs", json={"source_path": "samples/legacy_shop", "max_iterations": 1})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        assert client.post("/api/runs", json={"source_path": "samples/legacy_shop"}).status_code == 409
        state = await_result(client, run_id)
        assert state["status"] == "done", state
        assert set(state) == {"status", "phase", "isolation", "modules", "security", "hashes", "metrics", "chain_intact"}
        assert state["isolation"] == "docker"
        assert state["hashes"]["unchanged"] is True
        assert state["chain_intact"] is True
        assert len(state["modules"]) == 9  # Eight modules plus the imported package initializer.
        assert all(module["status"] == "green" and module["tests_total"] > 0 for module in state["modules"])
        assert state["metrics"]["tests_passed"] == state["metrics"]["tests_total"] == 100
        assert state["metrics"]["tokens_in"] == state["metrics"]["tokens_out"] == state["metrics"]["cost_usd"] == 0
        report = client.get(f"/api/runs/{run_id}/report?format=json").json()
        verification = report["verification"]
        assert report["simulation"] is False
        assert report["settings"]["pipeline"] == "fixtures"
        assert verification["ai_migration"] is False
        assert verification["model_calls"] == 0
        assert verification["legacy_tests"]["tests_run"] == verification["target_tests"]["tests_run"] == 10
        assert len(verification["comparisons"]) == 90
        assert all(case["matches"] for case in verification["comparisons"])
        assert report["allowed_differences"]
        assert state["security"]["before"] == state["security"]["after"] == 8
        assert len(verification["security_before"]["errors"]) == 4
        assert verification["security_after"]["errors"] == []
        assert {f["status"] for f in state["security"]["findings"]} <= {"open", "needs_review"}
        assert {f["scanner_test"] for f in verification["security_details"]} >= {"B307", "B324", "B301", "B608", "B602", "B105"}
        assert all(f["cwe"] and f["confidence"] for f in verification["security_details"])
        assert "shop-secret-2013" not in json.dumps(report)
        html = client.get(f"/api/runs/{run_id}/report?format=html")
        assert html.status_code == 200
        assert "REAL Docker execution" in html.text
        assert "not AI migration" in html.text
        run = client.app.state.runs.get(run_id)
        assert run.workspace.joinpath("golden.json").is_file()
        assert run.workspace.joinpath("original_hashes.json").is_file()
        assert run.workspace.joinpath("report.html").is_file()
        assert json.loads(run.workspace.joinpath("report.json").read_text())["state"]["status"] == "done"
        assert run.evidence.verify()
        entries = client.get(f"/api/runs/{run_id}/events?since=3").json()
        assert entries and all(entry["seq"] > 3 for entry in entries)
        assert any(entry["type"] == "sandbox_run" for entry in entries)
    assert hashes_for(SOURCE) == original_hashes


def test_real_fix_loop_retests_evidence_after_bad_candidate(real_settings, monkeypatch):
    original_translate = FixtureTranslator.translate
    calls = {}
    feedback = []
    def candidates(self, relative, source, previous=None, failures=None):
        code = original_translate(self, relative, source, previous, failures)
        calls[relative] = calls.get(relative, 0) + 1
        if relative == "legacy_shop/mathutils.py" and calls[relative] == 1:
            return code.replace("_py2_div(sum(values), len(values))", "sum(values) / len(values)")
        if relative == "legacy_shop/mathutils.py" and failures:
            feedback.append(failures)
        return code
    monkeypatch.setattr(FixtureTranslator, "translate", candidates)
    with run_pipeline() as client:
        run_id = client.post("/api/runs", json={"source_path": "samples/legacy_shop", "max_iterations": 2}).json()["run_id"]
        state = await_result(client, run_id)
        assert state["status"] == "done", state
        assert feedback
        math = next(module for module in state["modules"] if module["name"] == "legacy_shop.mathutils")
        assert math["iterations"] == 2
        workspace = client.app.state.runs.get(run_id).workspace
        first = json.loads((workspace / "comparisons_1.json").read_text())
        second = json.loads((workspace / "comparisons_2.json").read_text())
        assert any(not case["matches"] for case in first)
        assert all(case["matches"] for case in second)


def test_failed_candidate_never_becomes_success(real_settings, monkeypatch):
    original_translate = FixtureTranslator.translate
    def bad(self, relative, source, previous=None, failures=None):
        code = original_translate(self, relative, source, previous, failures)
        if relative == "legacy_shop/mathutils.py":
            return code.replace("_py2_div(sum(values), len(values))", "sum(values) / len(values)")
        return code
    monkeypatch.setattr(FixtureTranslator, "translate", bad)
    with run_pipeline() as client:
        run_id = client.post("/api/runs", json={"source_path": "samples/legacy_shop", "max_iterations": 1}).json()["run_id"]
        state = await_result(client, run_id)
        assert state["status"] == "failed"
        assert state["error"]["code"] == "verification_failed"
        assert any(module["status"] == "failed" for module in state["modules"])
        assert state["hashes"]["unchanged"] is True
        assert state["chain_intact"] is True


def test_missing_meta_key_records_behavior_without_ai_fallback(real_settings, monkeypatch):
    monkeypatch.setenv("PROOFPORT_PIPELINE", "verify")
    monkeypatch.setenv("LLM_MODE", "live")
    def no_api(**kwargs):
        pytest.fail("No SDK request is allowed without configured key and model")
    monkeypatch.setattr("backend.llm.client.OpenAI", no_api)
    with run_pipeline() as client:
        run_id = client.post("/api/runs", json={"source_path": "samples/legacy_shop", "max_iterations": 1}).json()["run_id"]
        state = await_result(client, run_id)
        assert state["status"] == "failed"
        assert state["error"]["code"] == "model_unavailable"
        assert all(module["status"] == "failed" for module in state["modules"])
        report = client.get(f"/api/runs/{run_id}/report?format=json").json()
        assert report["verification"]["golden_case_count"] == 90
        assert report["verification"]["ai_migration"] is False
        assert report["verification"]["model_calls"] == 0
