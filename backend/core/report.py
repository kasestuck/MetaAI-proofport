"""Portable HTML and JSON exports, with the contract state preserved."""

from html import escape
import json

from backend.core.runs import Run


def report_data(run: Run) -> dict:
    real = bool(run.verification)
    notice = (
        f"REAL Docker execution; provider={run.execution_mode}; status={run.state.status}. "
        "Fixture candidates are not AI migration. Verification covers only the recorded inputs and existing tests. "
        "Potential security findings are not automatically fixed; zero findings would not prove complete safety."
        if real else (
            "SIMULATED migration, tests, security fixes, tokens and costs. File hashes and evidence chain are real. No source was executed or modified."
            if run.simulation else "STATIC INVENTORY ONLY. Dynamic verification and security scanning did not run. No migration was performed or verified. Zero findings means not scanned, not secure. No source was executed or modified."
        )
    )
    return {
        "simulation": run.simulation,
        "notice": notice,
        "state": run.state.snapshot(),
        "settings": {"pipeline": "simulation" if run.simulation else run.execution_mode, "model": run.verification.get("model"), "max_iterations": run.max_iterations},
        "allowed_differences": [{"case": comparison["id"], **difference} for comparison in run.verification.get("comparisons", []) for difference in comparison["allowed_differences"]],
        "verification": run.verification,
        "events": run.evidence.since(0),
    }


def render_html(data: dict) -> str:
    state = data["state"]
    real = bool(data.get("verification"))
    title = "Proofport simulated run report" if data["simulation"] else ("Proofport Docker verification report" if real else "Proofport unverified source inventory")
    tests_label = "Simulated tests" if data["simulation"] else ("Recorded cases passed" if real else "Executed tests (unavailable)")
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
        f'{modules}</table><h2>Full evidence and metrics</h2><pre>{payload}</pre></html>'
    )
