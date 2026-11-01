"""Only bounded P4.1 smoke tests; real Docker results, no stress tests/pulls/API."""

import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.runs import hashes_for


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def forbid_meta(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("P4.1 may not construct a model SDK or spend credits")
    monkeypatch.setattr("backend.llm.client.OpenAI", forbidden)
    monkeypatch.setattr("backend.llm.client.LLMClient.complete", forbidden)


@pytest.mark.parametrize("body,source,expected", [
    ({"operation": "migration", "project_id": "legacy_shop", "source_version": "2.7", "target_version": "3.12",
      "execution_mode": "offline_fixtures", "fixture_profile_id": "legacy_shop_py27_py312",
      "cases_profile_id": "legacy_shop_golden", "max_iterations": 1}, "samples/legacy_shop", "migration"),
    ({"operation": "audit", "project_id": "security_subject", "source_version": "3.12", "execution_mode": "offline"},
     "tests/fixtures/security_subject", "audit"),
    ({"operation": "compatibility", "project_id": "universal_py3", "source_version": "3.12", "target_version": "3.13",
      "execution_mode": "offline", "verification_level": "behavior", "cases_profile_id": "universal_py3_golden"},
     "tests/fixtures/universal_py3", "behavior"),
    ({"operation": "compatibility", "project_id": "universal_py3", "source_version": "3.12", "target_version": "3.12",
      "execution_mode": "offline", "verification_level": "syntax"}, "tests/fixtures/universal_py3", "syntax"),
])
def test_control_plane_real_operations(body, source, expected):
    originals = hashes_for(ROOT / source)
    with TestClient(create_app(ROOT)) as client:
        preflight = client.post("/api/v1/runs/preflight", json=body).json()
        assert preflight["can_start"], preflight
        response = client.post("/api/v1/runs", json=body, headers={"Idempotency-Key": "p41-smoke-" + expected})
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            details = client.get("/api/v1/runs/" + run_id).json()
            if details["finalized"]:
                break
            time.sleep(0.05)
        assert details["finalized"] and details["state"]["status"] == "done", details
        state = client.get("/api/runs/" + run_id).json()
        assert state == details["state"]
        assert state["isolation"] == "docker" and state["chain_intact"] and state["hashes"]["unchanged"]
        assert state["metrics"]["tokens_in"] == state["metrics"]["tokens_out"] == state["metrics"]["cost_usd"] == 0
        assert not details["execution"]["ai_generated"] and not details["execution"]["simulated"]
        report = client.get(f"/api/runs/{run_id}/report?format=json").json()
        verification = report["verification"]
        assert verification["model_calls"] == 0 and not verification["ai_migration"]
        assert verification["control"]["parameters"] == details["parameters"]
        workspace = client.app.state.runs.get(run_id).workspace
        assert json.loads((workspace / "report.json").read_text())["state"] == state
        assert (workspace / "report.html").exists()
        assert client.get(f"/api/runs/{run_id}/report?format=html").status_code == 200
        assert client.get(f"/api/runs/{run_id}/events?since=2").json()
        if expected == "migration":
            assert len(verification["comparisons"]) == 90 and all(item["matches"] for item in verification["comparisons"])
            assert verification["legacy_tests"]["tests_run"] == verification["target_tests"]["tests_run"] == 10
            assert state["metrics"]["tests_passed"] == state["metrics"]["tests_total"] == 100
        elif expected == "audit":
            assert state["security"]["before"] == state["security"]["after"] > 0
            assert not verification["security_audit"]["project_executed"]
            assert not verification["security_audit"]["fixes_applied"]
            assert state["metrics"]["tests_total"] == 0
        elif expected == "behavior":
            assert verification["compatibility"]["level"] == "behavior_verified"
            assert state["metrics"]["tests_passed"] == state["metrics"]["tests_total"] == 4
        else:
            assert verification["compatibility"]["level"] == "syntax_compatible"
            assert verification["compatibility"]["tests_passed"] is None
            assert state["metrics"]["tests_total"] == 0
    assert hashes_for(ROOT / source) == originals
