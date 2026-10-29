"""Real, offline Bandit scan. Findings are potential risks, never auto-fixed."""

import ast
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import PurePosixPath

from backend.core.models import Finding
from backend.sandbox.runner import SandboxError


SCANNER_IMAGE = "proofport-bandit:1.8.6"

RECOMMENDATIONS = {
    "B307": "Review the supported expression language before replacing eval; literal-only parsing changes arithmetic/call semantics and also needs input/resource limits.",
    "B608": "Use parameterized queries after reviewing intentionally accepted query/input behavior.",
    "B602": "Prefer a fixed executable and argument list with shell=False; review legacy shell expansion and input semantics first.",
    "B105": "Move genuine credentials to an approved secret source and rotate them; configuration and output compatibility require review.",
    "B106": "Avoid embedded credentials; review configuration and credential rotation.",
    "B107": "Avoid credential defaults; review callers and configuration.",
    "B324": "Review strong salted password hashing and an explicit migration of stored hashes; never silently change formats.",
    "B301": "Restrict trusted inputs or adopt a reviewed serialization format; do not silently change stored data.",
    "B403": "Inspect actual deserialization use; an import advisory alone does not establish an exploitable vulnerability.",
    "B404": "Inspect actual subprocess arguments and shell use; an import advisory alone does not establish injection.",
    "B603": "Check executable/argument provenance and validation; non-shell execution is not by itself proof of injection.",
}


def _scope(source, line):
    try:
        tree = ast.parse(source)
        names = sorted((node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        and node.lineno <= line <= node.end_lineno), key=lambda node: node.lineno)
        return ".".join(node.name for node in names) or "<module>"
    except SyntaxError:
        # Python 2 scanning is partial; never execute it to discover context.
        return "<module>"


def scan(runner, source, evidence):
    result = runner.run(SCANNER_IMAGE, source, ["python", "-m", "bandit", "-r", "/src", "-f", "json", "--ignore-nosec"])
    evidence.append("sandbox_run", json.dumps({"action": "bandit", **result.summary()}, sort_keys=True))
    if result.exit_code not in (0, 1) or result.timed_out or result.output_exceeded:
        raise SandboxError("Bandit scan did not finish successfully.")
    data = json.loads(result.stdout)
    # Do not persist source snippets or secret values from scanner output.
    for item in data.get("results", []):
        item.pop("code", None)
        if item["test_id"] in {"B105", "B106", "B107"}:
            item["issue_text"] = "Possible hard-coded secret; inspect source privately."
        item["filename"] = str(PurePosixPath(item["filename"]).relative_to("/src"))
        item["scope"] = _scope((source / item["filename"]).read_text(encoding="utf-8"), item["line_number"])
    return data


def findings_for(data):
    findings = []
    details = []
    occurrences = defaultdict(int)
    for item in sorted(data.get("results", []), key=lambda item: (item["filename"], item["line_number"], item["test_id"])):
        anchor = (item["filename"], item["test_id"], item.get("scope", "<module>"))
        occurrences[anchor] += 1
        fingerprint = sha256(json.dumps([*anchor, occurrences[anchor]], separators=(",", ":")).encode()).hexdigest()[:24]
        needs_review = item["test_id"] == "B324"
        status = "needs_review" if needs_review else "open"
        note = f"Bandit {item['test_id']} ({item['issue_confidence']} confidence): {item['issue_text']} Not automatically fixed."
        if needs_review:
            note += " Crypto output changes require review."
        finding = Finding(id=f"{item['test_id']}-{fingerprint}", file=item["filename"], line=item["line_number"],
                          severity=item["issue_severity"], status=status, note=note)
        findings.append(finding)
        details.append({**finding.model_dump(), "cwe": item.get("issue_cwe"),
                        "confidence": item["issue_confidence"], "scanner": "bandit", "scanner_test": item["test_id"],
                        "scope": item.get("scope", "<module>"), "description": item["issue_text"],
                        "column": item.get("col_offset"),
                        "verification_status": "potential_risk_not_confirmed", "proposed_fix": RECOMMENDATIONS.get(item["test_id"], "Review context and behavior before applying a fix.")})
    return findings, details
