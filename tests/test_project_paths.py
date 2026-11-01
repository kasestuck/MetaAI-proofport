from pathlib import Path
import shutil
import subprocess

import pytest

from backend.core.control_models import ControlError
from backend.core.projects import ProjectCatalog, copy_project, source_files


@pytest.mark.parametrize("value", ["../outside", "samples/../outside", "backend/.work", ".git", ".venv", ".env",
                                   "backend/core", "frontend", "tests/test_api.py", "docs", "C:relative", "//host/share",
                                   "samples/file.py:stream", "samples/secret.pem", "samples/secrets.json"])
def test_policy_rejects_traversal_service_and_secret_paths(project, value):
    with pytest.raises(ControlError):
        ProjectCatalog(project).resolve(value)


def test_outside_absolute_path_and_root_itself_rejected(project, tmp_path):
    catalog = ProjectCatalog(project)
    for path in (str(project.parent), str(project)):
        with pytest.raises(ControlError):
            catalog.resolve(path)


def test_copy_excludes_secrets_services_but_keeps_code_tests_docs_fixtures(project):
    source = project / "samples/legacy_shop"
    (source / ".env").write_text("UNIT_SECRET=not-a-real-secret")
    (source / "credentials.json").write_text("{}")
    (source / "private.key").write_text("unit-not-a-key")
    (source / "README.md").write_text("docs")
    (source / "cases.json").write_text("{}")
    (source / ".git").mkdir()
    (source / ".git/config").write_text("private metadata")
    destination = project / "copy"
    copy_project(source, destination)
    names = {path.name for path in source_files(source)}
    assert {"mathutils.py", "README.md", "cases.json", "inventory.csv"} <= names
    assert not {".env", "credentials.json", "private.key", "config"} & names
    assert not (destination / ".env").exists() and not (destination / ".git").exists()
    assert (source / ".env").exists()  # Nothing deleted from originals.


def test_actual_symlink_or_junction_rejected_by_shared_policy(project):
    source = project / "samples/legacy_shop"
    alias = project / "linked_project"
    if __import__('os').name == "nt":
        # Create only a disposable test junction; it points within this test workspace.
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(source)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        alias.symlink_to(source, target_is_directory=True)
    for value in (str(alias), "linked_project"):
        with pytest.raises(ControlError):
            ProjectCatalog(project).resolve(value)
    # No deletion/traversal of the junction is performed here; pytest owns its temp workspace.


def test_project_limit_and_missing_source(project):
    catalog = ProjectCatalog(project)
    catalog.MAX_BYTES = 1
    with pytest.raises(ControlError) as exc:
        catalog.resolve("samples/legacy_shop")
    assert exc.value.code == "project_limit_exceeded"
    with pytest.raises(ControlError) as exc:
        ProjectCatalog(project).resolve("missing")
    assert exc.value.code == "source_not_found"


def test_hardlink_cannot_import_outside_content(project):
    import os
    sensitive = project / "outside.py"
    sensitive.write_text("PRIVATE = 1\n")
    alias = project / "samples/legacy_shop/linked.py"
    os.link(sensitive, alias)
    with pytest.raises(ControlError):
        ProjectCatalog(project).resolve("samples/legacy_shop")
    with pytest.raises(ControlError):
        ProjectCatalog(project).resolve("samples/legacy_shop/linked.py")
