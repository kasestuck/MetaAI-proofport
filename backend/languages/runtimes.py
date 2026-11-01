"""Configured official PHP image candidates; no receipts or support claims yet."""

from dataclasses import dataclass
import re

from backend.sandbox.runner import SandboxError


@dataclass(frozen=True)
class PHPRuntime:
    version: str
    image: str
    source: bool = True
    target: bool = True


PHP_RUNTIMES = (
    PHPRuntime("7.4", "php:7.4.33-cli", target=False),
    PHPRuntime("8.3", "php:8.3.36-cli"),
)
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def php_runtimes(probe=None, *, docker=None, runtimes=PHP_RUNTIMES):
    states = []
    for runtime in runtimes:
        state = {"language": "php", "version": runtime.version, "image": runtime.image,
                 "source": runtime.source, "target": runtime.target, "configured": True,
                 "available": None, "verified": False, "image_id": None,
                 "verification_scope": "No PHP operation receipts exist in P6.1.", "reason": "not_checked"}
        if not docker or probe is None:
            state["reason"] = "docker_unavailable" if docker is False else "not_checked"
        else:
            try:
                result = probe._metadata(["image", "inspect", "--format", "{{.Id}}", runtime.image])
                value = result.stdout.decode("ascii", errors="replace").strip()
                state["available"] = result.returncode == 0 and bool(IMAGE_ID.fullmatch(value))
                if state["available"]:
                    state.update(image_id=value, reason="operation_not_verified")
                else:
                    state["reason"] = "image_unavailable"
            except SandboxError:
                state["reason"] = "metadata_unavailable"
        states.append(state)
    return states
