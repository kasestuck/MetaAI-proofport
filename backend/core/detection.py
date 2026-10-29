"""Conservative static version evidence. Never imports setup.py or resolves deps."""

import ast
import configparser
import io
from pathlib import Path
import re
import tokenize
import tomllib

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from backend.core.versions import RUNTIMES, VersionRegistry


def _syntax(text):
    evidence, floor, py2 = [], None, False
    try:
        tokens = [token for token in tokenize.generate_tokens(io.StringIO(text).readline)
                  if token.type not in {tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.NL}]
    except (tokenize.TokenError, IndentationError):
        tokens = []
    lines = {}
    for token in tokens:
        if token.type not in {tokenize.NEWLINE, tokenize.ENDMARKER}:
            lines.setdefault(token.start[0], []).append(token)
    for line, parts in lines.items():
        if len(parts) > 1 and parts[0].string == "print" and parts[1].string not in {"(", "=", ":", "."}:
            py2 = True
            evidence.append({"line": line, "kind": "python2_print_statement"})
        if any(a.type == tokenize.NUMBER and b.string in {"L", "l"} and a.end == b.start for a, b in zip(parts, parts[1:])):
            py2 = True
            evidence.append({"line": line, "kind": "python2_long_literal"})
        if parts[0].string in {"except", "raise", "exec"}:
            depth = 0
            for part in parts[1:]:
                if part.string in {"(", "[", "{"}:
                    depth += 1
                elif part.string in {")", "]", "}"}:
                    depth -= 1
                elif part.string == "," and depth == 0:
                    py2 = True
                    evidence.append({"line": line, "kind": "python2_exception_statement"})
                    break
        # PEP 696: defaults in a type-parameter list. Comments/strings are tokens, not scanned text.
        words = [part.string for part in parts]
        if words[0] in {"def", "class", "type"} and "[" in words and "]" in words:
            between = words[words.index("[") + 1:words.index("]")]
            if "=" in between:
                floor = (3, 13)
                evidence.append({"line": line, "kind": "type_parameter_default", "minimum": "3.13"})
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return py2, floor, evidence, False
    # E.g. print >> stream also parses as a Python 3 expression; do not guess.
    py2 = False
    for node in ast.walk(tree):
        minimum = None
        if isinstance(node, ast.JoinedStr):
            minimum = (3, 6)
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await)):
            minimum = (3, 5)
        elif isinstance(node, ast.AnnAssign):
            minimum = (3, 6)
        elif isinstance(node, ast.NamedExpr):
            minimum = (3, 8)
        elif isinstance(node, ast.Match):
            minimum = (3, 10)
        elif isinstance(node, ast.TryStar):
            minimum = (3, 11)
        elif isinstance(node, ast.TypeAlias):
            minimum = (3, 12)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if getattr(node, "type_params", []):
                minimum = (3, 12)
            elif getattr(node.args, "posonlyargs", []):
                minimum = (3, 8)
            elif node.returns or node.args.kwonlyargs or any(arg.annotation for arg in node.args.args):
                minimum = (3, 0)
        if minimum:
            floor = max(floor or minimum, minimum)
            evidence.append({"line": getattr(node, "lineno", None), "kind": type(node).__name__, "minimum": ".".join(map(str, minimum))})
    return py2, floor, evidence, True


def _possible_minor(version, constraints):
    spec = SpecifierSet(",".join(constraints))
    major, minor = map(int, version.split("."))
    probes = {f"{version}.0", f"{version}.999999"}
    for constraint in spec:
        try:
            boundary = Version(constraint.version.rstrip(".*"))
            if (boundary.major, boundary.minor) == (major, minor):
                probes.update(f"{version}.{patch}" for patch in (max(0, boundary.micro - 1), boundary.micro, boundary.micro + 1))
        except InvalidVersion:
            pass
    return any(spec.contains(probe, prereleases=True) for probe in probes)


