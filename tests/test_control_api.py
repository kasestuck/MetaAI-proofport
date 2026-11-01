"""Control contract tests. Fake readiness is never treated as execution evidence."""

import asyncio
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.control_models import ControlRequest, RunSpec
from backend.core.runs import hashes_for
from backend.core.security import SCANNER_IMAGE
from backend.core.versions import RUNTIMES


ROOT = Path(__file__).resolve().parents[1]


def readiness():
    return {"docker": {"available": True}, "runtimes": [
        {"version": version, "image": item.image, "image_id": "sha256:" + str(index) * 64,
         "available": True, "verified": True, "python": [*map(int, version.split(".")), 16]} for index, (version, item) in enumerate(RUNTIMES.items(), 1)],
        "scanner": {"available": True, "image": SCANNER_IMAGE, "image_id": "sha256:" + "a" * 64}}


@pytest.fixture(autouse=True)
def no_meta(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Control plane must not construct/call a model SDK")
    monkeypatch.setattr("backend.llm.client.OpenAI", forbidden)
    monkeypatch.setattr("backend.llm.client.LLMClient.complete", forbidden)


@pytest.fixture
def control_client(project, monkeypatch):
    fixture = project / "tests/fixtures/universal_py3"
    fixture.parent.mkdir(parents=True)
    shutil.copytree(ROOT / "tests/fixtures/universal_py3", fixture)
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    app = create_app(project, step_seconds=0.01)
    monkeypatch.setattr(app.state.control.capabilities, "snapshot", lambda fresh=False: readiness())
    with TestClient(app) as client:
        yield client


def wait(client, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        data = client.get("/api/v1/runs/" + run_id).json()
        if data["finalized"]:
            return data
        time.sleep(0.01)
    pytest.fail("Control run did not finalize")


def simulation(**changes):
    return {"operation": "migration", "project_id": "legacy_shop", "execution_mode": "simulation", **changes}


def compatible(**changes):
    return {"operation": "compatibility", "project_id": "universal_py3", "execution_mode": "offline",
            "source_version": "3.12", "target_version": "3.13", **changes}


def test_all_routes_and_static_mount_precedence(control_client, project):
    client = control_client
    assert client.get("/api/v1/capabilities").status_code == 200
    projects = client.get("/api/v1/projects").json()
    assert next(item for item in projects["projects"] if item["project_id"] == "legacy_shop")["available"]
    resolved = client.post("/api/v1/projects/resolve", json={"relative_path": "samples/legacy_shop"})
    assert resolved.json()["project_id"] == "legacy_shop"
    assert client.post("/api/v1/runs/preflight", json=simulation()).json()["can_start"]
    response = client.post("/api/v1/runs", json=simulation())
    assert response.status_code == 202
    result = wait(client, response.json()["run_id"])
    assert result["parameters"]["operation"] == "migration"
    assert result["parameters"]["execution_mode"] == "simulation"
    assert result["execution"] == {"effective": "simulation", "simulated": True, "ai_generated": False, "live_enabled": False}
    assert result["state"]["status"] == "done" and result["state"]["hashes"]["unchanged"]
    run_id = response.json()["run_id"]
    assert set(client.get("/api/runs/" + run_id).json()) == {"status", "phase", "isolation", "modules", "security", "hashes", "metrics", "chain_intact"}
    report = client.get(f"/api/runs/{run_id}/report?format=json").json()
    assert report["simulation"] and "SIMULATED" in report["notice"]
    assert report["verification"]["control"]["parameters"] == result["parameters"]
    assert client.get(f"/api/runs/{run_id}/report?format=html").status_code == 200
    assert client.get(f"/api/runs/{run_id}/events?since=2").json()[0]["seq"] == 3


def test_idempotency_and_shared_busy_gate(control_client, monkeypatch):
    client = control_client
    import threading
    release = threading.Event()
    async def hold():
        while not release.is_set():
            await asyncio.sleep(0.001)
    monkeypatch.setattr(client.app.state.runs, "_pause", hold)
    headers = {"Idempotency-Key": "p41-test-0001"}
    first = client.post("/api/v1/runs", json=simulation(), headers=headers)
    run_id = first.json()["run_id"]
    assert client.post("/api/v1/runs", json=simulation(), headers=headers).json() == first.json()
    assert client.post("/api/v1/runs", json=simulation(max_iterations=2), headers=headers).status_code == 409
    assert client.post("/api/runs", json={"source_path": "samples/legacy_shop"}).status_code == 409
    assert client.post("/api/v1/runs", json=simulation()).status_code == 409
    release.set()
    wait(client, run_id)
    assert client.post("/api/v1/runs", json=simulation(), headers=headers).json() == first.json()
    assert len(client.app.state.runs.runs) == 1
    release.clear()
    legacy = client.post("/api/runs", json={"source_path": "samples/legacy_shop"})
    assert legacy.status_code == 200 and set(legacy.json()) == {"run_id"}
    assert client.post("/api/v1/runs", json=simulation()).status_code == 409
    release.set()
    wait(client, legacy.json()["run_id"])


@pytest.mark.parametrize("body,code", [
    (simulation(execution_mode="live"), "live_disabled"),
    (simulation(source_version="2.7"), "incompatible_parameters"),
    (compatible(source_version="3.9"), "unsupported_python_version"),
    (compatible(source_version="3.8"), "unsupported_compatibility_pair"),
    (compatible(verification_level="behavior"), "profile_unavailable"),
    (compatible(cases_profile_id="universal_py3_golden"), "incompatible_parameters"),
    (compatible(verification_level="behavior", cases_profile_id="legacy_shop_golden"), "profile_unavailable"),
    ({"operation": "migration", "project_id": "legacy_shop", "source_version": "2.7", "target_version": "3.13", "execution_mode": "offline_fixtures"}, "unsupported_migration_pair"),
    ({"operation": "audit", "project_id": "legacy_shop", "source_version": "2.7", "target_version": "3.12"}, "incompatible_parameters"),
    (simulation(project_id="unregistered"), "project_not_found"),
])
def test_preflight_and_start_use_same_rejection(control_client, body, code):
    client = control_client
    preflight = client.post("/api/v1/runs/preflight", json=body)
    assert preflight.status_code == 200
    assert preflight.json()["can_start"] is False
    assert preflight.json()["errors"][0]["code"] == code
    start = client.post("/api/v1/runs", json=body)
    assert start.status_code >= 400 and start.json()["error"]["code"] == code
    assert not client.app.state.runs.runs


@pytest.mark.parametrize("field,value", [("operation", "shell"), ("execution_mode", "replay"), ("max_iterations", True),
                                        ("max_iterations", 6), ("mount_options", "rw"), ("docker_command", "anything"),
                                        ("MODEL_API_KEY", "never-accepted"), ("source_path", "C:/")])
def test_unknown_fields_and_invalid_modes_rejected(control_client, field, value):
    assert control_client.post("/api/v1/runs", json=simulation(**{field: value})).status_code == 422


@pytest.mark.parametrize("kind,code", [("docker", "docker_unavailable"), ("missing", "runtime_unavailable"), ("unverified", "unverified_version")])
def test_fresh_readiness_is_required(control_client, monkeypatch, kind, code):
    control = control_client.app.state.control
    assert control_client.post("/api/v1/runs/preflight", json=compatible()).json()["can_start"]
    def changed(fresh=False):
        assert fresh
        data = readiness()
        if kind == "docker":
            data["docker"]["available"] = False
        else:
            for runtime in data["runtimes"]:
                if runtime["version"] == "3.13":
                    runtime["available" if kind == "missing" else "verified"] = False
        return data
    monkeypatch.setattr(control.capabilities, "snapshot", changed)
    result = control_client.post("/api/v1/runs", json=compatible())
    assert result.status_code == 503 and result.json()["error"]["code"] == code
    assert not control_client.app.state.runs.runs


def test_specs_are_frozen_and_do_not_leak_parameters(control_client, project, monkeypatch):
    control = control_client.app.state.control
    env_before = dict(__import__('os').environ)
    server_before = dict(control.store.settings)
    source_before = hashes_for(project / "samples/legacy_shop")
    audit = control.prepare(ControlRequest(operation="audit", project_id="legacy_shop", source_version="2.7"))
    compat = control.prepare(ControlRequest(**compatible(verification_level="behavior", cases_profile_id="universal_py3_golden")))
    assert "PROOFPORT_CASES_FILE" not in dict(audit.settings)
    assert dict(compat.settings)["PROOFPORT_SOURCE_VERSION"] == "3.12"
    assert audit.source_version == "2.7" and not audit.target_version
    with pytest.raises(FrozenInstanceError):
        audit.operation = "migration"
    assert env_before == dict(__import__('os').environ)
    assert server_before == control.store.settings
    assert source_before == hashes_for(project / "samples/legacy_shop")
    assert not list(project.rglob(".env"))


def test_worker_rechecks_pinned_image_and_finalizes_failure(control_client, monkeypatch):
    # Unit dispatch failure, not fabricated compile/test results.
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.image_id", lambda self, tag: "sha256:" + "f" * 64)
    response = control_client.post("/api/v1/runs", json=compatible())
    assert response.status_code == 202
    data = wait(control_client, response.json()["run_id"])
    assert data["state"]["status"] == "failed" and data["state"]["error"]["code"] == "runtime_changed"
    assert data["state"]["metrics"]["tests_passed"] == 0
    assert control_client.app.state.runs.active is None


def test_unknown_run_header_validation_and_legacy_extra_fields(control_client):
    assert control_client.get("/api/v1/runs/missing").status_code == 404
    assert control_client.post("/api/v1/runs", json=simulation(), headers={"Idempotency-Key": "bad"}).status_code == 422
    assert control_client.post("/api/runs", json={"source_path": "samples/legacy_shop", "operation": "migration"}).status_code == 422


def test_new_runs_ignore_legacy_global_security_and_model_settings(control_client, monkeypatch):
    control = control_client.app.state.control
    control.store.settings.update(PROOFPORT_SECURITY_FIXTURES="must-not-leak", MODEL_API_KEY="unit-not-a-key", LLM_MODE="live")
    run_id = control_client.post("/api/v1/runs", json=simulation()).json()["run_id"]
    data = wait(control_client, run_id)
    run = control.store.get(run_id)
    assert data["state"]["status"] == "done"
    assert dict(run.spec.settings) == {} and not data["execution"]["ai_generated"]


def test_finalize_report_failure_cannot_leave_success_or_busy(control_client, project, monkeypatch):
    store = control_client.app.state.runs
    original = store._simulate
    async def with_workspace(run_id):
        await original(run_id)
        run = store.get(run_id)
        run.workspace = project / "missing_parent/artifact"
    monkeypatch.setattr(store, "_simulate", with_workspace)
    response = control_client.post("/api/v1/runs", json=simulation())
    data = wait(control_client, response.json()["run_id"])
    assert data["state"]["status"] == "failed" and data["state"]["error"]["code"] == "report_unavailable"
    assert store.active is None


def test_preflight_does_not_reserve_or_execute_project(control_client, project):
    marker = project / "executed.txt"
    (project / "tests/fixtures/universal_py3/danger.py").write_text('raise RuntimeError("never import preflight")\n')
    before = hashes_for(project / "tests/fixtures/universal_py3")
    for _ in range(2):
        assert control_client.post("/api/v1/runs/preflight", json=compatible()).json()["can_start"]
    assert not marker.exists()
    assert not control_client.app.state.runs.runs
    assert hashes_for(project / "tests/fixtures/universal_py3") == before


@pytest.mark.parametrize("path", ["../outside", "backend/.work", ".env", "samples/file.py:stream"])
def test_legacy_and_v1_use_same_path_policy(control_client, path):
    legacy = control_client.post("/api/runs", json={"source_path": path})
    modern = control_client.post("/api/v1/projects/resolve", json={"relative_path": path})
    assert legacy.status_code == modern.status_code == 403
    assert legacy.json()["error"]["code"] == modern.json()["error"]["code"]
    assert set(legacy.json()["error"]) == {"code", "message"}


def test_finalizing_remains_running_until_artifacts_persist(control_client, monkeypatch, project):
    import threading
    entered, release = threading.Event(), threading.Event()
    store = control_client.app.state.runs
    original_simulate, original_finish = store._simulate, store._finish
    async def with_workspace(run_id):
        await original_simulate(run_id)
        run = store.get(run_id)
        run.workspace = project / "artifact"
        run.workspace.mkdir()
    def paused_finish(run):
        entered.set()
        assert release.wait(5)
        original_finish(run)
    monkeypatch.setattr(store, "_simulate", with_workspace)
    monkeypatch.setattr(store, "_finish", paused_finish)
    run_id = control_client.post("/api/v1/runs", json=simulation()).json()["run_id"]
    assert entered.wait(5)
    try:
        data = control_client.get("/api/v1/runs/" + run_id).json()
        assert data["lifecycle"] == "finalizing" and not data["finalized"]
        assert data["state"]["status"] == "running"
        seconds = data["state"]["metrics"]["seconds"]
        time.sleep(0.02)
        assert control_client.get("/api/v1/runs/" + run_id).json()["state"]["metrics"]["seconds"] == seconds
        assert control_client.get(f"/api/runs/{run_id}/report").status_code == 409
        assert control_client.post("/api/v1/runs", json=simulation()).status_code == 409
    finally:
        release.set()
    assert wait(control_client, run_id)["state"]["status"] == "done"


@pytest.mark.parametrize("constraint,code", [(">=3.12.999,<3.13", "source_metadata_conflict"), (">=3.12,<3.13", "target_metadata_conflict")])
def test_preflight_checks_actual_patch_constraints(control_client, project, constraint, code):
    (project / "tests/fixtures/universal_py3/pyproject.toml").write_text('[project]\nrequires-python = "' + constraint + '"\n')
    response = control_client.post("/api/v1/runs/preflight", json=compatible()).json()
    assert not response["can_start"] and response["errors"][0]["code"] == code
    assert not control_client.app.state.runs.runs


def test_concurrent_idempotent_creation_returns_one_run(control_client):
    request = ControlRequest(**simulation())
    async def create_twice():
        return await asyncio.gather(*(control_client.app.state.control.start(request, "concurrent-0001") for _ in range(2)))
    ids = control_client.portal.call(create_twice)
    assert ids[0] == ids[1]
    wait(control_client, ids[0])
    assert len(control_client.app.state.runs.runs) == 1


def test_sequential_jobs_keep_independent_specs(control_client, monkeypatch):
    from backend.core.control_models import ControlError
    store = control_client.app.state.runs
    before = dict(store.settings)
    def stop_before_execution(run):
        raise ControlError("unit_dispatch_stop", "Unit test stops before any Docker execution.")
    monkeypatch.setattr(store, "_runner", stop_before_execution)
    requests = [{"operation": "audit", "project_id": "legacy_shop", "source_version": "2.7"}, compatible()]
    specs = []
    for body in requests:
        response = control_client.post("/api/v1/runs", json=body)
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        result = wait(control_client, run_id)
        assert result["state"]["error"]["code"] == "unit_dispatch_stop"
        specs.append(store.get(run_id).spec)
    assert specs[0].source_version == "2.7" and specs[0].target_version is None
    assert specs[1].source_version == "3.12" and specs[1].target_version == "3.13"
    assert before == store.settings


def test_configured_credentials_cannot_enable_live(control_client, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "unit-placeholder-not-a-real-key")
    monkeypatch.setenv("MODEL_NAME", "must-not-call")
    monkeypatch.setenv("LLM_MODE", "live")
    response = control_client.post("/api/v1/runs", json=simulation(execution_mode="live"))
    assert response.status_code == 403 and response.json()["error"]["code"] == "live_disabled"
    assert not control_client.app.state.runs.runs


def test_legacy_snapshot_does_not_capture_secret_environment_settings(control_client):
    store = control_client.app.state.runs
    store.settings["PROOFPORT_SHOP_SECRET"] = "unit-placeholder-private-value"
    run_id = control_client.post("/api/runs", json={"source_path": "samples/legacy_shop"}).json()["run_id"]
    wait(control_client, run_id)
    spec = store.get(run_id).spec
    assert "PROOFPORT_SHOP_SECRET" not in dict(spec.settings)
    assert "unit-placeholder-private-value" not in repr(spec)
    assert "unit-placeholder-private-value" not in control_client.get(f"/api/runs/{run_id}/report?format=json").text
