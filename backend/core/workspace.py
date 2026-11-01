"""Preserve structure in per-run copies; never mount a writable host directory."""

from pathlib import Path
import shutil


def prepare(source: Path, destination: Path):
    from backend.core.projects import copy_project
    destination.mkdir(parents=True, exist_ok=False)
    copy_project(source, destination / "copy")
    shutil.copytree(destination / "copy", destination / "migrated")
    return destination / "copy", destination / "migrated"
