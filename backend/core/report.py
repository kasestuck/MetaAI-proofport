"""Portable HTML and JSON exports, with the contract state preserved."""

from html import escape
import json

from backend.core.runs import Run


def report_data(run: Run, *, status: str | None = None) -> dict:
    reported_status = status or run.state.status
    real = bool(run.verification) and not run.simulation and run.state.isolation == "docker"
    notice = (
        f"REAL Docker execution; provider={run.execution_mode}; status={reported_status}. "
        "Fixture candidates are not AI migration. Verification covers only the recorded inputs and existing tests. "
        "Security decisions require recorded behavior checks and policy review; zero scanner findings would not prove complete safety."
        if real else (
            "SIMULATED migration, tests, security fixes, tokens and costs. File hashes and evidence chain are real. No source was executed or modified."
            if run.simulation else "STATIC INVENTORY ONLY. Dynamic verification and security scanning did not run. No migration was performed or verified. Zero findings means not scanned, not secure. No source was executed or modified."
        )
    )
    if run.execution_mode in {"analyze", "audit", "compatibility"}:
        level = run.verification.get("compatibility", {}).get("level", "not_verified")
        notice = (f"Offline {run.execution_mode}; compatibility={level}; status={reported_status}. "
                  "No migration, source modifications, remediation or model calls. Completion is not proof of project compatibility. "
                  "Runtime self-tests certify only the shipped harness. Bandit findings are potential risks; parsing errors limit coverage.")
    if run.verification.get("language") == "php":
        notice = (f"PHP offline operation; mode={run.execution_mode}; status={reported_status}. "
                  "Authored fixtures are not AI migration or AI fixes. Syntax, tests and finite recorded behavior are separate checks. "
                  "The PHP lexical scanner reports potential risks, not confirmed exploits or complete security. "
                  + ("Static audit only; no project code executed." if run.spec.operation == "audit" else "Project execution used pinned Docker images; originals were not modified."))
    return {
        "simulation": run.simulation,
        "notice": notice,
        "state": {**run.state.snapshot(), "status": reported_status},
        "settings": {"pipeline": "simulation" if run.simulation else run.execution_mode, "model": run.verification.get("model"), "max_iterations": run.max_iterations},
        "allowed_differences": [{"case": comparison["id"], **difference} for comparison in run.verification.get("comparisons", []) for difference in comparison["allowed_differences"]],
        "verification": run.verification,
        "events": run.evidence.since(0),
    }


def _security_html(security):
    if not security:
        return ""
    def table(findings):
        rows = "".join(
            "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in (
                finding["id"], finding["file"] + ":" + str(finding["line"]),
                "CWE-" + str(finding["cwe"]["id"]) if finding.get("cwe") else "Unknown",
                finding["severity"], finding["confidence"], finding["status"], finding["description"], finding["proposed_fix"],
            )) + "</tr>" for finding in findings
        )
        return '<table><tr><th>ID</th><th>Location</th><th>CWE</th><th>Severity</th><th>Confidence</th><th>Status</th><th>Potential issue</th><th>Recommendation</th></tr>' + rows + '</table>'
    attempts = "".join(
        f'<article><h3>{escape(attempt["finding_id"])}: {escape(attempt["status"])}</h3>'
        f'<p>{escape(attempt["explanation"])}</p><p>Applied: {attempt["applied"]}; rolled back: {attempt["rolled_back"]}</p>'
        f'<p>{escape(" ".join(attempt["reasons"]))}</p>'
        f'<h4>Code changes (redacted)</h4><pre>{escape(attempt["diff"])}</pre>'
        f'<h4>Real checks / skipped-stage reasons</h4><pre>{escape(json.dumps(attempt.get("checks", {}), indent=2))}</pre></article>'
        for attempt in security["attempts"]
    )
    return (
        f'<section><h2>Security verification ({escape(security["mode"])})</h2>'
        '<p>Offline fixtures, not Meta AI. Scanner warnings are potential risks. Verified means the accepted project passed recorded tests; it does not mean every proposal was accepted or the project is fully secure.</p>'
        f'<p>Fixed: {len(security["fixed"])}; needs review: {len(security["needs_review"])}; rejected proposals: {len(security["rejected"])}</p>'
        f'<h3>Findings before fixes</h3>{table(security["findings_before"])}'
        f'<h3>Findings after fixes</h3>{table(security["findings_after"])}'
        f'<h3>Decisions, including resolved findings</h3>{table(security["decisions"])}'
        f'<h3>Attempts and evidence</h3>{attempts}</section>'
    )


def render_html(data: dict) -> str:
    state = data["state"]
    real = bool(data.get("verification")) and state["isolation"] == "docker" and not data["simulation"]
    title = "Proofport simulated run report" if data["simulation"] else ("Proofport Docker verification report" if real else "Proofport unverified source inventory")
    tests_label = "Simulated tests" if data["simulation"] else ("Recorded cases passed" if real else "Executed tests (unavailable)")
    verification = data.get("verification", {})
    universal = ""
    if verification.get("mode") in {"analyze", "audit", "compatibility"}:
        title = "Proofport offline " + verification["mode"] + " report"
        universal = ('<section><h2>Compatibility evidence</h2><pre>' + escape(json.dumps({
            "checks": verification.get("compatibility"), "version_detection": verification.get("version_detection"),
            "limitations": verification.get("limitations"), "runtime_registry": verification.get("registry"),
            "security_audit": verification.get("security_audit"), "findings": verification.get("security_details"),
        }, indent=2)) + '</pre></section>')
    modules = "".join(
        f"<tr><td>{escape(m['name'])}</td><td>{m['status']}</td>"
        f"<td>{m['iterations']}</td><td>{m['tests_passed']}/{m['tests_total']}</td></tr>"
        for m in state["modules"]
    )
    payload = escape(json.dumps(data, indent=2, ensure_ascii=False))
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        f'<title>{title}</title>'
        '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:0 20px}'
        'td,th{padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        f'<h1>{title}</h1><p>{escape(data["notice"])}</p>'
        f'<p>Status: {state["status"]}. Isolation: {state["isolation"]}. '
        f'Chain intact: {state["chain_intact"]}. Originals unchanged: {state["hashes"]["unchanged"]}.</p>'
        f'<table><tr><th>Module</th><th>Status</th><th>Iterations</th><th>{tests_label}</th></tr>'
        f'{modules}</table>{universal}{_security_html(data.get("verification", {}).get("security_fix"))}'
        f'<h2>Full evidence and metrics</h2><pre>{payload}</pre></html>'
    )
