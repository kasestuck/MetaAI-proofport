"""Original PHP fixtures; only lexical host reads and explicitly mocked Docker."""

import ast
from dataclasses import asdict
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from backend.core.evidence import Evidence
from backend.languages.base import AdapterError, hashes, inventory
from backend.languages.php import PHPAdapter, analyze_php
from backend.languages.__main__ import main
from backend.sandbox.runner import Result


FIXTURE = Path(__file__).parent / "fixtures/php_analysis"
IMAGE = "sha256:" + "a" * 64


@pytest.fixture(autouse=True)
def forbid_meta(monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI", lambda *a, **k: pytest.fail("No model calls in P6.1"))


def subject(tmp_path, text):
    source = tmp_path / "module.php"; source.write_text(text, encoding="utf-8"); return source


def test_analyzer_structure_dependencies_plan_hashes_and_no_ast_or_execution(monkeypatch):
    monkeypatch.setattr(ast, "parse", lambda *a, **k: pytest.fail("PHP must never use Python AST"))
    before = hashes(FIXTURE, inventory(FIXTURE)[1])
    evidence = Evidence()
    result = analyze_php(FIXTURE, source_version="7.4", target_version="8.3", evidence=evidence)
    modules = {m["file"]: m for m in result.analysis["modules"]}
    assert modules["bootstrap.php"]["classes"][0]["name"] == "Basket"
    assert modules["bootstrap.php"]["namespaces"] == [{"name": "ProofportDemo", "line": 3}]
    assert {f["name"] for f in modules["bootstrap.php"]["functions"]} == {"total", "legacy_pair", "legacy_offset", "compare_value"}
    assert modules["bootstrap.php"]["functions"][0]["kind"] == "method"
    assert modules["bootstrap.php"]["functions"][0]["class"] == "Basket"
    assert result.analysis["graph"]["bootstrap.php"] == ["lib/prices.php"]
    assert result.analysis["order"] == ["lib/prices.php", "bootstrap.php"]
    assert result.analysis["composer"]["php_constraint"] == ">=7.4 <8.4"
    assert not result.analysis["composer"]["dependencies_installed"]
    assert {f["name"] for f in modules["lib/prices.php"]["functions"]} == {"price_total"}
    assert result.analysis["source_hashes"] == before == hashes(FIXTURE, inventory(FIXTURE)[1])
    assert asdict(result.verification) == {"syntax_passed": None, "tests_passed": None, "behavior_verified": None}
    assert not result.analysis["project_executed"] and not result.analysis["migration_plan"]["migration_performed"]
    assert evidence.verify() and evidence.since(0)[0]["type"] == "language_analysis"


def test_real_lexical_warning_lines_not_security_verdicts():
    result = analyze_php(FIXTURE)
    module = next(m for m in result.analysis["modules"] if m["file"] == "bootstrap.php")
    issues = module["potential_incompatibilities"]
    assert {i["code"] for i in issues} == {"removed_function_candidate", "curly_offset_candidate", "loose_comparison_review"}
    assert next(i for i in issues if i["code"] == "removed_function_candidate")["line"] == 10
    assert all(i["status"] == "needs_review" for i in issues)


@pytest.mark.parametrize("literal", ["'class Fake {} function pretend() {} each([]);'", '"function pretend() {}"',
                                    "`echo 'function pretend() {}'`", "<<<'TEXT'\nfunction pretend() {}\nTEXT", '<<<TEXT\nclass Fake {}\nTEXT'])
def test_comments_strings_templates_and_heredoc_never_create_declarations(tmp_path, literal):
    source = subject(tmp_path, "<div>class HTMLFake {}</div><?php\n// class CommentFake {}\n/* function comment() {} */\n$v = " + literal + ";\nfunction real_name() {}\n?>function HtmlAgain() {}")
    module = analyze_php(source).analysis["modules"][0]
    assert [f["name"] for f in module["functions"]] == ["real_name"]
    assert not module["classes"] and not module["potential_incompatibilities"]


def test_dynamic_and_outside_includes_are_not_followed(tmp_path):
    source = subject(tmp_path, "<?php require $_GET['file']; include '/etc/private.php'; require __DIR__ . '/../outside.php';")
    items = analyze_php(source).analysis["modules"][0]["includes"]
    assert [i["resolution"] for i in items] == ["dynamic_requires_review", "external_or_unsupported_path", "outside_project"]
    assert all(i["dependency"] is None for i in items)


def test_include_cycle_and_unresolved_literal_require_review(tmp_path):
    (tmp_path / "a.php").write_text("<?php require 'b.php';")
    (tmp_path / "b.php").write_text("<?php require 'a.php'; include 'missing.php';")
    result = analyze_php(tmp_path)
    assert result.analysis["cyclic_or_blocked"] == ["a.php", "b.php"]
    assert result.analysis["migration_plan"]["manual_review"] == ["a.php", "b.php"]


def test_methods_class_constants_references_and_anonymous_classes(tmp_path):
    source = subject(tmp_path, "<?php class First { function each() {} } $x = First::class; $y = new class extends First { function method() {} }; function &each() {} function () {}; ")
    module = analyze_php(source).analysis["modules"][0]
    assert len(module["classes"]) == 2 and module["classes"][1]["anonymous"]
    assert [f["name"] for f in module["functions"]] == ["each", "method", "each"]
    assert not module["potential_incompatibilities"]


@pytest.mark.parametrize("text,code", [("<?php 'unterminated", "unterminated_literal"), ("<?php /* x", "unterminated_comment"),
                                      ("<?php $x = <<<END\nnot closed", "unterminated_heredoc")])
def test_lexical_errors_do_not_become_syntax_verdicts(tmp_path, text, code):
    result = analyze_php(subject(tmp_path, text))
    assert result.analysis["diagnostics"][0]["code"] == code
    assert result.verification.syntax_passed is None


def test_hashes_are_actual_bytes_and_literals_do_not_leak(tmp_path):
    key = "fake-private-value-for-unit-test"
    source = subject(tmp_path, "<?php $password = '" + key + "'; function f() {}")
    result = analyze_php(source)
    assert key not in json.dumps(result.public())
    source.write_bytes(b"<?php function different() {}\r\n")
    assert analyze_php(source).analysis["source_hashes"] != result.analysis["source_hashes"]


def test_non_utf8_and_oversized_files_are_partial_inventory(tmp_path):
    (tmp_path / "old.php").write_bytes(b"<?php // \xff")
    (tmp_path / "large.php").write_text("x" * 1_048_577)
    result = analyze_php(tmp_path)
    assert {d["code"] for d in result.analysis["diagnostics"]} == {"encoding_requires_review", "analysis_file_limit"}
    assert result.analysis["migration_plan"]["manual_review"] == ["large.php", "old.php"]
    assert result.verification.syntax_passed is None


@pytest.mark.parametrize("version", ["8.4", "latest", "8.3;sh", None])
def test_unconfigured_lint_versions_do_not_start_docker(tmp_path, version):
    class Forbidden:
        def available(self): pytest.fail("Version must be checked first")
    with pytest.raises(AdapterError) as caught:
        PHPAdapter().lint(subject(tmp_path, "<?php echo 1;"), version=version, runner=Forbidden())
    assert caught.value.code == "unsupported_php_version"


class LintDouble:
    """Checks command construction/decisions, not real PHP execution evidence."""
    def __init__(self, *, failed=False, timeout=False, patch="8.3.36", available=True):
        self.calls = []; self.failed = failed; self.timeout = timeout; self.patch = patch; self.local = available
    def available(self): return self.local
    def _metadata(self, args):
        assert args[:2] == ["image", "inspect"]
        return CompletedProcess(args, 0, IMAGE.encode(), b"")
    def run(self, image, source, command):
        self.calls.append((image, source, command))
        assert image == IMAGE and command[0] == "php" and "-n" in command
        assert not (source / ".env").exists()
        if "-r" in command:
            assert command[-1] == "echo PHP_VERSION;"
            return Result(image, 0, self.patch, "", 0.01)
        assert "-l" in command and "--" in command and command[-1].startswith("/src/")
        return Result(image, 255 if self.failed else 0, "not persisted", "not persisted", 0.01, timed_out=self.timeout)


@pytest.mark.parametrize("failed", [False, True])
def test_docker_lint_decisions_are_syntax_only_and_copy_isolated(tmp_path, failed):
    source = subject(tmp_path, "<?php file_put_contents('/src/never', 'must not execute');")
    (tmp_path / ".env").write_text("PRIVATE=unit-only")
    runner = LintDouble(failed=failed); evidence = Evidence()
    before = source.read_bytes()
    result = PHPAdapter().lint(source, version="8.3", source_version="7.4", target_version="8.3", runner=runner, evidence=evidence)
    assert result.verification.syntax_passed is (not failed)
    assert result.verification.tests_passed is result.verification.behavior_verified is None
    assert runner.calls[0][1] != tmp_path and source.read_bytes() == before
    assert result.analysis["lint"]["actual_version"] == "8.3.36"
    assert result.source_version == "7.4" and result.target_version == "8.3"
    assert evidence.verify() and len(evidence.since(0)) == 2


@pytest.mark.parametrize("options,code", [({"available": False}, "docker_unavailable"), ({"patch": "7.4.33"}, "php_runtime_mismatch"),
                                        ({"timeout": True}, "php_lint_unavailable")])
def test_lint_cannot_turn_unavailable_timeout_or_wrong_runtime_into_success(tmp_path, options, code):
    with pytest.raises(AdapterError) as caught:
        PHPAdapter().lint(subject(tmp_path, "<?php echo 1;"), version="8.3", runner=LintDouble(**options))
    assert caught.value.code == code


def test_original_change_during_lint_invalidates_verdict(tmp_path):
    source = subject(tmp_path, "<?php echo 1;")
    class ConcurrentEdit(LintDouble):
        def run(self, image, copy, command):
            result = super().run(image, copy, command)
            if "-l" in command: source.write_text("<?php echo 2;")
            return result
    with pytest.raises(AdapterError) as caught:
        PHPAdapter().lint(source, version="8.3", runner=ConcurrentEdit())
    assert caught.value.code == "source_changed"


def test_lint_never_mounts_composer_auth(tmp_path):
    subject(tmp_path, "<?php echo 1;")
    auth = tmp_path / "auth.json"; auth.write_text('{"unit":"private-value"}')
    runner = LintDouble()
    with pytest.raises(AdapterError) as caught:
        PHPAdapter().lint(tmp_path, version="8.3", runner=runner)
    assert caught.value.code == "php_credentials_require_review" and not runner.calls
    assert auth.read_text() == '{"unit":"private-value"}'


def test_no_php_run_operations_bandit_or_patches_are_enabled(tmp_path):
    adapter = PHPAdapter(); source = subject(tmp_path, "<?php echo 1;"); before = source.read_bytes()
    with pytest.raises(AdapterError, match="P6.2"):
        adapter.compatibility(None, None, None, None)
    with pytest.raises(AdapterError, match="P6.3"):
        adapter.security_findings(None, source, Evidence())
    assert source.read_bytes() == before


def test_cli_is_offline_default_and_evidence_is_verifiable(capsys):
    assert main([str(FIXTURE), "--source-version", "7.4", "--target-version", "8.3"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["language"] == "php" and data["chain_intact"] and data["verification"]["syntax_passed"] is None
