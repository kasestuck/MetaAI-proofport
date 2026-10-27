import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app


@pytest.mark.parametrize("mode", ["mock", "live", "replay"])
@pytest.mark.parametrize("docker", [False, True])
def test_default_never_claims_unverified_migration(project, monkeypatch, mode, docker):
    monkeypatch.delenv("PROOFPORT_PIPELINE")
    monkeypatch.setenv("LLM_MODE", mode)
    monkeypatch.setattr("backend.api.main.docker_available", lambda: docker)
    marker = project / "executed.txt"
    (project / "samples/legacy_shop/danger.py").write_text(
        f"open({str(marker)!r}, 'w').write('executed')\n", encoding="utf-8",
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Static inspection must not execute subprocesses or call a model")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("backend.llm.client.OpenAI", forbidden)
    with TestClient(create_app(project, step_seconds=0.001)) as client:
        response = client.post("/api/runs", json={"source_path": "samples/legacy_shop"})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get(f"/api/runs/{run_id}").json()
            assert state["status"] != "done"
            assert all(m["status"] != "green" for m in state["modules"])
            if state["status"] == "failed":
                break
            time.sleep(0.002)
        assert state["status"] == "failed"
        assert state["error"]["code"] == ("pipeline_unavailable" if docker else "docker_unavailable")
        assert state["hashes"]["unchanged"] is True
        assert state["chain_intact"] is True
        for metric, value in state["metrics"].items():
            if metric != "seconds":
                assert value == 0
        assert all(m["iterations"] == m["tests_passed"] == m["tests_total"] == 0 for m in state["modules"])
        report = client.get(f"/api/runs/{run_id}/report?format=json").json()
        assert report["simulation"] is False
        assert report["settings"]["pipeline"] == "static_only"
        assert "not scanned, not secure" in report["notice"]
        assert {e["type"] for e in report["events"]} == {"run_started", "hashes_recorded", "error", "run_finished"}
        html = client.get(f"/api/runs/{run_id}/report?format=html").text
        assert "unverified source inventory" in html
        assert "Executed tests (unavailable)" in html
    assert not marker.exists()


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_simulation_cannot_masquerade_as_live_or_replay(project, monkeypatch, mode):
    monkeypatch.setenv("PROOFPORT_PIPELINE", "simulation")
    monkeypatch.setenv("LLM_MODE", mode)
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    with TestClient(create_app(project)) as client:
        response = client.post("/api/runs", json={"source_path": "samples/legacy_shop"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "pipeline_unavailable"
        assert not client.app.state.runs.runs
