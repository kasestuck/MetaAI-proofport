"""Preserve structure in per-run copies; never mount a writable host directory."""

from pathlib import Path
import shutil


def prepare(source: Path, destination: Path):
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symbolic links in source projects require review.")
    destination.mkdir(parents=True, exist_ok=False)
    ignore = shutil.ignore_patterns(".*", "__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(source, destination / "copy", ignore=ignore)
    shutil.copytree(destination / "copy", destination / "migrated")
    return destination / "copy", destination / "migrated"
