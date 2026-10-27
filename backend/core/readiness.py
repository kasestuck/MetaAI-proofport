"""Read-only P0 prerequisite checks. Never import or execute project sources."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]
P0_IMAGES = ("python:2.7", "python:3.12-slim")


@dataclass(frozen=True)
class Readiness:
    docker: bool
    images: dict[str, bool]
    source_present: bool
    llm_mode: str
    model_configured: bool
    api_key_configured: bool
    pipeline_implemented: bool = False

    @property
    def blockers(self) -> list[str]:
        result = []
        if not self.docker:
            result.append("docker_unavailable")
        if not all(self.images.values()):
            result.append("runtime_images_unavailable")
        if not self.source_present:
            result.append("demo_source_unavailable")
        if self.llm_mode != "live":
            result.append("live_model_not_selected")
        if not self.api_key_configured or not self.model_configured:
            result.append("model_not_configured")
        if not self.pipeline_implemented:
            result.append("pipeline_not_implemented")
        return result

    def snapshot(self) -> dict:
        return {**asdict(self), "ready": not self.blockers, "blockers": self.blockers}


def _docker_ok(executable: str, *args: str) -> bool:
    try:
        return subprocess.run(
            [executable, *args], capture_output=True, timeout=3, check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def inspect_readiness(root: Path = ROOT) -> Readiness:
    settings = {**dotenv_values(root / ".env"), **os.environ}
    executable = shutil.which("docker")
    docker = bool(executable and _docker_ok(executable, "info", "--format", "{{.ServerVersion}}"))
    images = {
        image: bool(docker and _docker_ok(executable, "image", "inspect", image))
        for image in P0_IMAGES
    }
    source = root / "samples" / "legacy_shop"
    return Readiness(
        docker=docker, images=images,
        source_present=source.is_dir() and any(source.rglob("*.py")),
        llm_mode=(settings.get("LLM_MODE") or "mock").lower(),
        model_configured=bool(settings.get("MODEL_NAME")),
        api_key_configured=bool(settings.get("MODEL_API_KEY")),
    )


if __name__ == "__main__":
    readiness = inspect_readiness()
    print(json.dumps(readiness.snapshot(), indent=2))
    raise SystemExit(0 if not readiness.blockers else 2)
