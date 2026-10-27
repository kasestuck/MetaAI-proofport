import json
import subprocess

from backend.core.readiness import inspect_readiness


def test_missing_docker_checks_no_code_or_network(project, monkeypatch):
    monkeypatch.setattr("backend.core.readiness.shutil.which", lambda _: None)
    def forbidden(*args, **kwargs):
        raise AssertionError("No subprocess is needed when Docker is absent")
    monkeypatch.setattr("backend.core.readiness.subprocess.run", forbidden)
    result = inspect_readiness(project).snapshot()
    assert result["ready"] is False
    assert result["source_present"] is True
    assert result["docker"] is False
    assert not any(result["images"].values())
    assert {"docker_unavailable", "live_model_not_selected", "model_not_configured", "pipeline_not_implemented"} <= set(result["blockers"])


def test_configured_prerequisites_do_not_claim_implemented_pipeline(project, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("MODEL_API_KEY", "readiness-test-placeholder")
    monkeypatch.setenv("MODEL_NAME", "configured-name-is-not-a-live-call")
    monkeypatch.setattr("backend.core.readiness.shutil.which", lambda _: "docker-test")
    commands = []
    def success(args, **kwargs):
        commands.append(args)
        assert kwargs["timeout"] == 3
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr("backend.core.readiness.subprocess.run", success)
    result = inspect_readiness(project).snapshot()
    assert result["blockers"] == ["pipeline_not_implemented"]
    assert result["ready"] is False
    assert result["api_key_configured"] is True
    assert "readiness-test-placeholder" not in json.dumps(result)
    assert commands == [
        ["docker-test", "info", "--format", "{{.ServerVersion}}"],
        ["docker-test", "image", "inspect", "python:2.7"],
        ["docker-test", "image", "inspect", "python:3.12-slim"],
    ]


def test_docker_timeout_has_no_host_fallback(project, monkeypatch):
    commands = []
    monkeypatch.setattr("backend.core.readiness.shutil.which", lambda _: "docker-test")
    def timeout(args, **kwargs):
        commands.append(args)
        raise subprocess.TimeoutExpired(args, 3)
    monkeypatch.setattr("backend.core.readiness.subprocess.run", timeout)
    assert not inspect_readiness(project).docker
    assert len(commands) == 1
    assert commands[0][1] == "info"
