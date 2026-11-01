"""Adapter/discovery contracts; existing Python engines are delegated, not rebuilt."""

from dataclasses import FrozenInstanceError
from subprocess import CompletedProcess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.core.control_models import RunSpec
from backend.core.evidence import Evidence
from backend.languages.base import AdapterError, EvidenceSink, LanguageAdapter
from backend.languages.php import PHPAdapter
from backend.languages.python import PythonAdapter
from backend.languages.registry import LanguageRegistry
from backend.languages.runtimes import PHP_RUNTIMES, PHPRuntime, php_runtimes
from backend.sandbox.runner import SandboxError


class MetadataOnly:
    def __init__(self, available=True, timed_out=False): self.calls = []; self.local = available; self.timed_out = timed_out
    def _metadata(self, args):
        self.calls.append(args)
        assert args[:2] == ["image", "inspect"]
        if self.timed_out: raise SandboxError("Unit metadata timeout")
        return CompletedProcess(args, 0 if self.local else 1, ("sha256:" + "c" * 64).encode() if self.local else b"", b"")


def test_registry_is_extensible_and_does_not_construct_sdk_or_docker(monkeypatch):
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner", lambda *a, **k: pytest.fail("Registry selection is not execution"))
    registry = LanguageRegistry()
    assert isinstance(registry.get("python"), LanguageAdapter)
    assert isinstance(registry.get("php"), LanguageAdapter)
    assert isinstance(Evidence(), EvidenceSink)
    class Another(PHPAdapter): language = "another"
    registry.register(Another())
    assert registry.get("another").language == "another"
    with pytest.raises(ValueError): registry.register(PHPAdapter())
    with pytest.raises(AdapterError) as caught: registry.get("missing")
    assert caught.value.code == "unsupported_language"


@pytest.mark.parametrize("available", [True, False])
def test_php_image_presence_never_becomes_verified_operation_support(available):
    probe = MetadataOnly(available)
    data = LanguageRegistry().snapshot(probe=probe, docker=True)["php"]
    assert data["configured"] and not data["available"] and not data["verified"]
    assert data["supported_operations"] == [] and data["readiness"]["can_start"] is False
    assert data["source_versions"] == data["target_versions"] == []
    assert all(r["available"] is available and not r["verified"] for r in data["runtimes"])
    assert data["available_profiles"] == {"cases": [], "fixture": []}
    assert len(probe.calls) == len(PHP_RUNTIMES)


def test_unavailable_docker_or_probe_timeout_is_unknown_not_verified():
    probe = MetadataOnly(timed_out=True)
    assert all(r["available"] is None and r["reason"] == "metadata_unavailable" for r in php_runtimes(probe, docker=True))
    probe.calls.clear()
    assert all(r["available"] is None for r in php_runtimes(probe, docker=False))
    assert not probe.calls


def test_php_version_extension_uses_explicit_tag_without_adding_supported_operations():
    added = PHPRuntime("8.4", "php:8.4.27-cli")
    state = php_runtimes(MetadataOnly(), docker=True, runtimes=(*PHP_RUNTIMES, added))[-1]
    assert state["version"] == "8.4" and state["available"] and not state["verified"]
    with pytest.raises(FrozenInstanceError): added.image = "php:latest"


def test_python_registry_uses_existing_capability_pairs_roles_and_receipts():
    caps = {"runtimes": [{"version": "2.7", "available": True, "verified": True, "source": True, "target": False},
                         {"version": "3.12", "available": True, "verified": True, "source": True, "target": True}],
            "scanner": {"available": True}, "operations": {"migration": {"pairs": [["2.7", "3.12"]]},
            "audit": {"source_versions": ["2.7", "3.12"]}, "compatibility": {"pairs": [["3.12", "3.12"]]}}}
    first = LanguageRegistry().snapshot(caps)["python"]
    assert set(first["supported_operations"]) == {"migration", "audit", "compatibility"}
    caps["runtimes"][1]["verified"] = False
    assert LanguageRegistry().snapshot(caps)["python"]["supported_operations"] == ["audit"]
    caps["scanner"]["available"] = False
    assert LanguageRegistry().snapshot(caps)["python"]["supported_operations"] == []


def test_python_adapter_delegates_existing_analyzer_and_security(tmp_path, monkeypatch):
    (tmp_path / "module.py").write_text("VALUE=1")
    runner, evidence = object(), Evidence(); seen = []
    monkeypatch.setattr("backend.languages.python.VersionRegistry", lambda selected: SimpleNamespace(select=lambda version: {"image_id": "sha256:existing"}))
    def analyze(*args): seen.append(args); return {"modules": [], "python": [3, 12, 16]}
    monkeypatch.setattr("backend.languages.python.analyze_python", analyze)
    result = PythonAdapter().analyze(tmp_path, runner=runner, source_version="3.12", target_version="3.13", evidence=evidence)
    assert seen == [(runner, tmp_path, "sha256:existing", "3.12", "3.13")]
    assert result.language == "python" and result.verification.behavior_verified is None and evidence.verify()
    monkeypatch.setattr("backend.languages.python.scan", lambda *a: {"results": [], "errors": []})
    audit = PythonAdapter().security_findings(runner, tmp_path, evidence)
    assert audit.language == "python" and audit.findings == () and audit.limitations


