"""Bounded local metadata probes. Never pulls images or runs code/model calls."""

from datetime import datetime, timezone
from threading import Lock
from time import monotonic

from backend.core.security import SCANNER_IMAGE
from backend.core.versions import VersionRegistry
from backend.sandbox.runner import DockerRunner, SandboxError


AUDIT_VERSIONS = ("2.7", "3.12", "3.13")
COMPATIBILITY_PAIRS = (("3.12", "3.12"), ("3.12", "3.13"), ("3.13", "3.12"))


class MetadataProbe:
    """A metadata-only registry adapter with a shared deadline; no run method."""
    def __init__(self, runner, available, deadline):
        self.runner, self.linux, self.deadline = runner, available, deadline

    def available(self):
        return self.linux

    def _metadata(self, args):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise SandboxError("Metadata probe deadline exceeded.")
        return self.runner._metadata(args, timeout=min(2, remaining))


class Capabilities:
    TTL = 5

    def __init__(self, root):
        self.root = root
        self.lock = Lock()
        self.cached = None
        self.checked = 0

    def snapshot(self, fresh=False):
        with self.lock:
            if not fresh and self.cached is not None and monotonic() - self.checked < self.TTL:
                from copy import deepcopy
                return deepcopy(self.cached)
            runner = DockerRunner()
            deadline = monotonic() + 8
            docker = runner.available()
            probe = MetadataProbe(runner, docker, deadline)
            registry = VersionRegistry(probe, self.root / "backend/.work/runtime_registry.json")
            from backend.core.versions import RUNTIMES
            runtimes = []
            for version, runtime in RUNTIMES.items():
                try:
                    runtime_state = registry.inspect(version)
                    runtime_state["python"] = registry.receipts.get(version, {}).get("python") if runtime_state["verified"] else None
                    runtimes.append(runtime_state)
                except SandboxError:
                    runtimes.append({"version": version, "image": runtime.image, "configured": True,
                                     "available": None, "verified": False, "image_id": None,
                                     "source": runtime.source, "target": runtime.target, "reason": "metadata_unavailable"})
            scanner = {"available": False, "image": SCANNER_IMAGE, "image_id": None}
            if docker:
                try:
                    result = probe._metadata(["image", "inspect", "--format", "{{.Id}}", SCANNER_IMAGE])
                    image_id = result.stdout.decode().strip()
                    if result.returncode == 0 and image_id.startswith("sha256:"):
                        scanner.update(available=True, image_id=image_id)
                except SandboxError:
                    scanner["available"] = False
            data = {"api_version": "1", "checked_at": datetime.now(timezone.utc).isoformat(),
                    "cache_ttl_seconds": self.TTL, "docker": {"available": docker}, "runtimes": runtimes,
                    "scanner": scanner,
                    "operations": {
                        "migration": {"pairs": [["2.7", "3.12"]], "execution_modes": ["offline_fixtures", "simulation"]},
                        "audit": {"source_versions": list(AUDIT_VERSIONS), "execution_modes": ["offline"]},
                        "compatibility": {"pairs": [list(pair) for pair in COMPATIBILITY_PAIRS], "execution_modes": ["offline"]}},
                    "live": {"enabled": False, "reason": "live_disabled", "provider_validated": False},
                    "ai_security_fix": {"enabled": False, "reason": "not_implemented_live"},
                    "model_workflows": {"interface":"internal_language_adapter", "public_launchable":False,
                        "offline_response_modes":["mock","replay"], "structured_response":"ModelPatch/v1",
                        "languages":["python","php"], "live_enabled":False, "provider_validated":False,
                        "scope":"Offline response protocol and Docker verification. No real Meta migration/security claim or automatic paid retries."},
                    "scope": "Runtime self-tests and listed operation adapters, not universal project compatibility. Missing/unverified images cannot be selected."}
            from copy import deepcopy
            from backend.languages.registry import LanguageRegistry
            data["languages"] = LanguageRegistry(root=self.root).snapshot(data, probe=probe, docker=docker)
            self.cached, self.checked = deepcopy(data), monotonic()
            return data
