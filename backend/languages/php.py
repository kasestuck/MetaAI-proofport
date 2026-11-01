"""Read-only PHP lexical structure plus explicit, image-pinned Docker lint.

This is not a PHP AST, compatibility verifier, security scanner or translator.
No project PHP is imported/evaluated; optional php -l never runs top-level code.
"""

from dataclasses import replace
import json
from pathlib import Path
import posixpath
from uuid import uuid4

from backend.languages.base import AdapterError, AnalysisResult, Verification, hashes, inventory
from backend.languages.php_lexer import lex
from backend.languages.runtimes import PHP_RUNTIMES, php_runtimes
from backend.sandbox.runner import DockerRunner
from backend.core.projects import copy_project


REMOVED = {"each": "8.0", "create_function": "8.0", "get_magic_quotes_gpc": "8.0",
           "get_magic_quotes_runtime": "8.0", "money_format": "8.0", "hebrevc": "8.0",
           "convert_cyr_string": "8.0", "mysql_connect": "7.0", "mysql_query": "7.0"}
LIMITATIONS = (
    "Lexical inventory only; syntax is unknown unless explicit Docker lint runs.",
    "No type/data-flow analysis, runtime include resolution, autoloading or extension compatibility checks.",
    "Comments/literals are skipped; interpolation, dynamic declarations and non-UTF-8 source need review.",
    "Potential obsolete constructs may refer to user-defined names; no incompatibility/exploit is confirmed.",
    "No tests, PHPUnit, golden cases, security audit, fixes, migration or dependency installation performed.",
)


def _structure(tokens, filename, known_files):
    values = [t.value for t in tokens]
    depth, levels, stack, closes = 0, [], [], {}
    next_delimiter, next_semicolon = {}, {}
    delimiter, semicolon = None, None
    for index in range(len(tokens) - 1, -1, -1):
        next_delimiter[index], next_semicolon[index] = delimiter, semicolon
        if tokens[index].kind == "symbol" and values[index] in {"{", ";"}:
            delimiter = index
        if tokens[index].kind == "symbol" and values[index] == ";":
            semicolon = index
    for index, token in enumerate(tokens):
        levels.append(depth)
        if token.kind == "symbol" and token.value == "{":
            stack.append(index); depth += 1
        elif token.kind == "symbol" and token.value == "}" and stack:
            closes[stack.pop()] = index; depth -= 1
    classes, functions, includes, issues, namespaces = [], [], [], [], []
    class_openings, active_classes = {}, []
    for index, token in enumerate(tokens):
        word = token.value.lower() if token.kind == "name" else ""
        previous = values[index - 1] if index else ""
        following = values[index + 1] if index + 1 < len(values) else ""
        if word == "namespace" and following != "\\":
            end = next_delimiter[index]
            if end is not None:
                declaration = tokens[index + 1:end]
                if all(t.kind == "name" or (t.kind == "symbol" and t.value == "\\") for t in declaration):
                    namespaces.append({"name": "".join(t.value for t in declaration), "line": token.line})
        if token.kind == "symbol" and token.value == "{":
            if index in class_openings:
                active_classes.append(class_openings[index])
        elif token.kind == "symbol" and token.value == "}" and active_classes and active_classes[-1]["_close"] == index:
            active_classes.pop()
        if word in {"class", "interface", "trait", "enum"} and previous != "::":
            name = tokens[index + 1].value if previous.lower() != "new" and index + 1 < len(tokens) and tokens[index + 1].kind == "name" else None
            opening = next_delimiter[index]
            if opening is not None and values[opening] == "{":
                classes.append({"name": name, "kind": word, "line": token.line, "anonymous": name is None,
                                "_open": opening, "_close": closes.get(opening, len(tokens))})
                class_openings[opening] = classes[-1]
        if word == "function" and previous.lower() != "use":
            name_index = index + 1 + (following == "&")
            if name_index + 1 < len(tokens) and tokens[name_index].kind == "name" and values[name_index + 1] == "(":
                owner = active_classes[-1] if active_classes and levels[index] == levels[active_classes[-1]["_open"]] + 1 else None
                functions.append({"name": values[name_index], "line": token.line, "class": owner["name"] if owner else None,
                                  "kind": "method" if owner else "function"})
        if word in {"include", "include_once", "require", "require_once"} and previous not in {"->", "?->", "::"}:
            end = next_semicolon[index] if next_semicolon[index] is not None else len(tokens)
            expression = tokens[index + 1:end]
            if expression and expression[0].value == "(" and expression[-1].value == ")":
                expression = expression[1:-1]
            candidate, anchor = None, "file_relative_candidate"
            if len(expression) == 1 and expression[0].kind == "string":
                candidate = expression[0].value
            elif (len(expression) == 3 and expression[0].kind == "name" and expression[0].value.upper() == "__DIR__"
                  and expression[1].value == "." and expression[2].kind == "string" and expression[2].value.startswith("/")):
                candidate = expression[2].value.lstrip("/"); anchor = "__DIR__"
            dependency, status = None, "dynamic_requires_review"
            if candidate is not None:
                if candidate.startswith(("/", "\\")) or ":" in candidate or "\\" in candidate:
                    status = "external_or_unsupported_path"
                else:
                    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(filename), candidate))
                    if normalized == ".." or normalized.startswith("../"):
                        status = "outside_project"
                    elif normalized in known_files:
                        dependency, status = normalized, "local_candidate"
                    else:
                        status = "unresolved_literal"
            includes.append({"kind": word, "line": token.line, "dependency": dependency, "resolution": status, "anchor": anchor})
        # Only name tokens at call sites; a string containing 'each(' or a
        # declaration/method named each is not treated as a built-in call.
        declaration = previous.lower() in {"function", "new"} or (previous == "&" and index > 1 and values[index - 2].lower() == "function")
        if word in REMOVED and following == "(" and previous not in {"->", "?->", "::"} and not declaration:
            issues.append({"code": "removed_function_candidate", "name": word, "line": token.line,
                           "since": REMOVED[word], "status": "needs_review", "confidence": "LOW"})
        if token.kind == "variable" and following == "{":
            issues.append({"code": "curly_offset_candidate", "line": token.line, "since": "8.0", "status": "needs_review", "confidence": "MEDIUM"})
        if token.kind == "symbol" and token.value in {"==", "!="}:
            issues.append({"code": "loose_comparison_review", "line": token.line, "since": "8.0", "status": "needs_review", "confidence": "LOW"})
    return {"file": filename, "namespaces": namespaces, "classes": [{k: v for k, v in c.items() if not k.startswith("_")} for c in classes],
            "functions": functions, "includes": includes, "potential_incompatibilities": issues}