def test_python_compatibility_delegates_with_identical_immutable_run_spec(tmp_path, monkeypatch):
    spec = RunSpec("compatibility", "existing", str(tmp_path), "3.12", "3.13", "offline", "compatibility", 5)
    run, settings, seen = SimpleNamespace(spec=spec), {"existing": "settings"}, []
    monkeypatch.setattr("backend.core.universal.execute", lambda *args: seen.append(args))
    PythonAdapter().compatibility(run, "id", tmp_path, settings)
    assert seen == [(run, "id", tmp_path, settings, "compatibility")] and run.spec is spec
    with pytest.raises(FrozenInstanceError): spec.source_version = "7.4"


def test_python_adapter_never_sends_php_to_bandit(tmp_path, monkeypatch):
    (tmp_path / "file.php").write_text("<?php echo 1;")
    monkeypatch.setattr("backend.languages.python.scan", lambda *a: pytest.fail("Bandit is not PHP"))
    with pytest.raises(AdapterError) as caught:
        PythonAdapter().security_findings(None, tmp_path, Evidence())
    assert caught.value.code == "language_mismatch"


def test_api_discovery_is_additive_and_php_requests_cannot_start(project, monkeypatch):
    php = project / "samples/php_project"; php.mkdir(); (php / "index.php").write_text("<?php function f() {}")
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.available", lambda self: False)
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run", lambda *a, **k: pytest.fail("Discovery/PHP preflight must not execute"))
    monkeypatch.setattr("backend.llm.client.OpenAI", lambda *a, **k: pytest.fail("No Meta"))
    with TestClient(create_app(project)) as client:
        caps = client.get("/api/v1/capabilities").json()
        assert caps["api_version"] == "1" and caps["operations"]["migration"]["pairs"] == [["2.7", "3.12"]]
        assert {r["version"] for r in caps["runtimes"]} == {"2.7", "3.8", "3.10", "3.12", "3.13", "3.14"}
        assert caps["languages"]["php"]["supported_operations"] == []
        resolved = client.post("/api/v1/projects/resolve", json={"relative_path": "samples/php_project"})
        assert resolved.status_code == 200 and resolved.json()["language"] == "php"
        project_id = resolved.json()["project_id"]
        data = client.get("/api/v1/projects").json()
        item = next(p for p in data["projects"] if p["project_id"] == project_id)
        assert item["available"] and not item["readiness"]["can_start"] and item["supported_operations"] == []
        assert item["available_profiles"] == {"cases": [], "fixture": []}
        assert item["source_version"] is item["target_version"] is None
        request = {"operation": "migration", "project_id": project_id, "execution_mode": "simulation"}
        blocked = client.post("/api/v1/runs/preflight", json=request)
        assert blocked.status_code == 200 and not blocked.json()["can_start"]
        assert blocked.json()["errors"][0]["code"] == "language_not_enabled"
        assert client.post("/api/v1/runs", json=request).status_code == 422
        legacy = client.post("/api/runs", json={"source_path": "samples/php_project"})
        assert legacy.status_code == 422 and set(legacy.json()["error"]) == {"code", "message"}
        assert not client.app.state.runs.runs


def test_php_single_file_resolution_mixed_projects_and_path_policy(project, monkeypatch):
    from backend.core.control_models import ControlError
    from backend.core.projects import ProjectCatalog
    php = project / "samples/one.php"; php.write_text("<?php function f() {}")
    catalog = ProjectCatalog(project)
    assert catalog.register("samples/one.php")["language"] == "php"
    with pytest.raises(ControlError) as caught: catalog.resolve("samples/one.php")
    assert caught.value.code == "language_not_enabled"
    (project / "samples/legacy_shop/mixed.php").write_text("<?php echo 1;")
    assert catalog.resolve("samples/legacy_shop").is_dir()  # Legacy Python scope is preserved.
    assert catalog.register("samples/legacy_shop")["language"] == "mixed"
    with pytest.raises(ControlError): catalog.register("../outside.php")


def test_existing_python_simulation_keeps_python_scope_in_mixed_project(project, monkeypatch):
    import time
    source = project / "samples/legacy_shop"
    php = source / "asset.php"; php.write_text("<?php throw new Exception('must not execute');")
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run", lambda *a, **k: pytest.fail("No PHP/Docker execution in simulation"))
    with TestClient(create_app(project, step_seconds=0.001)) as client:
        response = client.post("/api/runs", json={"source_path": "samples/legacy_shop"})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get("/api/runs/" + run_id).json()
            if state["status"] in {"done", "failed"}: break
            time.sleep(0.01)
        assert state["status"] == "done" and all(m["name"] != "asset" for m in state["modules"])
        report = client.get(f"/api/runs/{run_id}/report?format=json").json()
        assert report["simulation"] and state["hashes"]["unchanged"]
    assert php.read_text() == "<?php throw new Exception('must not execute');"
