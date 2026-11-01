"""PHP control contract tests with mocked readiness; no Docker evidence inferred."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.languages.runtimes import PHP_RUNTIMES


ROOT=Path(__file__).resolve().parents[1]


def php_readiness(ready=True):
    return {"docker":{"available":ready},"languages":{"php":{"supported_operations":["migration","audit","compatibility"] if ready else [],
        "readiness":{"can_start":ready,"requires_preflight":True},"runtimes":[{"version":r.version,"image":r.image,"image_id":"sha256:"+str(i)*64,"available":ready,"verified":ready} for i,r in enumerate(PHP_RUNTIMES,1)]}}}


def body(**changes):
    return {"language":"php","operation":"migration","project_id":"php_shop","source_version":"7.4","target_version":"8.3",
        "execution_mode":"offline_fixtures","fixture_profile_id":"php_shop_74_83","cases_profile_id":"php_shop_golden", **changes}


def wait(client,run_id):
    for _ in range(200):
        result=client.get("/api/v1/runs/"+run_id).json()
        if result["finalized"]: return result
        time.sleep(.01)
    pytest.fail("PHP audit did not finalize")


@pytest.fixture
def php_client(project,monkeypatch):
    for name in ("php_shop","php_profiles"):
        shutil.copytree(ROOT/"tests/fixtures"/name,project/"tests/fixtures"/name)
    monkeypatch.setattr("backend.api.main.docker_available",lambda:False)
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**k:pytest.fail("No Meta SDK"))
    monkeypatch.setattr("backend.llm.client.LLMClient.complete",lambda *a,**k:pytest.fail("No model calls"))
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run",lambda *a,**k:pytest.fail("No project execution in unit contracts"))
    app=create_app(project)
    monkeypatch.setattr(app.state.control.capabilities,"snapshot",lambda fresh=False:php_readiness())
    with TestClient(app) as client: yield client


def test_php_run_spec_is_immutable_source_bound_and_does_not_change_python_settings(php_client):
    control=php_client.app.state.control; store=php_client.app.state.runs
    original=dict(store.settings)
    spec=control.prepare(__import__('backend.core.control_models',fromlist=['ControlRequest']).ControlRequest(**body()))
    assert spec.language=="php" and spec.public()["language"]=="php" and len(spec.images)==2
    with pytest.raises(FrozenInstanceError): spec.target_version="8.4"
    assert store.settings==original and "MODEL_API_KEY" not in dict(spec.settings)
    # Same PHP project is still unavailable to an implicit legacy Python request.
    response=php_client.post("/api/runs",json={"source_path":"tests/fixtures/php_shop"})
    assert response.status_code==422 and response.json()["error"]["code"]=="language_not_enabled"


@pytest.mark.parametrize("changes,code",[
    ({"source_version":"8.4"},"unsupported_php_version"),({"target_version":"8.4"},"unsupported_migration_pair"),
    ({"execution_mode":"live"},"live_disabled"),({"execution_mode":"simulation"},"incompatible_parameters"),
    ({"cases_profile_id":None},"profile_unavailable"),({"fixture_profile_id":"legacy_shop_py27_py312"},"profile_unavailable"),
    ({"security_fix_profile_id":"untrusted/path.json"},"profile_unavailable"),({"verification_level":"syntax"},"incompatible_parameters"),
    ({"project_id":"legacy_shop"},"language_mismatch")])
def test_php_preflight_rejects_wrong_combinations(php_client,changes,code):
    r=php_client.post("/api/v1/runs/preflight",json=body(**changes))
    assert r.status_code==200 and not r.json()["can_start"] and r.json()["errors"][0]["code"]==code
    assert php_client.app.state.runs.active is None


def test_php_not_advertised_without_proof_or_docker(php_client,monkeypatch):
    monkeypatch.setattr(php_client.app.state.control.capabilities,"snapshot",lambda fresh=False:php_readiness(False))
    r=php_client.post("/api/v1/runs/preflight",json=body()).json()
    assert not r["can_start"] and r["errors"][0]["code"]=="docker_unavailable"
    assert php_client.post("/api/v1/runs",json=body()).status_code==503


def test_static_php_audit_202_idempotency_legacy_reports_and_no_ai(php_client):
    request={"language":"php","operation":"audit","project_id":"php_shop","source_version":"7.4"}
    before=dict(php_client.app.state.runs.settings)
    assert php_client.post("/api/v1/runs/preflight",json=request).json()["can_start"]
    response=php_client.post("/api/v1/runs",json=request,headers={"Idempotency-Key":"php-unit-audit"})
    assert response.status_code==202
    run_id=response.json()["run_id"]; result=wait(php_client,run_id)
    assert result["state"]["status"]=="done" and result["result"]["compatibility"]["level"]=="not_verified"
    assert not result["execution"]["ai_generated"] and result["execution"]["effective"]=="offline"
    assert result["state"]["security"]["before"]==result["state"]["security"]["after"]==10
    assert result["state"]["isolation"]=="reduced" and result["state"]["hashes"]["unchanged"]
    assert php_client.get("/api/runs/"+run_id).json()==result["state"]
    report=php_client.get(f"/api/runs/{run_id}/report?format=json").json()
    assert report["verification"]["model_calls"]==0 and report["verification"]["chain_intact"]
    assert "Static audit only" in report["notice"] and "Bandit" not in report["notice"]
    assert php_client.get(f"/api/runs/{run_id}/report?format=html").status_code==200
    assert php_client.get(f"/api/runs/{run_id}/events?since=2").json()
    assert php_client.post("/api/v1/runs",json=request,headers={"Idempotency-Key":"php-unit-audit"}).json()["run_id"]==run_id
    conflict=php_client.post("/api/v1/runs",json={**request,"source_version":"8.3"},headers={"Idempotency-Key":"php-unit-audit"})
    assert conflict.status_code==409 and php_client.app.state.runs.settings==before


def test_busy_gate_shared_and_critical_readiness_rechecked(php_client,monkeypatch):
    control=php_client.app.state.control; store=php_client.app.state.runs
    assert php_client.post("/api/v1/runs/preflight",json=body()).json()["can_start"]
    store.active="unit-other-run"
    assert php_client.post("/api/v1/runs",json=body()).status_code==409
    assert not php_client.post("/api/v1/runs/preflight",json=body()).json()["can_start"]
    store.active=None
    monkeypatch.setattr(control.capabilities,"snapshot",lambda fresh=False:php_readiness(False))
    assert php_client.post("/api/v1/runs",json=body()).status_code==503


def test_php_profiles_are_server_bound_and_paths_never_accepted(php_client):
    catalog=php_client.get("/api/v1/projects").json()
    project=next(p for p in catalog["projects"] if p["project_id"]=="php_shop")
    assert project["language"]=="php" and project["available_profiles"]["security_fix"]==["php_shop_security"]
    assert php_client.post("/api/v1/runs/preflight",json=body(mount_options="evil")).status_code==422
    assert php_client.post("/api/v1/projects/resolve",json={"relative_path":"backend/.work"}).status_code==403
