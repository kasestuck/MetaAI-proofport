"""Portable HTML and JSON exports, with the contract state preserved."""

from html import escape
import json

from backend.core.runs import Run


def report_data(run: Run) -> dict:
    return {
        "simulation": run.simulation,
        "notice": (
            "SIMULATED migration, tests, security fixes, tokens and costs. File hashes and evidence chain are real. No source was executed or modified."
            if run.simulation else "STATIC INVENTORY ONLY. Dynamic verification and security scanning did not run. No migration was performed or verified. Zero findings means not scanned, not secure. No source was executed or modified."
        ),
        "state": run.state.snapshot(),
        "settings": {"pipeline": "simulation" if run.simulation else "static_only", "model": None, "max_iterations": run.max_iterations},
        "allowed_differences": [],
        "events": run.evidence.since(0),
    }


def render_html(data: dict) -> str:
    state = data["state"]
    title = "Proofport simulated run report" if data["simulation"] else "Proofport unverified source inventory"
    tests_label = "Simulated tests" if data["simulation"] else "Executed tests (unavailable)"
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
