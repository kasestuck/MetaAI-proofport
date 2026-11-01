"""Original bounded lexical PHP review rules. No Bandit, execution or exploit claim."""

from collections import defaultdict
from hashlib import sha256
import json

from backend.languages.base import SecurityResult, hashes, inventory
from backend.languages.php import analyze_php
from backend.languages.php_lexer import lex


RULES = {
    "PHP-SQL": (89, "HIGH", "SQL query construction/sink needs parameterization and context review."),
    "PHP-XSS": (79, "MEDIUM", "Dynamic HTML output needs context-appropriate escaping review."),
    "PHP-CMD": (78, "HIGH", "Shell/command sink needs argument separation and input review."),
    "PHP-DESERIALIZE": (502, "HIGH", "Unserialization needs trust-boundary and allowed-type review."),
    "PHP-PATH": (22, "MEDIUM", "Dynamic filesystem access needs confinement and input review."),
    "PHP-SECRET": (798, "LOW", "Possible embedded credential; value withheld. Review configuration impacts."),
    "PHP-HASH": (328, "MEDIUM", "Weak hash may be unsuitable for passwords; changing output requires review."),
    "PHP-UPLOAD": (434, "HIGH", "Upload sink needs filename/type/size and destination validation review."),
}
LIMITATIONS = ("Limited lexical sink rules, not interprocedural taint analysis or a security certificate.",
               "Includes/autoloading, sanitizers, templates, aliases, dynamic calls and application context may be missed.",
               "All findings are potential risks; no exploit or full absence of vulnerabilities is confirmed.",
               "Literal values/source snippets are withheld. Coverage is PHP files only, excluding tests/vendor.")


def scan_php(source, evidence=None):
    source, files = inventory(source)
    analysis = analyze_php(source).analysis
    before = hashes(source, files)
    modules = {m["file"]: m for m in analysis["modules"]}
    findings, errors, occurrences = [], list(analysis["diagnostics"]), defaultdict(int)
    for path in files:
        if path.suffix.lower() not in {".php", ".phtml"}: continue
        relative = path.name if source.is_file() else path.relative_to(source).as_posix()
        if "tests" in path.relative_to(source if source.is_dir() else source.parent).parts or "vendor" in path.parts: continue
        if relative not in modules: continue
        tokens, _ = lex(path.read_bytes().decode("utf-8"))
        funcs = modules[relative]["functions"]
        for index, token in enumerate(tokens):
            word = token.value.lower() if token.kind == "name" else ""
            prev = tokens[index - 1].value if index else ""
            following = tokens[index + 1].value if index + 1 < len(tokens) else ""
            statement = []
            for item in tokens[index:index + 160]:
                if item.kind == "symbol" and item.value == ";": break
                statement.append(item)
            dynamic = any(t.kind == "variable" for t in statement)
            direct_input = any(t.value in {"$_GET", "$_POST", "$_REQUEST", "$_FILES", "$_COOKIE"} for t in statement)
            selected = []
            call = following == "(" and prev.lower() not in {"function", "new"} and prev != "&"
            if call:
                if word in {"mysqli_query", "mysql_query"} or (word in {"query", "exec"} and prev in {"->", "?->"}): selected.append("PHP-SQL")
                if word in {"shell_exec", "system", "passthru", "exec", "popen"} and prev not in {"->", "?->", "::"}: selected.append("PHP-CMD")
                if word == "proc_open" and index + 2 < len(tokens) and tokens[index + 2].value not in {"[", "array"}: selected.append("PHP-CMD")
                if word == "unserialize": selected.append("PHP-DESERIALIZE")
                if word in {"readfile", "file_get_contents", "fopen"} and dynamic: selected.append("PHP-PATH")
                if word == "move_uploaded_file": selected.append("PHP-UPLOAD")
                if word in {"md5", "sha1"} or (word == "hash" and index + 2 < len(tokens) and tokens[index + 2].kind == "string" and tokens[index + 2].value.lower() in {"md5", "sha1"}): selected.append("PHP-HASH")
            if word in {"echo", "print"} and dynamic and not any(t.value.lower() in {"htmlspecialchars", "htmlentities"} for t in statement): selected.append("PHP-XSS")
            if token.kind == "variable" and any(part in token.value.lower() for part in ("password", "secret", "api_key", "token")):
                if following == "=" and index + 2 < len(tokens) and tokens[index + 2].kind == "string" and tokens[index + 2].value:
                    selected.append("PHP-SECRET")
            for rule in selected:
                preceding = [f for f in funcs if f["line"] <= token.line]
                scope = preceding[-1]["name"] if preceding else "<module>"
                anchor = (relative, rule, scope); occurrences[anchor] += 1
                fingerprint = sha256(json.dumps([*anchor, occurrences[anchor]], separators=(",", ":")).encode()).hexdigest()[:24]
                cwe, severity, description = RULES[rule]
                findings.append({"id": rule + "-" + fingerprint, "scanner": "proofport-php-lexical-v1", "scanner_test": rule,
                                 "file": relative, "line": token.line, "scope": scope, "cwe": {"id": cwe}, "severity": severity,
                                 "confidence": "HIGH" if direct_input else "MEDIUM" if dynamic else "LOW", "status": "open",
                                 "description": description, "proposed_fix": description,
                                 "verification_status": "potential_risk_not_confirmed"})
    if hashes(source, inventory(source)[1]) != before:
        raise ValueError("Source changed during PHP static scan.")
    data = {"scanner": "proofport-php-lexical-v1", "findings": findings, "confirmed_findings": [],
            "coverage": "partial" if errors else "limited_lexical", "errors": errors, "limitations": list(LIMITATIONS),
            "project_executed": False, "fixes_applied": False, "source_hashes": before, "originals_unchanged": True}
    if evidence: evidence.append("security_scan", json.dumps({"language": "php", "potential_findings": len(findings), "confirmed": 0, "coverage": data["coverage"]}, sort_keys=True))
    return data


def security_result(source, evidence=None):
    data = scan_php(source, evidence)
    return SecurityResult("php", tuple(data["findings"]), data["coverage"], LIMITATIONS)
