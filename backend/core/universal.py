"""Offline analysis, audit-only and selected-runtime compatibility evidence."""

import json
from pathlib import Path
import shutil
from time import monotonic

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from backend.core.analyzer import analyze_python
from backend.core.comparator import compare_cases
from backend.core.detection import detect
from backend.core.models import Error, Module
from backend.core.recorder import invoke, load_cases
from backend.core.security import findings_for, scan
from backend.core.versions import VersionError, VersionRegistry


def _path(root, value):
    path = Path(value)
    return path if path.is_absolute() else root / path


def _copy(source, destination):
    from backend.core.projects import copy_project
    copy_project(source, destination)


def _level(checks):
    if checks["behavior_verified"] is True and checks["tests_passed"] is not False:
        return "behavior_verified"
    if checks["tests_passed"] is True:
        return "tests_passed"
    if checks["syntax_compatible"] is True:
        return "syntax_compatible"
    return "not_verified"


def execute(run, run_id, root, settings, mode):
    from backend.core.runs import hashes_for
    state = run.state
    state.status = "running"
    run.execution_mode = mode
    details = run.verification
    checks = {"syntax_compatible": None, "tests_passed": None, "behavior_verified": None, "level": "not_verified"}
    details.update(mode=mode, model_calls=0, model=None, ai_migration=False, project_executed=False,
                   compatibility=checks, limitations=[
                       "Static analysis and completed audit tasks do not prove project compatibility.",
                       "Dependencies were not installed or resolved; missing dependencies can prevent execution.",
                       "Behavior verification is limited to supplied positive golden cases and covered modules.",
                       "Only unittest discovery under tests/ is supported; other test frameworks are not inferred.",
                   ])
    terminal = "failed"
    try:
        workspace = root / "backend/.work" / run_id
        if workspace.resolve().is_relative_to(run.source.resolve()) or run.source.resolve().is_relative_to((root / "backend/.work").resolve()):
            raise ValueError("Select a source outside the artifact workspace ancestry.")
        workspace.mkdir(parents=True, exist_ok=False)
        run.workspace = workspace
        run.evidence.bind(workspace / "evidence.log")
        project = workspace / "copy"
        _copy(run.source, project)
        copied = {name.split("/", 1)[1]: value for name, value in hashes_for(project).items()}
        expected = ({name.split("/", 1)[1]: value for name, value in run.originals.items()}
                    if run.source.is_dir() else run.originals)
        if copied != expected:
            raise VersionError("Working copy does not match the recorded original snapshot.", "source_snapshot_mismatch")
        (workspace / "original_hashes.json").write_text(json.dumps(run.originals, indent=2), encoding="utf-8")
        declared = settings.get("PROOFPORT_SOURCE_VERSION") or None
        detection = detect(run.source, declared)
        details["version_detection"] = detection
        if detection["status"] == "conflict":
            raise VersionError("Declared source version conflicts with syntax/project metadata.", "source_version_conflict")
        if not run.runner.available():
            raise VersionError("Linux Docker is unavailable; no host execution fallback.", "docker_unavailable")
        registry = VersionRegistry(run.runner, root / "backend/.work/runtime_registry.json")
        target = settings.get("PROOFPORT_TARGET_VERSION") if mode == "compatibility" else None
        if mode == "compatibility" and not target:
            raise VersionError("Select PROOFPORT_TARGET_VERSION for compatibility verification.")
        source_version = declared
        if not source_version and len(detection["possible_versions"]) == 1:
            source_version = detection["possible_versions"][0]
        if mode != "compatibility" and not source_version:
            raise VersionError("Source version is ambiguous; explicitly select PROOFPORT_SOURCE_VERSION.", "source_version_ambiguous")
        analysis_version = source_version or target
        for version in sorted(set(value for value in (analysis_version, target) if value)):
            VersionRegistry.configured(version)
            if settings.get("PROOFPORT_VERIFY_RUNTIME") == "1" and not registry.inspect(version)["verified"]:
                registry.verify(version, run.evidence)
        selected = registry.select(analysis_version, "source")
        selected_target = registry.select(target, "target") if target else None
        if run.spec and run.spec.images:
            pins = dict(run.spec.images)
            if any(item["image_id"] != pins.get(item["image"]) for item in (selected, selected_target) if item):
                raise VersionError("Selected runtime changed after preflight.", "runtime_changed")
        details.update(registry=registry.snapshot(), source_version=source_version, analysis_interpreter=analysis_version,
                       target_version=target, migration_performed=False)
        state.isolation = "docker"
        analysis = analyze_python(run.runner, project, selected["image_id"], analysis_version, target)
        details["analysis"] = analysis
        details["docker_analysis_performed"] = True
        run.evidence.append("sandbox_run", "Actual static analyzer in Docker Python " + analysis_version + "; no target imports.")
        state.modules = [Module(name=module["name"], tests_total=0) for module in analysis["modules"] if not module["is_test"]]
        if analysis.get("errors"):
            details["limitations"].append("Source analysis is incomplete under the selected grammar.")
        if source_version and detection["python_requires"]:
            try:
                if not SpecifierSet(",".join(detection["python_requires"])).contains(".".join(map(str, analysis["python"])), prereleases=True):
                    raise VersionError("Actual source patch version is excluded by project Python requirements.", "source_metadata_conflict")
            except InvalidSpecifier:
                details["limitations"].append("Some metadata constraints could not be validated.")
        if mode == "audit":
            state.phase = "security"
            result = scan(run.runner, project, run.evidence)
            state.security.findings, details["security_details"] = findings_for(result)
            state.security.before = state.security.after = len(result["results"])
            details["security_audit"] = {"scan": result, "coverage": "partial" if result["errors"] else "parsed_files_only",
                                          "scanner_python": "3.12", "project_executed": False, "fixes_applied": False}
            if result["errors"]:
                details["limitations"].append("Bandit 1.8.6 on Python 3.12 skipped files it could not parse; no full coverage or safety claim.")
            for finding in state.security.findings:
                run.evidence.append("security_finding", finding.note, finding.file)
        elif mode == "compatibility":
            result = invoke(run.runner, selected_target["image_id"], project, "compile", evidence=run.evidence, version=target)
            checks["syntax_compatible"] = not result["errors"]
            checks["syntax"] = result
            if not checks["syntax_compatible"]:
                raise VersionError("Source syntax failed on the selected target interpreter.", "target_syntax_incompatible")
            if detection["python_requires"]:
                try:
                    checks["target_metadata_compatible"] = SpecifierSet(",".join(detection["python_requires"])).contains(".".join(map(str, result["python"])), prereleases=True)
                    if not checks["target_metadata_compatible"]:
                        raise VersionError("Project Python requirements exclude the actual target runtime; metadata/dependencies need review.", "target_metadata_conflict")
                except InvalidSpecifier:
                    checks["target_metadata_compatible"] = None
                    details["limitations"].append("Target Python metadata constraints could not be interpreted.")
            if settings.get("PROOFPORT_VERIFICATION_LEVEL") != "syntax" and (project / "tests").is_dir():
                tests = invoke(run.runner, selected_target["image_id"], project, "tests", evidence=run.evidence, version=target)
                details["project_executed"] = True
                ids = [test["id"] for test in tests["outcomes"]]
                checks["existing_tests"] = tests
                if tests["tests_run"]:
                    checks["tests_passed"] = tests["tests_run"] == len(ids) == len(set(ids)) and all(test["status"] == "passed" for test in tests["outcomes"])
                    state.metrics.tests_total += tests["tests_run"]
                    state.metrics.tests_passed += sum(test["status"] == "passed" for test in tests["outcomes"])
            if checks["tests_passed"] is None:
                details["limitations"].append("No nonempty supported existing test suite was verified.")
                if settings.get("PROOFPORT_REQUIRED_TESTS") == "1":
                    raise VersionError("Requested existing test verification produced no nonempty suite.", "tests_unavailable")
            case_path = settings.get("PROOFPORT_CASES_FILE")
            if case_path:
                if not source_version:
                    raise VersionError("Golden recording requires an explicit/unambiguous source version.", "source_version_ambiguous")
                cases = load_cases(_path(root, case_path))
                baseline = invoke(run.runner, selected["image_id"], project, "cases", cases, run.evidence, version=source_version)["cases"]
                observed = invoke(run.runner, selected_target["image_id"], project, "cases", cases, run.evidence, version=target)["cases"]
                details["project_executed"] = True
                comparisons = compare_cases(baseline, observed)
                covered = {case["module"] for case, recorded in zip(cases, baseline)
                           for step, outcome in zip(case["steps"], recorded["steps"])
                           if "value" in outcome and str(step.get("call", step.get("attribute", ""))).startswith(case["module"] + ".")}
                known = {module.name for module in state.modules}
                complete = bool(known) and not analysis.get("errors") and known <= covered and covered <= known
                checks.update(recorded_cases_match=all(case["matches"] for case in comparisons), comparisons=comparisons,
                              covered_modules=sorted(covered), uncovered_modules=sorted(known - covered))
                checks["behavior_verified"] = all(case["matches"] for case in comparisons) if complete else None
                state.metrics.tests_total += len(comparisons)
                state.metrics.tests_passed += sum(case["matches"] for case in comparisons)
                (workspace / "golden.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")
                if not complete:
                    details["limitations"].append("Golden coverage is incomplete or only errors were recorded; full-project behavior is not verified.")
                for module in state.modules:
                    results = [case for case in comparisons if case["module"] == module.name]
                    module.tests_total = len(results)
                    module.tests_passed = sum(case["matches"] for case in results)
                if not all(case["matches"] for case in comparisons):
                    raise VersionError("Recorded behavior differs on the selected target.", "behavior_mismatch")
            if checks["tests_passed"] is False:
                raise VersionError("Existing tests failed on the selected target.", "target_tests_failed")
            if checks["behavior_verified"] is True:
                for module in state.modules:
                    module.status = "green"
            if settings.get("PROOFPORT_VERIFICATION_LEVEL") == "behavior" and checks["behavior_verified"] is not True:
                raise VersionError("Requested behavior verification lacks complete positive module coverage.", "insufficient_cases")
        terminal = "done"
    except Exception as exc:
        state.error = Error(code=getattr(exc, "code", "verification_unavailable"),
                            message=str(exc) if isinstance(exc, VersionError) else "Offline workflow failed: " + type(exc).__name__)
        run.evidence.append("error", state.error.message)
    finally:
        checks["level"] = _level(checks)
        if run.runner.cancelled.is_set():
            terminal = "failed"
            state.error = Error(code="run_interrupted", message="Offline verification was cancelled.")
        try:
            state.hashes["unchanged"] = hashes_for(run.source) == run.originals
        except OSError:
            state.hashes["unchanged"] = False
        if not state.hashes["unchanged"]:
            terminal = "failed"
            state.error = Error(code="source_changed", message="Original hashes changed or could not be rechecked.")
        state.phase = "reporting"
        state.metrics.seconds = round(monotonic() - run.started, 3)
        run.evidence.append("run_finished", f"Offline {mode} status={terminal}; compatibility level={checks['level']}; no migration or model calls.")
        state.chain_intact = run.evidence.verify()
        if not state.chain_intact:
            terminal = "failed"
            state.error = Error(code="evidence_corrupted", message="Persisted evidence integrity failed.")
        if terminal == "failed":
            for module in state.modules:
                module.status = "failed"
        run.pending_status = terminal
