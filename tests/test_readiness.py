import json
import subprocess

from backend.core.readiness import inspect_readiness


def test_missing_docker_checks_no_code_or_network(project, monkeypatch):
    monkeypatch.setattr("backend.core.readiness.find_docker", lambda: None)
    def forbidden(*args, **kwargs):
        raise AssertionError("No subprocess is needed when Docker is absent")
    monkeypatch.setattr("backend.core.readiness.subprocess.run", forbidden)
    result = inspect_readiness(project).snapshot()
    assert result["ready"] is False
    assert result["source_present"] is True
    assert result["docker"] is False
    assert not any(result["images"].values())
    assert {"docker_unavailable", "live_model_not_selected", "model_not_configured"} <= set(result["blockers"])


def test_configured_prerequisites_report_attempt_readiness_not_live_success(project, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("MODEL_API_KEY", "readiness-test-placeholder")
    monkeypatch.setenv("MODEL_NAME", "configured-name-is-not-a-live-call")
    monkeypatch.setattr("backend.core.readiness.find_docker", lambda: "docker-test")
    case_file = project / "cases.json"
    case_file.write_text('{"cases":[]}')
    monkeypatch.setenv("PROOFPORT_CASES_FILE", str(case_file))
    commands = []
    def success(args, **kwargs):
        commands.append(args)
        assert kwargs["timeout"] == 3
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr("backend.core.readiness.subprocess.run", success)
    result = inspect_readiness(project).snapshot()
    assert result["blockers"] == []
    assert result["ready"] is True  # Configuration only; no model or user code executed.
    assert result["api_key_configured"] is True
    assert "readiness-test-placeholder" not in json.dumps(result)
    assert commands == [
        ["docker-test", "info", "--format", "{{.ServerVersion}}"],
        ["docker-test", "image", "inspect", "python:2.7"],
        ["docker-test", "image", "inspect", "python:3.12-slim"],
        ["docker-test", "image", "inspect", "proofport-bandit:1.8.6"],
    ]


def test_docker_timeout_has_no_host_fallback(project, monkeypatch):
    commands = []
    monkeypatch.setattr("backend.core.readiness.find_docker", lambda: "docker-test")
    def timeout(args, **kwargs):
        commands.append(args)
        raise subprocess.TimeoutExpired(args, 3)
    monkeypatch.setattr("backend.core.readiness.subprocess.run", timeout)
    assert not inspect_readiness(project).docker
    assert len(commands) == 1
    assert commands[0][1] == "info"
