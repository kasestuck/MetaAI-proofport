"""Control plane validation builds immutable per-run settings, never environment mutations."""

import asyncio
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from backend.core.capabilities import AUDIT_VERSIONS, COMPATIBILITY_PAIRS, Capabilities
from backend.core.control_models import ControlError, RunSpec
from backend.core.detection import detect
from backend.core.recorder import load_cases
from backend.core.runs import hashes_for
from backend.core.projects import linked
from backend.core.versions import RUNTIMES


class ControlPlane:
    CASES = {"legacy_shop_golden": ("legacy_shop", "tests/fixtures/legacy_shop/cases.json"),
             "universal_py3_golden": ("universal_py3", "tests/fixtures/universal_py3/cases.json"),
             "security_subject_golden": ("security_subject", "tests/fixtures/security_subject/cases.json")}
    FIXTURES = {"legacy_shop_py27_py312": ("legacy_shop", "tests/fixtures/legacy_shop/patches.json")}

    def __init__(self, root, store, projects):
        self.root, self.store, self.projects = root, store, projects
        self.capabilities = Capabilities(root)
        self.instance_id = uuid4().hex
        self.idempotency = {}

    def profile(self, entries, profile_id, project_id, field):
        if profile_id not in entries or entries[profile_id][0] != project_id:
            raise ControlError("profile_unavailable", "Select a server profile bound to this project.", 422, field)
        path = self.root / entries[profile_id][1]
        if not path.is_file() or any(linked(part) for part in (path, *path.parents) if part != self.root and part.is_relative_to(self.root)):
            raise ControlError("profile_unavailable", "The selected server profile is unavailable.", 422, field)
        return path

    def catalog(self):
        return {"root_id": "workspace", "projects": self.projects.snapshot(),
                "cases_profiles": [{"id": key, "project_id": value[0], "available": (self.root / value[1]).is_file()} for key, value in self.CASES.items()],
                "fixture_profiles": [{"id": key, "project_id": value[0], "available": (self.root / value[1]).is_file()} for key, value in self.FIXTURES.items()]}

    def prepare(self, request):
        if request.execution_mode == "live":
            raise ControlError("live_disabled", "Live Meta AI is disabled. No model request was made.", 403, "execution_mode")
        source = self.projects.get(request.project_id)
        operation, mode = request.operation, request.execution_mode
        settings = {}
        pipeline = {"migration": "fixtures", "audit": "audit", "compatibility": "compatibility"}[operation]
        if mode == "simulation":
            if operation != "migration" or any((request.source_version, request.target_version, request.cases_profile_id,
                                                  request.fixture_profile_id, request.verification_level)):
                raise ControlError("incompatible_parameters", "Simulation is a migration demo without runtime/version/profile claims.")
            if not source.is_dir():
                raise ControlError("incompatible_parameters", "Migration demo requires a project directory.")
            return RunSpec(operation, request.project_id, str(source), None, None, mode, "simulation", request.max_iterations,
                           source_hashes=tuple(sorted(hashes_for(source).items())))
        for field in ("source_version", "target_version"):
            version = getattr(request, field)
            if (field == "source_version" or operation != "audit") and version not in RUNTIMES:
                raise ControlError("unsupported_python_version", "Select a configured source and target version for this operation.", 422, field)
        detection = detect(source, request.source_version)
        if detection["status"] == "conflict":
            raise ControlError("source_version_conflict", "Selected source conflicts with known syntax/project metadata.", 422, "source_version")
        if operation == "migration":
            if (request.source_version, request.target_version) != ("2.7", "3.12"):
                raise ControlError("unsupported_migration_pair", "Migration supports only Python 2.7 to Python 3.12.")
            if mode != "offline_fixtures" or not source.is_dir() or request.verification_level not in {None, "behavior"}:
                raise ControlError("incompatible_parameters", "Migration requires a fixture directory and full behavior verification.")
            fixture = self.profile(self.FIXTURES, request.fixture_profile_id, request.project_id, "fixture_profile_id")
            manifest = json.loads(fixture.read_text(encoding="utf-8"))
            if manifest.get("mode") != "explicit_fixture_patches_not_ai" or not manifest.get("files"):
                raise ControlError("profile_unavailable", "Invalid fixture manifest.")
            for name, entry in manifest["files"].items():
                path = (source / name).resolve()
                if not path.is_relative_to(source) or not path.is_file() or sha256(path.read_text(encoding="utf-8").encode()).hexdigest() != entry["sha256"]:
                    raise ControlError("fixture_source_mismatch", "Migration fixture does not match the selected project.")
            settings["PROOFPORT_FIXTURE_FILE"] = str(fixture)
        else:
            if mode != "offline" or request.fixture_profile_id or request.max_iterations != 5:
                raise ControlError("incompatible_parameters", "Audit/compatibility require offline mode without translation settings.")
            if operation == "audit" and (request.source_version not in AUDIT_VERSIONS or request.target_version or request.cases_profile_id or request.verification_level):
                raise ControlError("incompatible_parameters", "Audit uses a checked source version without target/cases/verification level.")
            if operation == "compatibility" and (request.source_version, request.target_version) not in COMPATIBILITY_PAIRS:
                raise ControlError("unsupported_compatibility_pair", "This compatibility operation pair has not been exercised.")
        level = "behavior" if operation == "migration" else request.verification_level or "tests"
        if request.cases_profile_id:
            if level != "behavior":
                raise ControlError("incompatible_parameters", "Cases profiles require behavior verification.")
            case_file = self.profile(self.CASES, request.cases_profile_id, request.project_id, "cases_profile_id")
            load_cases(case_file)
            settings["PROOFPORT_CASES_FILE"] = str(case_file)
        elif operation == "migration" or (operation == "compatibility" and level == "behavior"):
            raise ControlError("profile_unavailable", "Behavior verification requires a project-bound cases profile.", 422, "cases_profile_id")
        if operation == "compatibility" and level in {"tests", "behavior"} and not (source / "tests").is_dir():
            raise ControlError("tests_unavailable", "Requested verification requires an existing tests directory.")
        probe = self.capabilities.snapshot(fresh=True)
        if not probe["docker"]["available"]:
            raise ControlError("docker_unavailable", "Linux Docker is unavailable. No host fallback.", 503)
        pins = {}
        for version in dict.fromkeys(value for value in (request.source_version, request.target_version) if value):
            runtime = next(item for item in probe["runtimes"] if item["version"] == version)
            if not runtime["available"] or not runtime["verified"]:
                raise ControlError("unverified_version" if runtime["available"] else "runtime_unavailable",
                                   "Required runtime image must be local and verified.", 503)
            if detection["python_requires"]:
                if not runtime.get("python"):
                    raise ControlError("runtime_metadata_unavailable", "Actual interpreter patch version is not verified.", 503)
                try:
                    allowed = SpecifierSet(",".join(detection["python_requires"])).contains(".".join(map(str, runtime["python"])), prereleases=True)
                except InvalidSpecifier:
                    raise ControlError("project_metadata_invalid", "Project Python requirements require manual review.") from None
                if not allowed:
                    role = "source" if version == request.source_version else "target"
                    raise ControlError(role + "_metadata_conflict", "Project Python requirements exclude the actual " + role + " interpreter.", 422, role + "_version")
            pins[runtime["image"]] = runtime["image_id"]
        if operation in {"audit", "migration"}:
            if not probe["scanner"]["available"]:
                raise ControlError("scanner_unavailable", "Required local Bandit image is missing.", 503)
            pins[probe["scanner"]["image"]] = probe["scanner"]["image_id"]
        settings.update(PROOFPORT_SOURCE_VERSION=request.source_version,
                        PROOFPORT_TARGET_VERSION=request.target_version or "", PROOFPORT_VERIFICATION_LEVEL=level,
                        PROOFPORT_REQUIRED_TESTS="1" if operation == "compatibility" and level in {"tests", "behavior"} else "0")
        return RunSpec(operation, request.project_id, str(source), request.source_version, request.target_version, mode,
                       pipeline, request.max_iterations, level if operation != "audit" else None,
                       tuple(sorted(settings.items())), tuple(sorted(pins.items())), tuple(sorted(hashes_for(source).items())),
                       request.fixture_profile_id, request.cases_profile_id)

    def preflight(self, request):
        try:
            if self.store.active is not None:
                raise ControlError("run_busy", "Another run is already in progress.", 409)
            spec = self.prepare(request)
            return {"can_start": True, "parameters": spec.public(), "errors": [],
                    "scope": "Preconditions only; creation and worker repeat critical checks. No project code/model calls executed."}
        except ControlError as exc:
            return {"can_start": False, "parameters": request.model_dump(), "errors": [exc.snapshot()]}
        except (OSError, ValueError, KeyError, RuntimeError):
            return {"can_start": False, "parameters": request.model_dump(),
                    "errors": [{"code": "preflight_unavailable", "message": "Project/profile/readiness could not be inspected.", "field": None}]}

    async def start(self, request, key=None):
        digest = sha256(request.model_dump_json().encode()).hexdigest()
        def previous():
            if key and key in self.idempotency:
                old_digest, run_id = self.idempotency[key]
                if old_digest != digest:
                    raise ControlError("idempotency_conflict", "Idempotency key already belongs to different parameters.", 409)
                return run_id
        existing = previous()
        if existing:
            return existing
        if self.store.active is not None:
            raise ControlError("run_busy", "Another run is already in progress.", 409)
        try:
            spec = await asyncio.to_thread(self.prepare, request)
        except ControlError:
            raise
        except (OSError, ValueError, KeyError, RuntimeError):
            raise ControlError("preflight_unavailable", "Project/profile/readiness could not be inspected.", 503) from None
        existing = previous()  # No await until both slot and key are reserved.
        if existing:
            return existing
        run_id = self.store.start(spec.source_path, spec.max_iterations, spec=spec)
        if key:
            self.idempotency[key] = digest, run_id
        return run_id

    def details(self, run_id):
        run = self.store.get(run_id)
        spec = run.spec
        snapshot = run.state.snapshot()
        return {"run_id": run_id, "instance_id": self.instance_id,
                "parameters": spec.public() if spec else {"operation": "legacy", "execution_mode": run.execution_mode},
                "lifecycle": "finalizing" if run.finalizing else snapshot["status"],
                "finalized": run.finalized and self.store.active != run_id and snapshot["status"] in {"done", "failed"},
                "execution": {"effective": spec.execution_mode if spec else run.execution_mode,
                              "simulated": run.simulation, "ai_generated": False, "live_enabled": False},
                "result": {"compatibility": run.verification.get("compatibility"),
                           "security_audit": run.verification.get("security_audit"),
                           "target_tests": run.verification.get("target_tests"),
                           "security_fix": run.verification.get("security_fix"),
                           "limitations": run.verification.get("limitations", [])},
                "state": snapshot}
