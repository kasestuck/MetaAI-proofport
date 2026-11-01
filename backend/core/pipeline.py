"""Real Docker analysis, recording, migration candidates, verification and scan."""

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
from time import monotonic

from backend.core.analyzer import analyze
from backend.core.comparator import compare_cases
from backend.core.models import Error, Module
from backend.core.recorder import invoke, load_cases
from backend.core.security import SCANNER_IMAGE, findings_for, scan
from backend.core.translator import FixtureTranslator, LiveTranslator
from backend.core.workspace import prepare
from backend.llm.client import ModelUnavailable
from backend.sandbox.runner import SandboxError


class PipelineFailure(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _write(path: Path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _setting_path(root, settings, key):
    value = settings.get(key)
    if not value:
        raise PipelineFailure("verification_unavailable", f"Configure {key}; verification cannot use invented inputs or candidates.")
    path = Path(value)
    return path if path.is_absolute() else root / path


def _rollback_model(run, workspace, original, migrated, verified):
    if migrated is None or not migrated.exists() or run.verification.get("rollback"): return
    if migrated.parent != workspace or original.parent != workspace: raise RuntimeError("Unsafe rollback workspace")
    rejected = workspace / "model_rejected_final"
    migrated.rename(rejected)  # Retain bytes; do not delete or touch originals.
    shutil.copytree(verified or original, migrated)
    run.verification["rollback"] = {"performed":True, "retained":rejected.name, "restored":"verified_translation" if verified else "copy"}
    run.evidence.append("fix_reverted", "Unsuccessful model candidate retained; copied project restored to the last verified baseline.")


def execute(run, run_id, root, settings, mode, *, translator=None, security_generator=None):
    from backend.core.runs import hashes_for

    runner = run.runner
    state = run.state
    model_path = translator is not None
    workspace = original = migrated = verified_baseline = None
    model_calls_recorded = 0
    state.status = "running"
    terminal = "failed"
    try:
        if model_path:
            from backend.ai.provider import StructuredTranslator
            if not isinstance(translator, StructuredTranslator) or mode != translator.mode or translator.client.mode not in {"mock", "replay"}:
                raise ModelUnavailable("Explicit offline structured translator required; live is disabled.", "live_disabled")
            if security_generator and security_generator.session is not translator.session:
                raise ModelUnavailable("Migration/security must share one bounded model session.", "budget_required")
        if settings.get("PROOFPORT_SECURITY_FIXTURES") and mode != "fixtures":
            raise PipelineFailure("offline_only", "Security fixture verification cannot invoke live or replay model generation.")
        if not runner.available():
            raise PipelineFailure("docker_unavailable", "Linux Docker is unavailable; host execution is forbidden.")
        for image in ("python:2.7", "python:3.12-slim", SCANNER_IMAGE):
            runner.image_id(image)
        workspace = root / "backend" / ".work" / run_id
        original, migrated = prepare(run.source, workspace)
        run.workspace = workspace
        run.evidence.bind(workspace / "evidence.log")
        _write(workspace / "original_hashes.json", run.originals)
        if hashes_for(run.source) != run.originals:
            raise PipelineFailure("source_changed", "Original sources changed before recording.")
        copied = {f"{run.source.name}/{path.relative_to(original).as_posix()}": sha256(path.read_bytes()).hexdigest()
                  for path in original.rglob("*") if path.is_file()}
        if copied != run.originals:
            raise PipelineFailure("source_changed", "Working copy hashes do not match the original snapshot.")
        run.execution_mode = mode
        state.isolation = "docker"
        run.evidence.append("run_started", f"REAL Docker verification; translation provider={mode}. Fixtures are not AI migration.")
        analysis = analyze(runner, original)
        run.verification.update(
            mode=mode, ai_migration=False, source_python=analysis["python"],
            images=dict(runner._images), analysis=analysis,
            limitations=[
                "Finite, explicitly supplied cases and existing tests do not prove every possible behavior.",
                "Only Python 2.7 to Python 3.12 is exercised; no universal-version support is claimed.",
                "No automatic security fixes were attempted. A clean scan would not prove complete security.",
                "Fixture compatibility patches (including eval and CSV error formatting) cover the recorded inputs, not arbitrary programs.",
            ],
        )
        _write(workspace / "analysis.json", analysis)
        state.modules = [Module(name=module["name"], tests_total=0) for module in analysis["order"]]
        cases = load_cases(_setting_path(root, settings, "PROOFPORT_CASES_FILE"))
        known = {module.name for module in state.modules}
        if any(case["module"] not in known for case in cases):
            raise PipelineFailure("invalid_cases", "Golden inputs reference modules absent from the analyzed project.")
        state.phase = "recording"
        golden = invoke(runner, "python:2.7", original, "cases", cases, run.evidence)["cases"]
        legacy_tests = invoke(runner, "python:2.7", original, "tests", evidence=run.evidence)
        outcomes = legacy_tests["outcomes"]
        if (not legacy_tests["tests_run"] or len(outcomes) != legacy_tests["tests_run"]
                or len({test["id"] for test in outcomes}) != len(outcomes)
                or any(test["status"] != "passed" for test in outcomes)):
            raise PipelineFailure("legacy_tests_failed", "The original test suite is empty or not fully passing.")
        run.verification.update(golden_case_count=len(golden), legacy_tests=legacy_tests)
        _write(workspace / "golden.json", golden)
        _write(workspace / "legacy_tests.json", legacy_tests)
        run.evidence.append("golden_recorded", f"Recorded {len(golden)} real Python 2.7 cases and {legacy_tests['tests_run']} passing existing tests.")
        for module in state.modules:
            module.tests_total = sum(case["module"] == module.name for case in cases)
        exercised = {case["module"] for case, observed in zip(cases, golden)
                     for step, outcome in zip(case["steps"], observed["steps"])
                     if "value" in outcome and str(step.get("call", step.get("attribute", ""))).startswith(case["module"] + ".")}
        if any(not module.tests_total for module in state.modules):
            raise PipelineFailure("insufficient_cases", "At least one module has no golden coverage; it cannot be marked green.")
        if not known <= exercised:
            raise PipelineFailure("insufficient_cases", "Each module requires at least one successful directly exercised behavior, not only errors or empty steps.")
        state.metrics.tests_total = len(golden) + legacy_tests["tests_run"]
        state.phase = "security"
        before = scan(runner, original, run.evidence)
        run.verification["security_before"] = before
        _write(workspace / "security_before.json", before)
        state.security.before = len(before["results"])
        state.security.after = state.security.before
        state.security.findings, run.verification["security_details"] = findings_for(before)
        if before["errors"]:
            run.verification["limitations"].append(f"Bandit could not parse {len(before['errors'])} Python 2 source files; original scan coverage is partial.")
        if model_path:
            run.verification["limitations"] = [note for note in run.verification["limitations"] if not note.startswith("Fixture compatibility patches")]
            run.verification["limitations"].append("Mock/replayed structured model responses are not a real AI migration; no Meta request was made.")
        elif mode == "fixtures":
            translator = FixtureTranslator(_setting_path(root, settings, "PROOFPORT_FIXTURE_FILE"))
        else:
            raise ModelUnavailable("Live Meta AI is disabled pending separate authorization. No model request was made.")
        run.verification["model"] = None  # Offline configurations never certify a provider/model.
        modules = {module.name: module for module in state.modules}
        by_file = {module["file"]: module for module in analysis["order"]}
        feedback = {}
        to_fix = set(by_file)
        compiled = False
        success = False
        for iteration in range(1, run.max_iterations + 1):
            if runner.cancelled.is_set():
                raise PipelineFailure("run_interrupted", "Run was cancelled.")
            state.phase = "migrating"
            for module in state.modules:
                module.status = "pending"
                module.tests_passed = 0
            state.metrics.tests_passed = state.metrics.lines_migrated = 0
            patch_errors = []
            for relative, analyzed in by_file.items():
                if relative not in to_fix:
                    continue
                module = modules[analyzed["name"]]
                module.status = "translating" if not module.iterations else "fixing"
                module.iterations += 1
                original_text = (original / relative).read_text(encoding="utf-8")
                previous = (migrated / relative).read_text(encoding="utf-8")
                try:
                    code = translator.translate(relative, original_text, previous if iteration > 1 else None, feedback.get(relative))
                    (migrated / relative).write_text(code, encoding="utf-8")
                    run.evidence.append("patch_applied", f"{mode} candidate iteration {module.iterations}; not accepted until Docker verification.", module.name)
                except ValueError as exc:
                    patch_errors.append({"file": relative, "message": str(exc)})
                    run.evidence.append("error", f"Candidate rejected for {module.name}: {type(exc).__name__}", module.name)
                finally:
                    if translator.client:
                        for call in translator.client.calls[model_calls_recorded:]:
                            run.evidence.append("model_response_usage" if model_path else "model_call", json.dumps(asdict(call), sort_keys=True))
                        model_calls_recorded = len(translator.client.calls)
                        state.metrics.tokens_in = translator.client.tokens_in
                        state.metrics.tokens_out = translator.client.tokens_out
                        state.metrics.cost_usd = translator.client.cost_usd
            compile_result = invoke(runner, "python:3.12-slim", migrated, "compile", evidence=run.evidence)
            errors = compile_result["errors"] + patch_errors
            if model_path:
                saved = workspace / ("model_iteration_%02d" % iteration)
                shutil.copytree(migrated, saved)
                run.verification.setdefault("iterations", []).append({"iteration":iteration, "mode":mode, "syntax_passed":not errors,
                    "tests_passed":None, "behavior_verified":None, "candidate":saved.name})
            if errors:
                run.verification["target_compiles"] = False
                _write(workspace / f"compile_{iteration}.json", errors)
                if any(error["file"] not in by_file for error in errors):
                    raise PipelineFailure("test_suite_incompatible", "Existing test syntax requires a reviewed port; tests were not rewritten or weakened.")
                to_fix = {error["file"] for error in errors}
                feedback = {path: [error for error in errors if error["file"] == path] for path in to_fix}
                run.evidence.append("test_result", f"Target compilation failed for {len(errors)} files; no success claimed.")
                continue
            compiled = True
            for module in state.modules:
                module.status = "testing"
            candidate = invoke(runner, "python:3.12-slim", migrated, "cases", cases, run.evidence)["cases"]
            target_tests = invoke(runner, "python:3.12-slim", migrated, "tests", evidence=run.evidence)
            comparisons = compare_cases(golden, candidate)
            expected_ids = {test["id"] for test in legacy_tests["outcomes"]}
            actual_ids = {test["id"] for test in target_tests["outcomes"]}
            suite_passes = expected_ids == actual_ids and target_tests["tests_run"] == legacy_tests["tests_run"] and all(test["status"] == "passed" for test in target_tests["outcomes"])
            if model_path:
                run.verification["iterations"][-1].update(tests_passed=suite_passes, behavior_verified=bool(comparisons) and all(c["matches"] for c in comparisons))
            run.verification.update(comparisons=comparisons, target_tests=target_tests, target_compiles=True)
            _write(workspace / f"comparisons_{iteration}.json", comparisons)
            _write(workspace / f"target_tests_{iteration}.json", target_tests)
            run.evidence.append("test_result", f"REAL Python 3.12: {sum(c['matches'] for c in comparisons)}/{len(comparisons)} golden matches; existing suite passes={suite_passes}.")
            to_fix = set()
            feedback = {}
            for relative, analyzed in by_file.items():
                module = modules[analyzed["name"]]
                results = [comparison for comparison in comparisons if comparison["module"] == module.name]
                module.tests_passed = sum(comparison["matches"] for comparison in results)
                good = module.tests_passed == module.tests_total and suite_passes
                module.status = "green" if good else "fixing"
                if not good:
                    to_fix.add(relative)
                    feedback[relative] = {"cases": [c for c in results if not c["matches"]], "suite": target_tests if not suite_passes else None}
            state.metrics.tests_passed = sum(c["matches"] for c in comparisons) + sum(test["status"] == "passed" for test in target_tests["outcomes"] if test["id"] in expected_ids)
            state.metrics.lines_migrated = sum(len((migrated / relative).read_text(encoding="utf-8").splitlines()) for relative, analyzed in by_file.items() if modules[analyzed["name"]].status == "green")
            if not to_fix:
                success = True
                break
        state.phase = "security"
        if compiled:
            after = scan(runner, migrated, run.evidence)
            run.verification["security_after"] = after
            _write(workspace / "security_after.json", after)
            state.security.after = len(after["results"])
            state.security.findings, run.verification["security_details"] = findings_for(after)
            for finding in state.security.findings:
                run.evidence.append("security_finding", finding.note, finding.file)
            if after["errors"]:
                success = False
                run.verification["limitations"].append("Target Bandit scan has parse errors; security coverage is incomplete.")
        if success and model_path:
            verified_baseline = workspace / "verified_translation"
            shutil.copytree(migrated, verified_baseline)
        if success and (settings.get("PROOFPORT_SECURITY_FIXTURES") or security_generator is not None):
            from backend.security.engine import SecurityFixEngine
            from backend.security.providers import OfflineFixtureGenerator
            _write(workspace / "security_pre_fixes.json", after)
            generator = security_generator or OfflineFixtureGenerator(_setting_path(root, settings, "PROOFPORT_SECURITY_FIXTURES"))
            security = SecurityFixEngine(
                runner=runner, working=migrated, original=run.source,
                original_hashes={key.split("/", 1)[1]: value for key, value in run.originals.items()},
                artifacts=workspace / "security_attempts", cases=cases, golden=golden,
                existing_tests=legacy_tests, evidence=run.evidence,
            ).run(generator)
            run.verification["security_fix"] = security
            if security["status"] != "verified":
                raise PipelineFailure(security.get("error_code", "security_verification_failed"), "Offline security verification failed; no unverified fix is accepted.")
            after = security["scan_after"]
            run.verification["security_after"] = after
            _write(workspace / "security_after.json", after)
            state.security.before = len(security["findings_before"])
            state.security.after = len(security["findings_after"])
            details = list(security["findings_after"])
            live_ids = {finding["id"] for finding in details}
            details.extend(finding for finding in security["decisions"] if finding["id"] not in live_ids)
            run.verification["security_details"] = details
            from backend.core.models import Finding
            state.security.findings = [Finding.model_validate({key: finding[key] for key in Finding.model_fields}) for finding in details]
            run.verification["comparisons"] = security["final_checks"]["golden"]["comparisons"]
            run.verification["target_tests"] = {key: value for key, value in security["final_checks"]["existing_tests"].items() if key not in {"ran", "passed"}}
            run.verification["limitations"] = [note for note in run.verification["limitations"] if not note.startswith("No automatic security fixes")]
            run.verification["limitations"].append("Security decisions use offline proposals and real Docker checks, not Meta AI. Behavior/configuration/crypto changes require review; a clean scan is not full security.")
        if not success:
            raise PipelineFailure("verification_failed", "Candidate did not pass all compilation, golden, test suite, and scanner checks. No complete migration is claimed.")
        terminal = "done"
    except Exception as exc:
        code = "run_interrupted" if runner.cancelled.is_set() else getattr(exc, "code", "model_unavailable" if isinstance(exc, ModelUnavailable) else "verification_failed")
        terminal = "failed"
        # Provider bodies, keys, and source snippets are not included in top-level errors.
        message = str(exc) if isinstance(exc, (PipelineFailure, ModelUnavailable, SandboxError)) else f"Pipeline failed: {type(exc).__name__}; inspect saved stage evidence."
        state.error = Error(code=code, message=message)
        run.evidence.append("error", message)
    finally:
        if translator:
            translator.close()
        state.phase = "reporting"
        if runner.cancelled.is_set():
            terminal = "failed"
            state.error = Error(code="run_interrupted", message="Docker verification was cancelled; no complete migration is claimed.")
        for module in state.modules:
            if module.status != "green":
                module.status = "failed"
        try:
            state.hashes["unchanged"] = hashes_for(run.source) == run.originals
        except OSError:
            state.hashes["unchanged"] = False
        if not state.hashes["unchanged"]:
            terminal = "failed"
            state.error = Error(code="source_changed", message="Original source hashes changed or could not be rechecked.")
            run.evidence.append("error", state.error.message)
        state.metrics.seconds = round(monotonic() - run.started, 3)
        if model_path:
            if terminal != "done" and migrated is not None and migrated.exists():
                _rollback_model(run, workspace, original, migrated, verified_baseline)
            run.verification["response_calls"] = len(translator.client.calls)
            run.verification["llm_budget"] = translator.client.budget_snapshot()
        run.verification["model_calls"] = 0 if model_path else model_calls_recorded
        run.verification["ai_migration"] = False
        run.evidence.append("run_finished", f"Real Docker pipeline status={terminal}; provider={mode}; original hashes unchanged={state.hashes['unchanged']}.")
        state.chain_intact = run.evidence.verify()
        if not state.chain_intact:
            terminal = "failed"
            state.error = Error(code="evidence_corrupted", message="Evidence chain verification failed.")
            if model_path: _rollback_model(run, workspace, original, migrated, verified_baseline)
        run.pending_status = terminal
