"""Explicit PHP branch of the control plane; no global settings or downloads."""

from backend.core.control_models import ControlError, RunSpec
from backend.core.runs import hashes_for
from backend.languages.base import inventory
from backend.php.fixtures import load_manifest
from backend.php.protocol import load_cases
from backend.php.runtime import source_hashes
from backend.php.verification import test_runner


def prepare(control, request):
    source = control.projects.get(request.project_id, inventory_only=True)
    _, files = inventory(source)
    if not any(p.suffix == ".php" for p in files):
        raise ControlError("language_mismatch", "Select an explicit PHP project.")
    source_hashes(source)  # Includes credential/mixed-project denial.
    op = request.operation
    if request.source_version not in {"7.4", "8.3"}:
        raise ControlError("unsupported_php_version", "Configured PHP versions are 7.4 and 8.3.")
    level = request.verification_level or ("behavior" if op == "migration" else "tests")
    settings = {}
    if op == "migration":
        if (request.source_version, request.target_version) != ("7.4", "8.3"):
            raise ControlError("unsupported_migration_pair", "Only PHP 7.4 to 8.3 offline fixture migration is implemented.")
        if request.execution_mode != "offline_fixtures" or level != "behavior" or not source.is_dir():
            raise ControlError("incompatible_parameters", "PHP migration requires a directory, offline fixtures and behavior verification.")
        fixture = control.profile(control.FIXTURES, request.fixture_profile_id, request.project_id, "fixture_profile_id")
        load_manifest(fixture, source)
        settings["PHP_FIXTURE_FILE"] = str(fixture)
        if request.security_fix_profile_id:
            settings["PHP_SECURITY_FILE"] = str(control.profile(control.SECURITY_FIXTURES, request.security_fix_profile_id, request.project_id, "security_fix_profile_id"))
    else:
        if request.execution_mode != "offline" or request.fixture_profile_id or request.security_fix_profile_id or request.max_iterations != 5:
            raise ControlError("incompatible_parameters", "PHP checks require offline mode without translation/fix settings.")
        if op == "audit":
            if request.target_version or request.cases_profile_id or request.verification_level:
                raise ControlError("incompatible_parameters", "Static PHP audit does not take a target, cases or dynamic verification level.")
        elif (request.source_version, request.target_version) != ("7.4", "8.3"):
            raise ControlError("unsupported_compatibility_pair", "Only PHP 7.4 to 8.3 has an exercised compatibility workflow.")
    if request.cases_profile_id:
        if level != "behavior" or op == "audit":
            raise ControlError("incompatible_parameters", "Cases profiles require behavior verification.")
        cases = control.profile(control.CASES, request.cases_profile_id, request.project_id, "cases_profile_id")
        load_cases(cases); settings["PHP_CASES_FILE"] = str(cases)
    elif op == "migration" or (op == "compatibility" and level == "behavior"):
        raise ControlError("profile_unavailable", "Behavior verification requires project-bound PHP cases.", field="cases_profile_id")
    if op != "audit" and level in {"tests", "behavior"}:
        if not source.is_dir(): raise ControlError("tests_unavailable", "Tests require a project directory.")
        test_runner(source)
    caps = control.capabilities.snapshot(fresh=True)
    php = caps.get("languages", {}).get("php", {})
    if op not in php.get("supported_operations", []):
        code = "docker_unavailable" if op != "audit" and not caps["docker"]["available"] else "php_e2e_verification_required"
        raise ControlError(code, "PHP operation requires a current local demo proof and pinned runtimes; no host fallback.", 503)
    pins = {}
    if op != "audit":
        for runtime in php["runtimes"]:
            if runtime["version"] in {request.source_version, request.target_version}:
                if runtime.get("available") is not True or runtime.get("verified") is not True:
                    raise ControlError("unverified_version", "Required PHP runtime is not verified.", 503)
                pins[runtime["image"]] = runtime["image_id"]
    return RunSpec(op, request.project_id, str(source), request.source_version, request.target_version,
                   request.execution_mode, "php", request.max_iterations, None if op == "audit" else level,
                   settings=tuple(sorted(settings.items())), images=tuple(sorted(pins.items())),
                   source_hashes=tuple(sorted(hashes_for(source).items())), fixture_profile_id=request.fixture_profile_id,
                   cases_profile_id=request.cases_profile_id, language="php", security_fix_profile_id=request.security_fix_profile_id)
