import json

from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.core.runs import hashes_for
from backend.universal import main


def test_single_file_hash_uses_actual_bytes_and_cli_is_static(tmp_path, capsys):
    path = tmp_path / "module.py"
    path.write_text('raise RuntimeError("must not execute")\n')
    before = hashes_for(path)
    assert set(before) == {"module.py"}
    assert main(["detect", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["project_executed"] is False
    assert hashes_for(path) == before


def test_cli_bad_source_returns_structured_error(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.py"), "--target-version", "3.13"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "source_not_found"


def test_legacy_migration_rejects_unimplemented_version_pair(monkeypatch, project):
    monkeypatch.setenv("PROOFPORT_PIPELINE", "fixtures")
    monkeypatch.setenv("PROOFPORT_TARGET_VERSION", "3.13")
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    with TestClient(create_app(project)) as application:
        response = application.post("/api/runs", json={"source_path": "samples/legacy_shop"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unsupported_migration_pair"