def detect(source: Path, override=None):
    source = Path(source)
    if override:
        VersionRegistry.configured(override)
    if not source.exists() or (source.is_file() and source.suffix != ".py"):
        raise ValueError("Select a Python file or project directory.")
    files = [source] if source.is_file() else sorted(path for path in source.rglob("*.py")
             if not path.is_symlink() and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(source).parts))
    root = source.parent if source.is_file() else source
    evidence, constraints, dependencies, hints, limitations = [], [], [], [], []
    py2, floor = False, None
    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        old, minimum, facts, parsed = _syntax(text)
        py2 |= old
        if minimum:
            floor = max(floor or minimum, minimum)
        evidence.extend({"file": path.name if source.is_file() else path.relative_to(root).as_posix(), **fact} for fact in facts)
        if not parsed and not old and not minimum:
            limitations.append("Host parser could not read " + path.name + "; invalid or newer grammar is possible.")

    def dependency(text, location):
        try:
            requirement = Requirement(text)
            dependencies.append({"name": requirement.name, "specifier": str(requirement.specifier),
                                 "marker": str(requirement.marker) if requirement.marker else None,
                                 "direct_reference": bool(requirement.url), "origin": location})
        except InvalidRequirement:
            limitations.append("Dependency entry could not be statically interpreted in " + location)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8-sig"))
            project = data.get("project", {})
            if isinstance(project.get("requires-python"), str):
                constraints.append(project["requires-python"])
            for entry in project.get("dependencies", []):
                dependency(entry, "pyproject.toml")
            poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry.get("python"), str):
                value = poetry["python"]
                if value.startswith("^") and re.fullmatch(r"\d+(?:\.\d+){1,2}", value[1:]):
                    value = ">=" + value[1:] + ",<" + str(int(value[1:].split(".")[0]) + 1)
                constraints.append(value)
        except (ValueError, TypeError, OSError):
            limitations.append("pyproject.toml metadata could not be fully interpreted.")
    configuration = root / "setup.cfg"
    if configuration.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(configuration, encoding="utf-8-sig")
            if parser.has_option("options", "python_requires"):
                constraints.append(parser.get("options", "python_requires"))
            for entry in parser.get("options", "install_requires", fallback="").splitlines():
                if entry.strip():
                    dependency(entry.strip(), "setup.cfg")
        except configparser.Error:
            limitations.append("setup.cfg could not be fully interpreted.")
    setup = root / "setup.py"
    if setup.is_file():
        try:
            tree = ast.parse(setup.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == "setup") or (isinstance(node.func, ast.Attribute) and node.func.attr == "setup")):
                    for keyword in node.keywords:
                        if keyword.arg == "python_requires" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                            constraints.append(keyword.value.value)
                        elif keyword.arg == "install_requires" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                            for entry in keyword.value.elts:
                                if isinstance(entry, ast.Constant) and isinstance(entry.value, str):
                                    dependency(entry.value, "setup.py (static literal only)")
        except (SyntaxError, ValueError):
            limitations.append("setup.py metadata is not statically readable; it was not executed.")
    requirements = root / "requirements.txt"
    if requirements.is_file():
        for line in requirements.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                dependency(line.strip(), "requirements.txt")
    preference = root / ".python-version"
    if preference.is_file():
        text = preference.read_text().strip()
        if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", text):
            hints.append({"file": ".python-version", "preferred_interpreter": text})
    possible = []
    metadata_valid = True
    try:
        SpecifierSet(",".join(constraints))
    except InvalidSpecifier:
        metadata_valid = False
        limitations.append("Unsupported Python metadata constraint; it is not used to infer support.")
    for version in RUNTIMES:
        pair = tuple(map(int, version.split(".")))
        if py2 and pair != (2, 7):
            continue
        if floor and pair < floor:
            continue
        if metadata_valid and not _possible_minor(version, constraints):
            continue
        possible.append(version)
    if override:
        status = "declared" if override in possible else "conflict"
        if status == "declared":
            possible = [override]
    elif not possible:
        status = "conflict_or_outside_configured_versions"
    elif evidence or constraints:
        status = "range" if len(possible) > 1 else "candidate"
    else:
        status = "unknown"
    return {"status": status, "user_version": override, "possible_versions": possible,
            "syntax_minimum": ".".join(map(str, floor)) if floor else None,
            "python_requires": constraints, "dependency_constraints": dependencies, "interpreter_hints": hints,
            "evidence": evidence, "project_executed": False, "dependencies_resolved": False,
            "limitations": [*limitations, "Candidates are not proof of interpreter or project compatibility.",
                            "Conditional dependency markers do not restrict the entire project. Package Python requirements were not downloaded/resolved.",
                            "Patch-version constraints require the actual interpreter version; detection only considers possible minor-series patches."]}
