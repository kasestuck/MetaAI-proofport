from hashlib import sha256
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.evidence import entry_hash


SOURCE = "samples/legacy_shop"
STATE_FIELDS = {"status", "phase", "isolation", "modules", "security", "hashes", "metrics", "chain_intact"}


def start(client):
    response = client.post("/api/runs", json={"source_path": SOURCE})
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"run_id"}
    return response.json()["run_id"]


def wait_done(client, run_id):
    deadline = time.monotonic() + 5
    snapshots = []
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        state = response.json()
        snapshots.append(state)
        if state["status"] in {"done", "failed"}:
            assert state["status"] == "done", state
            return state, snapshots
        time.sleep(0.002)
    pytest.fail("Run did not finish within five seconds")


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True, "docker": False, "llm_mode": "mock"}


def test_run_lifecycle_contract_real_hashes_and_events(client, project):
    source = project / SOURCE
    original_bytes = {p.name: p.read_bytes() for p in source.iterdir()}
    run_id = start(client)
    done, snapshots = wait_done(client, run_id)
    assert set(done) == STATE_FIELDS
    for state in snapshots:
        assert set(state) == STATE_FIELDS
        assert state["isolation"] == "reduced"
        for module in state["modules"]:
            assert set(module) == {"name", "status", "iterations", "tests_passed", "tests_total"}
    statuses = {m["status"] for state in snapshots for m in state["modules"]}
    assert {"pending", "translating", "testing", "green"} <= statuses
    assert {m["name"] for m in done["modules"]} == {"config", "mathutils", "storage"}
    assert all(m["status"] == "green" and m["iterations"] == 1 for m in done["modules"])
    assert done["metrics"]["tests_passed"] == done["metrics"]["tests_total"] > 0
    assert set(done["metrics"]) == {"tests_passed", "tests_total", "lines_migrated", "tokens_in", "tokens_out", "cost_usd", "seconds"}
    assert done["metrics"]["lines_migrated"] == sum(len(p.read_text().splitlines()) for p in source.glob("*.py"))
    assert done["hashes"] == {
        **{f"legacy_shop/{name}": sha256(content).hexdigest() for name, content in original_bytes.items()},
        "unchanged": True,
    }
    assert {p.name: p.read_bytes() for p in source.iterdir()} == original_bytes
    assert set(done["security"]) == {"before", "after", "findings"}
    assert done["security"]["before"] == 3
    assert done["security"]["after"] == 2
    assert {f["status"] for f in done["security"]["findings"]} == {"fixed", "needs_review"}
    for finding in done["security"]["findings"]:
        assert set(finding) == {"id", "file", "line", "severity", "status", "note"}
        assert "SIMULATED" in finding["note"]
    entries = client.get(f"/api/runs/{run_id}/events").json()
    previous = "0" * 64
    for seq, event in enumerate(entries, 1):
        assert set(event) == {"seq", "ts", "type", "module", "detail", "prev_hash", "entry_hash"}
        assert event["seq"] == seq
        assert event["prev_hash"] == previous
        assert event["entry_hash"] == entry_hash(event)
        previous = event["entry_hash"]
    assert entries[-1]["type"] == "run_finished"
    assert done["chain_intact"] is True
    cursor = entries[len(entries) // 2]["seq"]
    assert client.get(f"/api/runs/{run_id}/events?since={cursor}").json() == [e for e in entries if e["seq"] > cursor]
    assert client.get(f"/api/runs/{run_id}/events?since={entries[-1]['seq']}").json() == []
    # Completion releases the single-worker slot.
    start(client)


def test_busy_and_report_not_ready(project, monkeypatch):
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    with TestClient(create_app(project, step_seconds=0.1)) as client:
        run_id = start(client)
        response = client.post("/api/runs", json={"source_path": SOURCE})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "run_busy"
        response = client.get(f"/api/runs/{run_id}/report")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "run_not_finished"


def test_reports(client):
    run_id = start(client)
    done, _ = wait_done(client, run_id)
    response = client.get(f"/api/runs/{run_id}/report?format=json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"].endswith(f'{run_id}.json"')
    report = response.json()
    assert report["simulation"] is True
    assert report["state"] == done
    assert report["events"][-1]["type"] == "run_finished"
    assert "MODEL_API_KEY" not in response.text
    html = client.get(f"/api/runs/{run_id}/report?format=html")
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert "SIMULATED" in html.text
    assert "mathutils" in html.text
    assert html.headers["content-disposition"].endswith(f'{run_id}.html"')


@pytest.mark.parametrize("suffix", ["", "/events", "/report"])
def test_unknown_run(client, suffix):
    response = client.get(f"/api/runs/missing{suffix}")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "run_not_found", "message": "The requested run does not exist."}}


@pytest.mark.parametrize("body,code", [
    ({"source_path": "missing"}, "source_not_found"),
    ({}, "invalid_request"),
    ({"source_path": SOURCE, "max_iterations": 0}, "invalid_request"),
    ({"source_path": SOURCE, "max_iterations": "5"}, "invalid_request"),
])
def test_start_errors(client, body, code):
    response = client.post("/api/runs", json=body)
    assert response.status_code in {400, 422}
    assert response.json()["error"]["code"] == code


def test_empty_source(client, project):
    (project / "empty").mkdir()
    response = client.post("/api/runs", json={"source_path": "empty"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "source_empty"


def test_invalid_queries(client):
    run_id = start(client)
    for suffix in ["events?since=-1", "events?since=no", "report?format=pdf"]:
        response = client.get(f"/api/runs/{run_id}/{suffix}")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"


def test_original_edit_causes_failed_run(project, monkeypatch):
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    with TestClient(create_app(project, step_seconds=0.01)) as client:
        run_id = start(client)
        (project / SOURCE / "mathutils.py").write_text("# externally edited\n")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get(f"/api/runs/{run_id}").json()
            if state["status"] == "failed":
                break
            time.sleep(0.005)
        assert state["status"] == "failed"
        assert state["error"]["code"] == "source_changed"
        assert state["hashes"]["unchanged"] is False
        assert state["chain_intact"] is True
        assert client.get(f"/api/runs/{run_id}/report?format=json").status_code == 200


def test_static_frontend_and_api_precedence(project, monkeypatch):
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Frontend fixture</h1>")
    (frontend / "app.js").write_text("// fixture")
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    with TestClient(create_app(project)) as client:
        assert "Frontend fixture" in client.get("/").text
        assert client.get("/app.js").status_code == 200
        assert client.get("/api/health").json()["ok"] is True


def test_missing_frontend_landing_page(client):
    assert client.get("/").status_code == 200
    assert "Proofport" in client.get("/").text


def test_tampered_durable_evidence_revokes_success(client, project):
    run_id = start(client)
    wait_done(client, run_id)
    evidence = client.app.state.runs.get(run_id).evidence
    log = project / "evidence.log"
    evidence.bind(log)
    log.write_text(log.read_text().replace("SIMULATED", "TAMPERED"))
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["status"] == "failed"
    assert state["chain_intact"] is False
    assert state["error"]["code"] == "evidence_corrupted"
