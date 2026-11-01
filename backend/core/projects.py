"""One filesystem policy for both HTTP APIs and copied project content."""

from hashlib import sha256
import os
from pathlib import Path, PureWindowsPath
import shutil
import stat

from backend.core.control_models import ControlError


SERVICE_NAMES = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".work", ".tmp",
                 "work", "node_modules", ".mypy_cache", ".ruff_cache"}
SECRET_NAMES = {".env", "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml",
                "id_rsa", "id_ed25519"}


def excluded(name):
    lower = name.lower()
    return (lower.startswith(".") or lower in SERVICE_NAMES or lower in SECRET_NAMES
            or lower.endswith((".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx")))


def linked(path):
    try:
        value = path.lstat()
        return path.is_symlink() or bool(getattr(value, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def source_files(source, *, max_files=None, max_bytes=None):
    if linked(source):
        raise ControlError("unsafe_project_path", "Project links/junctions are not allowed.", 403)
    if source.is_file():
        if source.stat().st_nlink > 1:
            raise ControlError("unsafe_project_path", "Hard-linked source files require review.", 403)
        return [] if excluded(source.name) else [source]
    result, pending, size, entries = [], [source], 0, 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as children:
            for entry in children:
                if excluded(entry.name):
                    continue
                entries += 1
                if max_files and entries > max_files * 2:
                    raise ControlError("project_limit_exceeded", "Too many project entries.", 413)
                path = Path(entry.path)
                if linked(path):
                    raise ControlError("unsafe_project_path", "Project links/junctions are not allowed.", 403)
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    # Path.stat obtains link-count metadata on Windows too.
                    info = path.stat(follow_symlinks=False)
                    if info.st_nlink > 1:
                        raise ControlError("unsafe_project_path", "Hard-linked project files require review.", 403)
                    size += info.st_size
                    result.append(path)
                    if (max_files and len(result) > max_files) or (max_bytes and size > max_bytes):
                        raise ControlError("project_limit_exceeded", "Project exceeds file/byte limits.", 413)
                else:
                    raise ControlError("unsafe_project_path", "Only regular project files are allowed.", 403)
    return sorted(result)


def copy_project(source, destination):
    source_files(source)  # Reject visible links before any content copy.
    if source.is_file():
        destination.mkdir()
        shutil.copy2(source, destination / source.name)
    else:
        def ignore(directory, names):
            for name in names:
                if not excluded(name) and linked(Path(directory) / name):
                    raise ControlError("unsafe_project_path", "Project link changed during copy.", 403)
            return [name for name in names if excluded(name)]
        shutil.copytree(source, destination, ignore=ignore)


class ProjectCatalog:
    """The workspace is the approved root; service/source-control areas are denied."""
    DEFAULTS = {"legacy_shop": "samples/legacy_shop", "universal_py3": "tests/fixtures/universal_py3",
                "security_subject": "tests/fixtures/security_subject"}
    MAX_FILES = 2000
    MAX_BYTES = 16 * 1024 * 1024

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.entries = dict(self.DEFAULTS)

    def resolve(self, value, *, relative_only=False):
        if not isinstance(value, str) or not value or "\0" in value or value.startswith(("~", "\\\\", "//")):
            raise ControlError("unsafe_project_path", "Choose a workspace-relative project path.", 403)
        windows = PureWindowsPath(value)
        parts = value.replace("\\", "/").split("/")
        if ".." in parts or (relative_only and (Path(value).is_absolute() or windows.drive)):
            raise ControlError("unsafe_project_path", "Traversal or absolute project paths are not allowed here.", 403)
        path = Path(value)
        if not path.is_absolute():
            if windows.drive:
                raise ControlError("unsafe_project_path", "Drive-relative project paths are not allowed.", 403)
            path = self.root / path
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            raise ControlError("project_outside_root", "Project must be inside the approved workspace.", 403) from None
        names = relative.parts
        if not names or any(excluded(name) or ":" in name for name in names):
            raise ControlError("unsafe_project_path", "Secret and service paths cannot be selected.", 403)
        if names[0].lower() in {"backend", "frontend", "docs"} or (names[0].lower() == "tests" and (len(names) < 3 or names[1].lower() != "fixtures")):
            raise ControlError("unsafe_project_path", "Select a project, not backend/frontend/service source.", 403)
        current = self.root
        for name in names:
            current /= name
            if linked(current):
                raise ControlError("unsafe_project_path", "Links and junctions cannot select project content.", 403)
        canonical = path.resolve()
        if not canonical.is_relative_to(self.root):
            raise ControlError("project_outside_root", "Resolved project escapes the workspace.", 403)
        if not canonical.exists() or not (canonical.is_dir() or (canonical.is_file() and canonical.suffix == ".py")):
            raise ControlError("source_not_found", "The source folder or Python file does not exist.", 400)
        try:
            self.inspect(canonical)
        except OSError:
            raise ControlError("source_unreadable", "Project files could not be inspected.", 400) from None
        return canonical

    def inspect(self, source):
        files = source_files(source, max_files=self.MAX_FILES, max_bytes=self.MAX_BYTES)
        if len(files) > self.MAX_FILES or sum(path.stat().st_size for path in files) > self.MAX_BYTES:
            raise ControlError("project_limit_exceeded", "Project exceeds 2000 files or 16 MiB.", 413)
        if not any(path.suffix == ".py" for path in files):
            raise ControlError("source_empty", "The source folder contains no Python modules.", 400)
        return files

    def register(self, value):
        path = self.resolve(value, relative_only=True)
        relative = path.relative_to(self.root).as_posix()
        project_id = next((key for key, entry in self.entries.items() if entry == relative),
                          "project_" + sha256(relative.encode()).hexdigest()[:24])
        self.entries[project_id] = relative
        return {"project_id": project_id, "relative_path": relative, "kind": "file" if path.is_file() else "directory"}

    def get(self, project_id):
        if project_id not in self.entries:
            raise ControlError("project_not_found", "Resolve or select a registered project first.", 404, "project_id")
        return self.resolve(self.entries[project_id])

    def snapshot(self):
        entries = []
        for project_id, relative in list(self.entries.items()):
            try:
                self.get(project_id)
                entries.append({"project_id": project_id, "relative_path": relative, "available": True})
            except (ControlError, OSError) as exc:
                entries.append({"project_id": project_id, "relative_path": relative, "available": False,
                                "reason": getattr(exc, "code", "source_unreadable")})
        return entries