def analyze_php(source, *, source_version=None, target_version=None, evidence=None):
    versions = {r.version for r in PHP_RUNTIMES}
    if (source_version is not None and source_version not in versions) or (target_version is not None and target_version not in versions):
        raise AdapterError("unsupported_php_version", "Select a configured PHP analysis version; no compatibility support is implied.")
    source, files = inventory(source)
    php_files = [p for p in files if p.suffix.lower() in {".php", ".phtml"}]
    if not php_files:
        raise AdapterError("source_empty", "No PHP files were found.", 400)
    before = hashes(source, files)
    names = {p.name if source.is_file() else p.relative_to(source).as_posix() for p in php_files}
    modules, diagnostics = [], []
    for path in php_files:
        name = path.name if source.is_file() else path.relative_to(source).as_posix()
        if path.stat().st_size > 1_048_576:
            diagnostics.append({"file": name, "code": "analysis_file_limit"}); continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            diagnostics.append({"file": name, "code": "encoding_requires_review"}); continue
        tokens, errors = lex(text)
        diagnostics.extend({"file": name, **error} for error in errors)
        module = _structure(tokens, name, names)
        module["sha256"] = before[name]
        module["is_test"] = "tests" in Path(name).parts or Path(name).stem.lower().endswith("test")
        modules.append(module)
    graph = {m["file"]: sorted({item["dependency"] for item in m["includes"] if item["dependency"]}) for m in modules}
    pending, order = set(graph), []
    while pending:
        ready = sorted(name for name in pending if not (set(graph[name]) & pending))
        if not ready:
            break
        order.extend(ready); pending.difference_update(ready)
    composer = None
    if not source.is_file() and source / "composer.json" in files:
        try:
            data = json.loads((source / "composer.json").read_text(encoding="utf-8"))
            requirement = data.get("require", {}).get("php")
            composer = {"php_constraint": requirement if isinstance(requirement, str) else None,
                        "scripts_present": bool(data.get("scripts")), "dependencies_installed": False}
        except (ValueError, AttributeError):
            diagnostics.append({"file": "composer.json", "code": "composer_metadata_requires_review"})
    unchanged = hashes(source, inventory(source)[1]) == before
    if not unchanged:
        raise AdapterError("source_changed", "Original files changed during PHP analysis.", 409)
    data = {"mode": "lexical_inventory", "project_executed": False, "syntax_checked": False,
            "source_hashes": before, "originals_unchanged": True, "modules": modules,
            "file_count": len(php_files), "graph": graph, "order": order, "cyclic_or_blocked": sorted(pending),
            "diagnostics": diagnostics, "composer": composer,
            "phpunit": {"configuration_present": not source.is_file() and any(source / n in files for n in ("phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml")),
                        "executed": False, "dependencies_checked": False},
            "migration_plan": {"target_requested": target_version, "migration_performed": False,
                               "manual_review": sorted(pending | {d["file"] for d in diagnostics} | {m["file"] for m in modules if m["potential_incompatibilities"] or any(i["resolution"] != "local_candidate" for i in m["includes"])}),
                               "steps": ["Review lexical inventory and dynamic includes", "Verify official runtime image IDs",
                                         "Lint in source and target Docker runtimes", "Add explicit tests/golden profiles in P6.2"]}}
    if evidence:
        evidence.append("language_analysis", json.dumps({"language": "php", "mode": "lexical_inventory", "files": len(php_files),
                                                       "source_unchanged": True, "syntax_passed": None, "tests_passed": None, "behavior_verified": None}, sort_keys=True))
    return AnalysisResult("php", source_version, target_version, data, limitations=LIMITATIONS)


