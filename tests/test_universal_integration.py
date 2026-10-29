import asyncio
import json
from pathlib import Path
import shutil
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.analyzer import analyze_python
from backend.core.report import report_data
from backend.core.runs import RunStore, hashes_for
from backend.core.versions import VersionError, VersionRegistry
from backend.sandbox.runner import DockerRunner


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "tests/fixtures/universal_py3"


@pytest.fixture(autouse=True)
def no_model_requests(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("P3 must not construct an SDK or spend API credits")
    monkeypatch.setattr("backend.llm.client.OpenAI", forbidden)
    monkeypatch.setattr("backend.llm.client.LLMClient.complete", forbidden)


@pytest.fixture(scope="module")
def runtimes(tmp_path_factory):
    runner = DockerRunner()
    assert runner.available(), "Enabled integration tests require real Linux Docker"
    registry = VersionRegistry(runner, tmp_path_factory.mktemp("registry") / "runtimes.json")
    for version in ("2.7", "3.12", "3.13"):
        result = registry.verify(version)  # Actual analyzer + compile + two tests + two cases.
        assert result["available"] and result["verified"]
    return registry


def configure_root(root, runtimes):
    destination = root / "backend/.work/runtime_registry.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(runtimes.path.read_text(), encoding="utf-8")


def workflow(root, runtimes, source, mode="compatibility", **settings):
    configure_root(root, runtimes)
    settings = {"PROOFPORT_SOURCE_VERSION": "3.12", "PROOFPORT_TARGET_VERSION": "3.13", **settings}
    async def execute():
        store = RunStore(root, pipeline=mode, settings=settings)
        run_id = store.start(str(source), 1)
        await asyncio.gather(*list(store.tasks))
        run = store.get(run_id)
        assert store.active is None
        assert run.evidence.verify()
        assert run.state.hashes["unchanged"] is True
        assert run.state.metrics.cost_usd == run.state.metrics.tokens_in == run.state.metrics.tokens_out == 0
        if run.workspace:
            persisted = json.loads((run.workspace / "report.json").read_text())
            assert persisted["state"]["status"] == run.state.status
        return run, report_data(run)
    return asyncio.run(execute())


def test_real_runtime_receipts_and_image_binding(runtimes):
    for version in ("2.7", "3.12", "3.13"):
        selected = runtimes.select(version)
        receipt = runtimes.receipts[version]
        assert selected["verified"]
        assert receipt["python"][:2] == list(map(int, version.split(".")))
        assert receipt["tests_run"] == receipt["cases_run"] == 2
        assert all(receipt["checks"].values())
        image = receipt["image_id"]
        receipt["image_id"] = "sha256:" + "0" * 64
        assert not runtimes.inspect(version)["verified"]
        receipt["image_id"] = image
        assert runtimes.inspect(version)["verified"]
    assert all(not runtimes.inspect(version)["verified"] for version in ("3.8", "3.10", "3.14"))


def test_python3_analyzer_functions_classes_relative_imports_cycles_and_obsolete(tmp_path, runtimes):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "util.py").write_text('def value(x, /, *, default=1):\n    return x or default\n')
    (package / "main.py").write_text('from .util import value\nimport imp\nasync def task(x):\n    return x\nclass Service:\n    def run(self):\n        return value(2)\ndef old(d):\n    return d.iteritems()\nraise RuntimeError("never import static analysis")\n')
    selected = runtimes.select("3.12")
    analysis = analyze_python(DockerRunner(), tmp_path, selected["image_id"], "3.12", "3.13")
    main = next(module for module in analysis["modules"] if module["name"] == "pkg.main")
    assert main["functions"][0]["async"]
    assert main["classes"][0]["methods"][0]["name"] == "run"
    assert "pkg.util" in analysis["graph"]["pkg.main"]
    order = [module["name"] for module in analysis["order"]]
    assert order.index("pkg.util") < order.index("pkg.main")
    assert {item["kind"] for item in main["deprecated"]} == {"stdlib_review", "legacy_attribute"}
    assert not analysis["project_executed"] and not analysis["migration_plan"]["migration_performed"]
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("import a\n")
    cycle = analyze_python(DockerRunner(), tmp_path, selected["image_id"], "3.12")
    assert cycle["cyclic_or_blocked"] == ["a", "b"]


