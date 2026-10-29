import json
from subprocess import CompletedProcess

import pytest

from backend.core.detection import detect
from backend.core.versions import RUNTIMES, VersionError, VersionRegistry


class MetadataOnly:
    """Tests registry state transitions, never pretends to run project tests."""
    image = None

    def available(self):
        return True

    def _metadata(self, args):
        assert args[:2] == ["image", "inspect"]  # Never pulls or executes anything.
        return CompletedProcess(args, 0 if self.image else 1, (self.image or "").encode(), b"")


def test_registry_configured_is_distinct_from_available_and_verified(tmp_path):
    runner = MetadataOnly()
    registry = VersionRegistry(runner, tmp_path / "registry.json")
    assert set(RUNTIMES) == {"2.7", "3.8", "3.10", "3.12", "3.13", "3.14"}
    state = registry.inspect("3.13")
    assert state["configured"] and not state["available"] and not state["verified"]
    with pytest.raises(VersionError, match="unavailable"):
        registry.select("3.13")
    runner.image = "sha256:" + "a" * 64
    assert registry.inspect("3.13")["available"]
    with pytest.raises(VersionError, match="not verified"):
        registry.select("3.13")
    with pytest.raises(VersionError, match="role"):
        registry.select("2.7", "target")


@pytest.mark.parametrize("value", ["3.9", "3", "latest", "3.13-slim", "3.12;bad", None])
def test_registry_rejects_unconfigured_versions(value):
    with pytest.raises(VersionError):
        VersionRegistry.configured(value)


@pytest.mark.parametrize("data", [[], {"3.12": []}, {"3.12": {"python": 3}}, {"3.12": {"checks": []}}, {"3.12": {"checks": {"syntax": True}}}])
def test_corrupt_receipts_cannot_claim_support(tmp_path, data):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data))
    runner = MetadataOnly()
    runner.image = "sha256:" + "a" * 64
    assert not VersionRegistry(runner, path).inspect("3.12")["verified"]


def subject(tmp_path, code):
    path = tmp_path / "module.py"
    path.write_text(code, encoding="utf-8")
    return path


def test_common_syntax_does_not_guess_exact_version(tmp_path):
    result = detect(subject(tmp_path, 'def add(a, b):\n    return a + b\n'))
    assert result["status"] == "unknown"
    assert set(result["possible_versions"]) == set(RUNTIMES)
    assert not result["project_executed"]


@pytest.mark.parametrize("code", ['print "old"\n', 'x = 10L\n', 'try:\n    pass\nexcept Exception, error:\n    pass\n'])
def test_python2_syntax_evidence(tmp_path, code):
    result = detect(subject(tmp_path, code))
    assert result["possible_versions"] == ["2.7"]
    assert result["status"] == "candidate"


@pytest.mark.parametrize("code,minimum,possible", [
    ('x = f"{1}"\n', "3.6", ["3.8", "3.10", "3.12", "3.13", "3.14"]),
    ('match x:\n    case 1: pass\n', "3.10", ["3.10", "3.12", "3.13", "3.14"]),
    ('type Items = list[int]\n', "3.12", ["3.12", "3.13", "3.14"]),
    ('def identity[T = int](value: T) -> T:\n    return value\n', "3.13", ["3.13", "3.14"]),
])
def test_newer_grammar_returns_range_not_exact_compatibility(tmp_path, code, minimum, possible):
    result = detect(subject(tmp_path, code))
    assert result["syntax_minimum"] == minimum
    assert result["possible_versions"] == possible


def test_comments_and_strings_are_not_version_syntax(tmp_path):
    result = detect(subject(tmp_path, '# print "x"\ntext = "def fn[T = int](): pass"\n'))
    assert result["status"] == "unknown"
    assert result["syntax_minimum"] is None


def test_metadata_and_dependency_requirements_are_distinguished(tmp_path):
    subject(tmp_path, 'x = 1\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.10,<3.14"\ndependencies = [\'example>=2; python_version < "3.12"\']\n')
    (tmp_path / ".python-version").write_text("3.10.15")
    result = detect(tmp_path)
    assert result["possible_versions"] == ["3.10", "3.12", "3.13"]
    assert result["dependency_constraints"][0]["marker"] == 'python_version < "3.12"'
    assert result["interpreter_hints"][0]["preferred_interpreter"] == "3.10.15"
    assert result["status"] == "range"
    assert not result["dependencies_resolved"]


def test_setup_metadata_is_parsed_without_execution(tmp_path):
    (tmp_path / "setup.py").write_text('from setuptools import setup\nraise RuntimeError("must never execute")\nsetup(python_requires=">=3.12.1,<3.13", install_requires=["example>=1"])\n')
    result = detect(tmp_path)
    assert result["possible_versions"] == ["3.12"]  # Some 3.12 patches can satisfy it.
    assert result["dependency_constraints"][0]["name"] == "example"
    assert not result["project_executed"]


def test_user_version_validated_against_static_evidence(tmp_path):
    path = subject(tmp_path, 'match x:\n    case 1: pass\n')
    assert detect(path, "3.12")["status"] == "declared"
    assert detect(path, "3.8")["status"] == "conflict"
    with pytest.raises(VersionError):
        detect(path, "3.9")