class PHPAdapter:
    language = "php"

    def analyze(self, source, *, source_version=None, target_version=None, runner=None, evidence=None):
        return analyze_php(source, source_version=source_version, target_version=target_version, evidence=evidence)

    def lint(self, source, *, version, source_version=None, target_version=None, runner=None, evidence=None):
        """Developer opt-in only. A passing lint does not create a support receipt."""
        if version not in {r.version for r in PHP_RUNTIMES}:
            raise AdapterError("unsupported_php_version", "PHP lint requires a configured runtime.")
        result = self.analyze(source, source_version=source_version, target_version=target_version)
        source, files = inventory(source)
        if any(p.name.lower() == "auth.json" for p in files):
            raise AdapterError("php_credentials_require_review", "Composer auth.json must not be mounted; prepare a separately sanitized project for lint.", 403)
        php_files = [p for p in files if p.suffix.lower() in {".php", ".phtml"}]
        if len(php_files) > 32:
            raise AdapterError("php_lint_limit", "P6.1 lint is limited to 32 files; no partial syntax success is inferred.")
        runner = runner or DockerRunner()
        states = php_runtimes(runner, docker=runner.available())
        selected = next(state for state in states if state["version"] == version)
        if selected["available"] is not True:
            raise AdapterError(selected["reason"], "PHP lint requires an available local official image; no pull or host fallback.", 503)
        image_id = selected["image_id"]
        runtime = next(r for r in PHP_RUNTIMES if r.version == version)
        expected_patch = runtime.image.split(":", 1)[1].split("-", 1)[0]
        artifact = Path(__file__).resolve().parents[1] / ".work" / ("php-lint-" + uuid4().hex)
        artifact.mkdir(parents=True)
        root = artifact / "project"
        copy_project(source, root)
        if hashes(root, inventory(root)[1]) != result.analysis["source_hashes"]:
            raise AdapterError("source_changed", "PHP working copy does not match original hashes.", 409)
        probe = runner.run(image_id, root, ["php", "-n", "-r", "echo PHP_VERSION;"])
        if probe.exit_code or probe.timed_out or probe.output_exceeded or probe.stdout.strip() != expected_patch:
            raise AdapterError("php_runtime_mismatch", "PHP image did not confirm its configured patch version.", 503)
        if evidence:
            evidence.append("sandbox_run", json.dumps({"language": "php", "action": "runtime_identity", "actual_version": expected_patch,
                                                       "image_id": image_id}, sort_keys=True))
        outcomes = []
        for path in php_files:
            relative = path.name if source.is_file() else path.relative_to(source).as_posix()
            observed = runner.run(image_id, root, ["php", "-n", "-d", "auto_prepend_file=", "-d", "auto_append_file=",
                                  "-d", "opcache.enable_cli=0", "-l", "/src/" + relative])
            if observed.timed_out or observed.output_exceeded:
                raise AdapterError("php_lint_unavailable", "Docker lint did not complete; no syntax verdict.", 503)
            if observed.exit_code not in {0, 255}:
                raise AdapterError("php_lint_unavailable", "Unexpected PHP lint exit; no syntax verdict.", 503)
            outcomes.append({"file": relative, "syntax_passed": observed.exit_code == 0})
            if evidence:
                evidence.append("sandbox_run", json.dumps({"language": "php", "action": "lint", "file": relative,
                                                           "image_id": selected["image_id"], "syntax_passed": observed.exit_code == 0}, sort_keys=True))
        if hashes(source, inventory(source)[1]) != result.analysis["source_hashes"] or hashes(root, inventory(root)[1]) != result.analysis["source_hashes"]:
            raise AdapterError("source_changed", "Original files changed during PHP lint.", 409)
        data = {**result.analysis, "syntax_checked": True, "lint": {"version_requested": version, "actual_version": expected_patch, "image_id": image_id,
                                                                  "artifact_id": artifact.name, "files": outcomes,
                                                                  "scope": "Syntax only; no includes or project statements executed."}}
        return replace(result, analysis=data, verification=Verification(syntax_passed=all(item["syntax_passed"] for item in outcomes)))

    def compatibility(self, run, run_id, root, settings):
        from backend.php.worker import execute_run
        return execute_run(run, run_id, root, settings)

    def security_findings(self, runner, source, evidence):
        from backend.php.security import security_result
        return security_result(source, evidence)