def test_real_python312_to313_behavior_verification_and_reports(tmp_path, runtimes):
    original = hashes_for(SUBJECT)
    run, report = workflow(tmp_path, runtimes, SUBJECT, PROOFPORT_CASES_FILE=str(SUBJECT / "cases.json"))
    checks = report["verification"]["compatibility"]
    assert run.state.status == "done", report
    assert checks["level"] == "behavior_verified"
    assert checks["syntax_compatible"] and checks["tests_passed"] and checks["behavior_verified"]
    assert len(checks["comparisons"]) == 2 and all(case["matches"] for case in checks["comparisons"])
    assert checks["existing_tests"]["python"][:2] == [3, 13]
    assert run.state.metrics.tests_passed == run.state.metrics.tests_total == 4
    assert all(module.status == "green" for module in run.state.modules)
    assert not report["verification"]["migration_performed"] and report["verification"]["model_calls"] == 0
    assert (run.workspace / "golden.json").is_file()
    assert "behavior_verified" in (run.workspace / "report.html").read_text()
    assert "status=done" in json.loads((run.workspace / "report.json").read_text())["notice"]
    assert hashes_for(SUBJECT) == original


def test_tests_passed_does_not_claim_behavior_verification(tmp_path, runtimes):
    run, report = workflow(tmp_path, runtimes, SUBJECT)
    checks = report["verification"]["compatibility"]
    assert run.state.status == "done"
    assert checks["level"] == "tests_passed" and checks["behavior_verified"] is None
    assert all(module.status == "pending" for module in run.state.modules)


def test_single_file_syntax_only_never_imports_or_claims_tests(tmp_path, runtimes):
    source = tmp_path / "standalone.py"
    source.write_text('def add(a, b):\n    return a + b\nraise RuntimeError("never execute compile")\n')
    run, report = workflow(tmp_path, runtimes, source)
    checks = report["verification"]["compatibility"]
    assert run.state.status == "done", report
    assert checks["level"] == "syntax_compatible"
    assert checks["tests_passed"] is checks["behavior_verified"] is None
    assert run.state.metrics.tests_total == 0
    assert report["verification"]["project_executed"] is False
    assert all(module.status == "pending" for module in run.state.modules)


def test_source313_grammar_is_analyzed_by313_and_rejected_by312(tmp_path, runtimes):
    source = ROOT / "tests/fixtures/universal_py313/modern.py"
    run, report = workflow(tmp_path / "analyze", runtimes, source, "analyze", PROOFPORT_SOURCE_VERSION="3.13")
    assert run.state.status == "done", report
    assert report["verification"]["analysis"]["python"][:2] == [3, 13]
    assert report["verification"]["analysis"]["modules"][0]["functions"][0]["name"] == "identity"
    failed, data = workflow(tmp_path / "check", runtimes, source, PROOFPORT_SOURCE_VERSION="3.13", PROOFPORT_TARGET_VERSION="3.12")
    assert failed.state.status == "failed"
    assert failed.state.error.code == "target_syntax_incompatible"
    assert data["verification"]["compatibility"]["level"] == "not_verified"


def test_existing_test_failure_is_reported_as_failure(tmp_path, runtimes):
    source = tmp_path / "project"
    shutil.copytree(SUBJECT, source)
    path = source / "numbers_demo.py"
    path.write_text(path.read_text().replace("return a + b", "return 0"))
    run, report = workflow(tmp_path, runtimes, source)
    assert run.state.status == "failed"
    assert run.state.error.code == "target_tests_failed"
    assert report["verification"]["compatibility"]["tests_passed"] is False
    assert run.state.metrics.tests_passed == 1 and run.state.metrics.tests_total == 2


def test_behavior_mismatch_between_actual_runtimes_is_not_success(tmp_path, runtimes):
    source = tmp_path / "version_sensitive.py"
    source.write_text('import sys\ndef runtime():\n    return sys.version_info.minor\n')
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps({"cases": [{"id": "runtime", "module": "version_sensitive", "steps": [{"call": "version_sensitive.runtime"}]}]}))
    run, data = workflow(tmp_path, runtimes, source, PROOFPORT_CASES_FILE=str(cases))
    assert run.state.status == "failed" and run.state.error.code == "behavior_mismatch"
    assert data["verification"]["compatibility"]["behavior_verified"] is False
    assert not data["verification"]["compatibility"]["comparisons"][0]["matches"]


def test_partial_golden_coverage_does_not_verify_project(tmp_path, runtimes):
    source = tmp_path / "project"
    shutil.copytree(SUBJECT, source)
    (source / "uncovered.py").write_text('def extra():\n    return "not exercised"\n')
    run, data = workflow(tmp_path, runtimes, source, PROOFPORT_CASES_FILE=str(source / "cases.json"))
    assert run.state.status == "done"
    checks = data["verification"]["compatibility"]
    assert checks["recorded_cases_match"] is True
    assert checks["behavior_verified"] is None and checks["uncovered_modules"] == ["uncovered"]
    assert checks["level"] == "tests_passed"


