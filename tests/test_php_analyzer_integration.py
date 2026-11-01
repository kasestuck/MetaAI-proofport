"""Opt-in PHP lint only. No pulls, dependency installs, project execution or migration."""

from pathlib import Path

import pytest

from backend.core.evidence import Evidence
from backend.languages.base import hashes, inventory
from backend.languages.php import PHPAdapter
from backend.languages.runtimes import PHP_RUNTIMES, php_runtimes
from backend.sandbox.runner import DockerRunner


pytestmark = pytest.mark.docker


@pytest.mark.parametrize("version", [runtime.version for runtime in PHP_RUNTIMES])
def test_php_lint_real_local_image_no_execution_or_download(tmp_path, version):
    runner = DockerRunner()
    if not runner.available():
        pytest.skip("Docker is unavailable; no PHP runtime has been verified.")
    state = next(r for r in php_runtimes(runner, docker=True) if r["version"] == version)
    if not state["available"]:
        pytest.skip("Configured official PHP image is not installed; no download is authorized.")
    project = tmp_path / "php_source"; project.mkdir()
    (project / "safe.php").write_text("<?php file_put_contents('/src/MUST_NOT_EXECUTE', 'forbidden'); function f($x) { return $x + 1; }\n")
    original = hashes(project, inventory(project)[1]); evidence = Evidence()
    result = PHPAdapter().lint(project, version=version, runner=runner, evidence=evidence)
    assert result.verification.syntax_passed is True
    assert result.verification.tests_passed is result.verification.behavior_verified is None
    artifact = Path(__file__).resolve().parents[1] / "backend/.work" / result.analysis["lint"]["artifact_id"]
    assert not (artifact / "project/MUST_NOT_EXECUTE").exists()
    assert hashes(project, inventory(project)[1]) == original and evidence.verify()
    (project / "broken.php").write_text("<?php function invalid( {\n")
    broken = PHPAdapter().lint(project, version=version, runner=runner, evidence=evidence)
    assert broken.verification.syntax_passed is False
    assert not any(r["verified"] for r in php_runtimes(runner, docker=True))
