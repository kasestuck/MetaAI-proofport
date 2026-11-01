"""Map real PHP evidence to the unchanged legacy state and report envelope."""

from pathlib import Path

from backend.core.models import Error, Finding
from backend.languages.runtimes import PHP_RUNTIMES
from backend.php.pipeline import PHPJob, execute


def execute_run(run, run_id, root, settings):
    spec = run.spec
    run.state.status = "running"
    run.execution_mode = spec.execution_mode
    pins = dict(spec.images)
    images = {r.version: pins[r.image] for r in PHP_RUNTIMES if r.image in pins}
    path = lambda key: Path(settings[key]) if settings.get(key) else None
    data, artifact = execute(PHPJob(run.source, operation=spec.operation, source_version=spec.source_version,
        target_version=spec.target_version, cases=path("PHP_CASES_FILE"), fixture=path("PHP_FIXTURE_FILE"),
        security_fixture=path("PHP_SECURITY_FILE"), max_iterations=spec.max_iterations,
        verification_level=spec.verification_level or "syntax"), runner=run.runner, images=images,
        evidence=run.evidence, progress=lambda phase: setattr(run.state, "phase", phase))
    # Keep the engine's own report; the existing finalizer writes the HTTP exports.
    export = artifact / "api"; export.mkdir()
    run.workspace = export
    run.verification.update(data)
    level = "behavior_verified" if data["behavior_verified"] is True else "tests_passed" if data["tests_passed"] is True else "syntax_compatible" if data["syntax_passed"] is True else "not_verified"
    run.verification["compatibility"] = {"level": level, "syntax_passed": data["syntax_passed"],
        "tests_passed": data["tests_passed"], "behavior_verified": data["behavior_verified"], "source": spec.source_version, "target": spec.target_version}
    run.state.isolation = data["isolation"]
    comparisons = data.get("comparisons", [])
    for module in run.state.modules:
        filename = module.name.replace(".", "/") + ".php"
        checks = [c for c in comparisons if c["module"] == filename]
        module.tests_total = len(checks)
        module.tests_passed = sum(c["matches"] for c in checks)
        module.iterations = len(data["iterations"]) if data.get("migration_performed") and not filename.startswith("tests/") else 0
        # For audits green means the operation finished, never behavioral proof.
        module.status = "green" if data["status"] == "done" else "failed"
    run.state.metrics.tests_total = len(comparisons)
    run.state.metrics.tests_passed = sum(c["matches"] for c in comparisons)
    if data.get("migration_performed"):
        old, new = data["original_hashes"], data.get("accepted_hashes", {})
        accepted = artifact / data["accepted_copy"]
        run.state.metrics.lines_migrated = sum(len((accepted / name).read_bytes().splitlines()) for name in old if name.endswith(".php") and old[name] != new.get(name))
    scan = data.get("security_audit") or data.get("security_before", {})
    after = data.get("security_audit") or data.get("security_after", {})
    run.state.security.before = len(scan.get("findings", []))
    run.state.security.after = len(after.get("findings", []))
    decisions = data.get("security_fix", {}).get("decisions", scan.get("findings", []))
    run.state.security.findings = [Finding(id=f["id"], file=f["file"], line=f["line"], severity=f["severity"], status=f["status"],
        note="Potential PHP static warning; " + f["description"]) for f in decisions]
    run.pending_status = data["status"]
    if data.get("error"): run.state.error = Error(**data["error"])
