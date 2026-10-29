"""Configured runtimes, local availability and image-bound self-test receipts."""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from backend.core.analyzer import analyze_python
from backend.core.recorder import invoke
from backend.sandbox.runner import DockerRunner, SandboxError


class VersionError(ValueError):
    def __init__(self, message, code="unsupported_python_version"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Runtime:
    version: str
    image: str
    source: bool = True
    target: bool = True


RUNTIMES = {
    version: Runtime(version, "python:" + version + ("" if version == "2.7" else "-slim"), target=version != "2.7")
    for version in ("2.7", "3.8", "3.10", "3.12", "3.13", "3.14")
}
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend/sandbox/runtime_fixture"


def _digest(data):
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class VersionRegistry:
    def __init__(self, runner=None, path=None):
        self.runner = runner or DockerRunner()
        self.path = Path(path) if path else ROOT / "backend/.work/runtime_registry.json"
        try:
            self.receipts = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.receipts = {}
        if not isinstance(self.receipts, dict):
            self.receipts = {}

    @staticmethod
    def configured(version):
        if version not in RUNTIMES:
            raise VersionError("Unsupported Python version: " + str(version))
        return RUNTIMES[version]

    def _revision(self):
        files = [ROOT / "backend/sandbox/harness.py", ROOT / "backend/sandbox/analyze_py2.py", ROOT / "backend/sandbox/analyze_py3.py",
                 ROOT / "backend/core/analyzer.py", ROOT / "backend/core/recorder.py", ROOT / "backend/core/versions.py",
                 ROOT / "backend/sandbox/runner.py", *sorted(FIXTURE.rglob("*.py"))]
        return _digest({str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in files})

    def inspect(self, version):
        runtime = self.configured(version)
        image_id = None
        if self.runner.available():
            result = self.runner._metadata(["image", "inspect", "--format", "{{.Id}}", runtime.image])
            if result.returncode == 0 and result.stdout.strip().startswith(b"sha256:"):
                image_id = result.stdout.decode().strip()
        receipt = self.receipts.get(version, {})
        if not isinstance(receipt, dict) or not isinstance(receipt.get("checks", {}), dict) or not isinstance(receipt.get("python", []), list):
            receipt = {}
        payload = {key: value for key, value in receipt.items() if key != "receipt_hash"}
        verified = bool(image_id and receipt.get("image_id") == image_id
                        and receipt.get("revision") == self._revision()
                        and receipt.get("python", [])[:2] == [int(part) for part in version.split(".")]
                        and set(receipt.get("checks", {})) == {"analyzer", "syntax", "tests", "behavior_harness"}
                        and all(value is True for value in receipt["checks"].values())
                        and receipt.get("receipt_hash") == _digest(payload))
        return {"version": version, "image": runtime.image, "configured": True, "available": bool(image_id),
                "verified": verified, "image_id": image_id, "source": runtime.source, "target": runtime.target,
                "verification_scope": "Runtime and shipped analyzer/harness self-tests; not arbitrary project compatibility or a migration pair.",
                "capabilities": list(receipt.get("checks", {})) if verified else []}

    def snapshot(self):
        return [self.inspect(version) for version in RUNTIMES]

    def select(self, version, role="source"):
        runtime = self.configured(version)
        if role not in {"source", "target"} or not getattr(runtime, role):
            raise VersionError("Python " + version + " is not configured for role " + role)
        state = self.inspect(version)
        if not state["available"]:
            raise VersionError("Docker image unavailable for Python " + version + "; no automatic download or host fallback.", "runtime_unavailable")
        if not state["verified"]:
            raise VersionError("Python " + version + " is available but not verified. Run explicit runtime verification first.", "unverified_version")
        return state

    def verify(self, version, evidence=None):
        runtime = self.configured(version)
        state = self.inspect(version)
        if not state["available"]:
            raise VersionError("Required local image is unavailable: " + runtime.image)
        image = state["image_id"]
        analysis = analyze_python(self.runner, FIXTURE, image, version)
        compiled = invoke(self.runner, image, FIXTURE, "compile", evidence=evidence, version=version)
        tests = invoke(self.runner, image, FIXTURE, "tests", evidence=evidence, version=version)
        cases = [{"id": "runtime.add", "module": "numbers_demo", "steps": [{"call": "numbers_demo.add", "args": [2, 3]}]},
                 {"id": "runtime.divide", "module": "numbers_demo", "steps": [{"call": "numbers_demo.divide", "args": [7, 2]}]}]
        observed = invoke(self.runner, image, FIXTURE, "cases", cases, evidence, version=version)
        checks = {
            "analyzer": bool(analysis["modules"]) and not analysis.get("errors"),
            "syntax": not compiled["errors"],
            "tests": tests["tests_run"] == len(tests["outcomes"]) == 2 and all(test["status"] == "passed" for test in tests["outcomes"]),
            "behavior_harness": [case["steps"][0].get("value") for case in observed["cases"]] == [{"t": "int", "v": 5}, {"t": "int", "v": 3}],
        }
        if not all(checks.values()):
            raise SandboxError("Runtime self-tests failed; version is not verified.")
        receipt = {"version": version, "image_id": image, "python": observed["python"], "revision": self._revision(),
                   "checks": checks, "tests_run": tests["tests_run"], "cases_run": len(observed["cases"])}
        receipt["receipt_hash"] = _digest(receipt)
        self.receipts[version] = receipt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.receipts, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
        return self.select(version)