@pytest.mark.parametrize("version,code", [("3.9", "unsupported_python_version"), ("3.14", "runtime_unavailable")])
def test_unsupported_or_missing_target_fails_without_pull(tmp_path, runtimes, version, code):
    if version == "3.14" and runtimes.inspect(version)["available"]:
        code = "unverified_version"
    run, data = workflow(tmp_path, runtimes, SUBJECT, PROOFPORT_TARGET_VERSION=version)
    assert run.state.status == "failed" and run.state.error.code == code
    assert data["verification"]["compatibility"]["level"] == "not_verified"


def test_audit_api_preserves_contract_no_execution_no_model_no_changes(tmp_path, runtimes, monkeypatch):
    source = tmp_path / "audit_me.py"
    source.write_text('def evaluate(value):\n    return eval(value)\nraise RuntimeError("audit must never import this")\n')
    before = hashes_for(source)
    configure_root(tmp_path, runtimes)
    monkeypatch.setenv("PROOFPORT_PIPELINE", "audit")
    monkeypatch.setenv("PROOFPORT_SOURCE_VERSION", "3.12")
    monkeypatch.setenv("LLM_MODE", "live")  # Offline mode must ignore even configured live credentials.
    monkeypatch.setenv("MODEL_API_KEY", "unit-test-not-a-real-key")
    monkeypatch.setenv("MODEL_NAME", "do-not-call")
    with TestClient(create_app(tmp_path)) as client:
        response = client.post("/api/runs", json={"source_path": str(source)})
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 60
        while client.app.state.runs.active is not None and time.monotonic() < deadline:
            time.sleep(0.05)
        state = client.get(f"/api/runs/{run_id}").json()
        assert state["status"] == "done", state
        assert set(state) == {"status", "phase", "isolation", "modules", "security", "hashes", "metrics", "chain_intact"}
        assert state["security"]["before"] == state["security"]["after"] == 1
        assert state["security"]["findings"][0]["status"] == "open"
        data = client.get(f"/api/runs/{run_id}/report?format=json").json()
        assert data["verification"]["security_details"][0]["scanner_test"] == "B307"
        assert data["verification"]["security_audit"]["coverage"] == "parsed_files_only"
        assert not data["verification"]["project_executed"]
        assert data["verification"]["model_calls"] == 0
        assert data["verification"]["compatibility"]["level"] == "not_verified"
        assert "potential risks" in client.get(f"/api/runs/{run_id}/report?format=html").text
        assert all(event["seq"] > 2 for event in client.get(f"/api/runs/{run_id}/events?since=2").json())
    assert hashes_for(source) == before


def test_audit313_reports_bandit_parser_limit_instead_of_clean_security(tmp_path, runtimes):
    source = ROOT / "tests/fixtures/universal_py313/modern.py"
    run, data = workflow(tmp_path, runtimes, source, "audit", PROOFPORT_SOURCE_VERSION="3.13")
    assert run.state.status == "done", data
    audit = data["verification"]["security_audit"]
    assert audit["coverage"] == "partial" and audit["scan"]["errors"]
    assert any("skipped files" in limitation for limitation in data["verification"]["limitations"])


def test_actual_patch_constraints_are_checked_before_project_execution(tmp_path, runtimes):
    source = tmp_path / "project"
    source.mkdir()
    (source / "module.py").write_text('raise RuntimeError("must not execute")\n')
    (source / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12.999,<3.13"\n')
    run, data = workflow(tmp_path, runtimes, source)
    assert run.state.status == "failed" and run.state.error.code == "source_metadata_conflict"
    assert not data["verification"]["project_executed"]


def test_target_metadata_conflict_is_not_supported_compatibility(tmp_path, runtimes):
    source = tmp_path / "project"
    shutil.copytree(SUBJECT, source)
    (source / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12,<3.13"\n')
    run, data = workflow(tmp_path, runtimes, source)
    assert run.state.status == "failed" and run.state.error.code == "target_metadata_conflict"
    assert data["verification"]["compatibility"]["target_metadata_compatible"] is False
    assert not data["verification"]["project_executed"]


def test_corrupted_working_copy_is_rejected_before_execution(tmp_path, runtimes, monkeypatch):
    from backend.core import universal
    original_copy = universal._copy
    def corrupted_copy(source, destination):
        original_copy(source, destination)
        (destination / "numbers_demo.py").write_text('raise RuntimeError("tampered copy")\n')
    monkeypatch.setattr(universal, "_copy", corrupted_copy)
    before = hashes_for(SUBJECT)
    run, data = workflow(tmp_path, runtimes, SUBJECT)
    assert run.state.status == "failed" and run.state.error.code == "source_snapshot_mismatch"
    assert not data["verification"]["project_executed"]
    assert hashes_for(SUBJECT) == before
