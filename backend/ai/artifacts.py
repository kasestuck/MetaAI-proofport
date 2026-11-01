"""Local JSON/HTML receipts and hash-chained artifact seals for PHP live trials."""

from html import escape
import json
from pathlib import Path

from backend.ai.first_live import digest, write
from backend.core.evidence import entry_hash
from backend.core.projects import linked


def html(report):
    heading = "PHP baseline preparation; no model request" if report["phase"] == "preparation" else "PHP live module verification"
    title = "Proofport PHP verification"
    if report.get("operation") == "security_fix":
        title = "Proofport security verification"
        heading = "Security baseline preparation; no model request" if report["phase"] == "preparation" else "Security proposal verification; inspect review decision"
    return '<!doctype html><meta charset="utf-8"><title>' + title + '</title><h1>' + heading + '</h1><pre>' + escape(json.dumps(report, sort_keys=True, indent=2)) + '</pre>'


def export(workspace, report, evidence, *, stem="report"):
    if stem not in {"baseline-report", "report"}: raise ValueError("Invalid report stem")
    if not evidence.verify(): raise ValueError("Evidence corrupted before report export")
    files = {p.relative_to(workspace).as_posix():digest(p) for p in workspace.rglob('*') if p.is_file()}
    evidence.append("artifacts_sealed", json.dumps({k:v for k,v in files.items() if k != evidence.path.name}, sort_keys=True))
    files[evidence.path.name] = digest(evidence.path)
    report.update(artifact_hashes=files, events=evidence.since(0), evidence_file=evidence.path.name, chain_intact=evidence.verify())
    write(workspace / (stem + '.json'), report)
    (workspace / (stem + '.html')).write_text(html(report), encoding='utf-8')
    write(workspace / (stem + '-receipt.json'), {stem + '.json':digest(workspace / (stem + '.json')),
                                               stem + '.html':digest(workspace / (stem + '.html'))})


def verify(workspace, original_check, *, stem="report"):
    workspace = Path(workspace).absolute()
    if any(linked(p) for p in (workspace, *workspace.parents)): raise ValueError("Linked report workspace")
    if stem not in {"baseline-report", "report"}: raise ValueError("Invalid report stem")
    receipt = json.loads((workspace / (stem + '-receipt.json')).read_text(encoding='utf-8'))
    if set(receipt) != {stem + '.json', stem + '.html'}: raise ValueError("Invalid report receipt")
    if any(digest(workspace / name) != value for name,value in receipt.items()): raise ValueError("Report changed")
    report = json.loads((workspace / (stem + '.json')).read_text(encoding='utf-8'))
    for name,value in report['artifact_hashes'].items():
        path = workspace / name
        if not path.resolve().is_relative_to(workspace.resolve()) or any(linked(p) for p in (path, *path.parents)):
            raise ValueError("Unsafe artifact path")
        if digest(path) != value: raise ValueError("Artifact changed")
    log = report['evidence_file']
    if log not in report['artifact_hashes']: raise ValueError("Evidence not sealed")
    events = [json.loads(line) for line in (workspace / log).read_text(encoding='utf-8').splitlines()]
    if events != report['events']: raise ValueError("Report evidence differs")
    previous = '0'*64
    for seq,event in enumerate(events,1):
        if event['seq'] != seq or event['prev_hash'] != previous or entry_hash(event) != event['entry_hash']:
            raise ValueError("Evidence chain mismatch")
        previous = event['entry_hash']
    if (workspace / (stem + '.html')).read_text(encoding='utf-8') != html(report): raise ValueError("HTML differs from JSON")
    original_check(report['original_hashes'])
    return True
