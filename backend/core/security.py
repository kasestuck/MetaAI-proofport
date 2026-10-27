"""Real, offline Bandit scan. Findings are potential risks, never auto-fixed."""

import json
from pathlib import PurePosixPath

from backend.core.models import Finding
from backend.sandbox.runner import SandboxError


SCANNER_IMAGE = "proofport-bandit:1.8.6"


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
    return data


def findings_for(data):
    findings = []
    details = []
    for index, item in enumerate(data.get("results", []), 1):
        needs_review = item["test_id"] == "B324"
        status = "needs_review" if needs_review else "open"
        note = f"Bandit {item['test_id']} ({item['issue_confidence']} confidence): {item['issue_text']} Not automatically fixed."
        if needs_review:
            note += " Crypto output changes require review."
        finding = Finding(id=f"{item['test_id']}-{index}", file=item["filename"], line=item["line_number"],
                          severity=item["issue_severity"], status=status, note=note)
        findings.append(finding)
        details.append({**finding.model_dump(), "cwe": item.get("issue_cwe"),
                        "confidence": item["issue_confidence"], "scanner": "bandit", "scanner_test": item["test_id"],
                        "verification_status": "static_finding_only", "proposed_fix": "Review context and behavior before applying a fix."})
    return findings, details
