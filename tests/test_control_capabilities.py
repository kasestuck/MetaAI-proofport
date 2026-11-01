from backend.core.capabilities import Capabilities, MetadataProbe
from backend.core.versions import RUNTIMES
from backend.sandbox.runner import SandboxError


def test_metadata_reads_never_run_containers_or_model_and_cache_is_defensive(tmp_path, monkeypatch):
    calls = []
    def unavailable(self):
        calls.append("info")
        return False
    def forbidden(*args, **kwargs):
        raise AssertionError("No run/image pull/model is allowed in unavailable metadata probes")
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.available", unavailable)
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run", forbidden)
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner._metadata", forbidden)
    monkeypatch.setattr("backend.llm.client.OpenAI", forbidden)
    caps = Capabilities(tmp_path)
    first = caps.snapshot()
    assert not first["docker"]["available"]
    assert not first["live"]["enabled"] and not first["ai_security_fix"]["enabled"]
    assert {entry["version"] for entry in first["runtimes"]} == set(RUNTIMES)
    assert all(entry["configured"] and not entry["available"] and not entry["verified"] for entry in first["runtimes"])
    first["docker"]["available"] = True
    assert not caps.snapshot()["docker"]["available"]
    assert calls == ["info"]
    caps.snapshot(fresh=True)
    assert calls == ["info", "info"]
    assert not hasattr(MetadataProbe(None, False, 0), "run")


def test_expired_metadata_deadline_does_not_start_process():
    import pytest
    with pytest.raises(SandboxError):
        MetadataProbe(None, True, 0)._metadata(["image", "inspect", "python:3.12-slim"])
