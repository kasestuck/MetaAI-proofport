"""Real offline PHP orchestration. All project execution stays inside Docker."""

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from uuid import uuid4

from backend.core.evidence import Evidence
from backend.core.projects import copy_project, linked
from backend.languages.base import AdapterError
from backend.languages.php import analyze_php
from backend.php.fixtures import apply_candidate, load_manifest
from backend.php.fixes import verify_fixes
from backend.php.protocol import compare, load_cases
from backend.php.runtime import PHPExecutor, local_images, source_hashes
from backend.php.security import scan_php
from backend.php.verification import test_runner, verify
from backend.sandbox.runner import DockerRunner


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PHPJob:
    source: Path
    operation: str = "migration"
    source_version: str = "7.4"
    target_version: str | None = "8.3"
    cases: Path | None = None
    fixture: Path | None = None
    security_fixture: Path | None = None
    max_iterations: int = 5
    verification_level: str = "behavior"


def execute(job, *, runner=None, images=None, evidence=None, artifacts=None, progress=None):
    if job.operation not in {"migration", "compatibility", "audit"} or job.source_version not in {"7.4", "8.3"} or job.verification_level not in {"syntax", "tests", "behavior"} or type(job.max_iterations) is not int or not 1 <= job.max_iterations <= 5:
        raise ValueError("Unsupported PHP job")
    if job.operation == "migration" and (job.source_version, job.target_version) != ("7.4", "8.3"):
        raise ValueError("Only PHP 7.4 to 8.3 fixture migration is implemented")
    source = Path(job.source).absolute()  # inventory rejects link ancestors before resolution.
    before = source_hashes(source)
    artifacts = Path(artifacts) if artifacts else ROOT / "backend/.work" / ("php-run-" + uuid4().hex)
    artifacts = artifacts.absolute()
    if any(linked(p) for p in (artifacts, *artifacts.parents)): raise ValueError("Artifact paths cannot follow links/junctions")
    if artifacts == source or artifacts.is_relative_to(source) or source.is_relative_to(artifacts): raise ValueError("Separate project/artifact paths required")
    artifacts.mkdir(parents=True, exist_ok=False)
    evidence = evidence or Evidence(); evidence.bind(artifacts / "evidence.jsonl")
    data = {"language": "php", "mode": "php_" + job.operation, "execution_mode": "offline_fixtures" if job.operation == "migration" else "offline",
            "status": "failed", "model_calls": 0, "ai_migration": False, "source_version": job.source_version,
            "target_version": job.target_version, "isolation": "reduced", "iterations": [], "limitations": [],
            "syntax_passed": None, "tests_passed": None, "behavior_verified": None, "original_hashes": before,
            "artifact_id": artifacts.name, "migration_performed": False, "project_executed": False}
    phase = lambda value: progress(value) if progress else None
    evidence.append("run_started", "PHP offline verification; fixtures are authored candidates, not AI migration.")
    accepted, checks = None, None
    try:
        phase("analyzing")
        data["analysis"] = analyze_php(source, source_version=job.source_version, target_version=job.target_version, evidence=evidence).analysis
        original = artifacts / "original"; copy_project(source, original)
        if source_hashes(original) != before: raise ValueError("Original working-copy hash mismatch")
        if job.operation == "audit":
            phase("security"); data["security_audit"] = scan_php(original, evidence)
            accepted = original; data["status"] = "done"
        else:
            if job.target_version not in {"7.4", "8.3"}: raise ValueError("Unconfigured PHP target")
            runner = runner or DockerRunner(); images = images or local_images(runner)
            executor = PHPExecutor(runner=runner, images=images, evidence=evidence)
            data["isolation"] = "docker"; data["images"] = dict(images)
            data["source_syntax"] = executor.lint(original, job.source_version)
            if not data["source_syntax"]["passed"]: raise AdapterError("php_source_syntax_failed", "Original PHP syntax failed.")
            level = "behavior" if job.operation == "migration" else job.verification_level
            profile = load_cases(job.cases) if job.cases and level == "behavior" else None
            golden, baseline_tests = None, None
            if level in {"tests", "behavior"}:
                baseline_tests = executor.tests(original, job.source_version, test_runner=test_runner(original))
                data["source_tests"] = baseline_tests; data["project_executed"] = True
                if not baseline_tests["passed"]: raise AdapterError("php_source_tests_failed", "Original PHP tests failed.")
            if level == "behavior":
                if not profile: raise AdapterError("profile_unavailable", "Behavior verification requires server-bound PHP inputs.")
                phase("recording"); golden = executor.cases(original, job.source_version, profile)
                if not all(c["matches"] for c in compare(profile, golden, golden)): raise AdapterError("php_baseline_unverified", "Golden inputs did not exercise their declared outcomes.")
                (artifacts / "golden.json").write_text(json.dumps(golden, indent=2), encoding="utf-8")
                data["golden_case_count"] = len(golden)
                evidence.append("golden_recorded", "Actual PHP source outcomes recorded for %d explicit inputs." % len(golden))
                required = {(m["file"], ((m["namespaces"][0]["name"] + "\\") if m.get("namespaces") else "") + f["name"])
                            for m in data["analysis"]["modules"] if not m["is_test"] for f in m["functions"] if f["kind"] == "function"}
                covered = {(c["file"], c["call"]) for c in profile["cases"]}
                data["coverage"] = {"scope": "Recorded function inputs only; not branch coverage or universal equivalence.",
                                    "uncovered_functions": sorted([list(item) for item in required - covered])}
                if required - covered or data["analysis"]["diagnostics"]: raise AdapterError("insufficient_cases", "PHP function/lexical coverage is incomplete.")
            if job.operation == "migration":
                if not job.fixture: raise ValueError("Explicit PHP fixture manifest required")
                manifest = load_manifest(job.fixture, original)
                for iteration in range(job.max_iterations):
                    phase("migrating" if iteration == 0 else "fixing")
                    candidate = artifacts / ("migration_%02d" % (iteration + 1)); copy_project(original, candidate)
                    apply_candidate(manifest, candidate, iteration)
                    evidence.append("patch_applied", "Authored PHP fixture candidate %d staged; not yet accepted." % (iteration + 1))
                    phase("testing"); checks = verify(executor, candidate, job.target_version, profile=profile, golden=golden, baseline_tests=baseline_tests)
                    data["iterations"].append({"iteration": iteration + 1, "mode": "fixture", "checks": checks})
                    evidence.append("test_result", json.dumps({"language": "php", "iteration": iteration + 1, "passed": bool(checks["passed"])}))
                    if checks["passed"]: accepted = candidate; break
                if accepted is None: raise AdapterError("php_verification_failed", "No PHP fixture candidate passed all requested checks.")
                data["migration_performed"] = True
                phase("security"); data["security_before"] = scan_php(original, evidence)
                data["security_after"] = scan_php(accepted, evidence)
                if job.security_fixture:
                    sec = artifacts / "security"; sec.mkdir()
                    accepted, details, fixed_checks = verify_fixes(working=accepted, original=source, original_hashes=before,
                        artifacts=sec, profile=profile, golden=golden, baseline_tests=baseline_tests, executor=executor, evidence=evidence, proposals_file=job.security_fixture)
                    data["security_fix"] = details
                    if fixed_checks: checks = fixed_checks
                    data["security_after"] = scan_php(accepted, evidence)
            else:
                phase("testing"); accepted = original
                checks = verify(executor, original, job.target_version, profile=profile, golden=golden, baseline_tests=baseline_tests, level=level)
                if not checks["passed"]: raise AdapterError("php_verification_failed", "Requested PHP compatibility checks failed.")
            data.update(syntax_passed=checks["syntax"]["passed"], tests_passed=checks["existing_tests"]["passed"],
                        behavior_verified=checks["golden"]["passed"], target_tests=checks["existing_tests"] if checks["existing_tests"]["ran"] else None,
                        comparisons=checks["golden"].get("comparisons", []), accepted_hashes=source_hashes(accepted))
            data["status"] = "done"
        if accepted: data["accepted_copy"] = accepted.relative_to(artifacts).as_posix()
        data["limitations"].extend(["Offline fixtures are not AI migration or AI remediation.",
                                    "Only recorded inputs/tests are checked; no universal equivalence or complete security coverage."])
    except Exception as exc:
        data["status"] = "failed"
        data["error"] = {"code": getattr(exc, "code", "php_verification_failed"),
                         "message": str(exc) if isinstance(exc, AdapterError) else "PHP workflow failed: " + type(exc).__name__ + "; inspect retained stage artifacts."}
        evidence.append("error", data["error"]["message"])
        if checks:
            data.update(syntax_passed=checks["syntax"]["passed"], tests_passed=checks["existing_tests"]["passed"], behavior_verified=checks["golden"]["passed"],
                        comparisons=checks["golden"].get("comparisons", []))
    finally:
        phase("reporting")
        try: data["originals_unchanged"] = source_hashes(source) == before
        except (OSError, ValueError, AdapterError): data["originals_unchanged"] = False
        if not data["originals_unchanged"]:
            data.update(status="failed", error={"code": "source_changed", "message": "PHP original source hash changed."})
        evidence.append("run_finished", "PHP offline status=%s; no model calls." % data["status"])
        data["chain_intact"] = evidence.verify()
        if not data["chain_intact"]: data.update(status="failed", error={"code": "evidence_corrupted", "message": "PHP evidence integrity failed."})
        exported = {**data, "events": evidence.since(0)}
        (artifacts / "report.json").write_text(json.dumps(exported, indent=2), encoding="utf-8")
        (artifacts / "report.html").write_text('<!doctype html><meta charset="utf-8"><title>Proofport offline PHP report</title><h1>Offline PHP verification; not AI</h1><pre>' + escape(json.dumps(exported, indent=2)) + '</pre>', encoding="utf-8")
    return data, artifacts
