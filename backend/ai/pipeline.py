"""One immutable AI job delegates to the existing Python/PHP verification engines.

Only explicit bounded mock/replay clients are allowed. This is real Docker
verification of offline model responses, never a claim of real Meta generation.
"""

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from uuid import uuid4

from backend.ai.provider import ModelSession, StructuredTranslator
from backend.core.evidence import Evidence
from backend.core.projects import linked
from backend.languages.base import AdapterError, inventory
from backend.llm.client import ModelUnavailable
from backend.sandbox.runner import DockerRunner
from backend.security.providers import LLMFixGenerator


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AIJob:
    source: Path
    language: str
    cases: Path
    source_version: str
    target_version: str
    max_iterations: int = 1
    security_fixes: bool = False
    security_rules: tuple[str, ...] = ()
    security_scopes: tuple[str, ...] = ()
    max_security_proposals: int = 2

    def __post_init__(self):
        if (self.language, self.source_version, self.target_version) not in {("python","2.7","3.12"),("php","7.4","8.3")}:
            raise ValueError("AI adapters cover only Python 2.7→3.12 and PHP 7.4→8.3")
        if type(self.max_iterations) is not int or not 1 <= self.max_iterations <= 5 or type(self.security_fixes) is not bool:
            raise ValueError("Invalid AI iteration/security settings")
        if type(self.max_security_proposals) is not int or not 1 <= self.max_security_proposals <= 4:
            raise ValueError("Security proposals must be bounded to 1..4")
        for entries in (self.security_rules, self.security_scopes):
            if not isinstance(entries, tuple) or len(entries) > 16 or any(not isinstance(s,str) or not 1 <= len(s) <= 128 for s in entries):
                raise ValueError("Use immutable bounded finding selectors")


def execute(job, *, client, runner=None, work_root=ROOT):
    session = ModelSession(client, job.language)  # No SDK or project execution.
    source, files = inventory(job.source)
    if not source.is_dir(): raise AdapterError("source_not_found", "AI migration requires a project directory with existing tests.")
    other = {".php", ".phtml"} if job.language == "python" else {".py"}
    if any(p.suffix.lower() in other for p in files): raise AdapterError("language_mismatch", "Mixed-language model jobs require review.")
    for path in files:
        # Refuse credentials in source, data or filenames before copies/execution.
        if client._api_key and (client._api_key in str(path) or client._api_key.encode() in path.read_bytes()):
            raise ModelUnavailable("Credential found in project input; no model request sent.", "credential_in_prompt")
    work_root = Path(work_root).absolute()
    destination = work_root / "backend/.work" / ("ai-run-" + uuid4().hex)
    if any(linked(p) for p in (destination, *destination.parents)) or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Separate link-free AI artifact workspace required")
    evidence = Evidence(); session.evidence = evidence
    translator = StructuredTranslator(session)
    generator = LLMFixGenerator(session=session, rules=job.security_rules, scopes=job.security_scopes,
        max_proposals=job.max_security_proposals) if job.security_fixes else None
    runner = runner or DockerRunner()
    try:
        if job.language == "php":
            from backend.php.pipeline import PHPJob, execute as php_execute
            data, artifact = php_execute(PHPJob(source, cases=Path(job.cases), max_iterations=job.max_iterations),
                runner=runner, artifacts=destination, evidence=evidence, translator=translator, security_generator=generator)
        else:
            from backend.core.models import Metrics, RunState
            from backend.core.runs import Run, hashes_for
            from backend.core.pipeline import execute as python_execute
            before = hashes_for(source)
            run = Run(RunState(modules=[], hashes={**before,"unchanged":None}, metrics=Metrics()), source, before, {}, job.max_iterations,
                      runner=runner, evidence=evidence)
            settings = {"PROOFPORT_CASES_FILE":str(Path(job.cases).absolute())}
            python_execute(run, destination.name, work_root, settings, translator.mode, translator=translator, security_generator=generator)
            artifact = run.workspace or destination
            artifact.mkdir(parents=True, exist_ok=True)
            if evidence.path is None: evidence.bind(artifact / "evidence.log")
            status = run.pending_status or "failed"
            if status != "done":
                for module in run.state.modules: module.status = "failed"
            run.state.status = status
            last = run.verification.get("iterations", [])[-1:]
            checks = last[0] if last else {}
            data = {**run.verification, "language":"python", "status":status,
                    "execution_mode":translator.mode, "source_version":job.source_version, "target_version":job.target_version,
                    "original_hashes":before, "originals_unchanged":run.state.hashes["unchanged"], "chain_intact":evidence.verify(),
                    "state":run.state.snapshot(), "error":run.state.error.model_dump() if run.state.error else None,
                    "syntax_passed":checks.get("syntax_passed"), "tests_passed":checks.get("tests_passed"),
                    "behavior_verified":checks.get("behavior_verified"), "isolation":run.state.isolation}
        data.update(provider_validated=False, live_enabled=False, model_calls=0, ai_migration=False,
                    response_calls=len(client.calls), response_attempts=len(client.attempts), response_mode=client.mode,
                    llm_budget=client.budget_snapshot(), responses=session.responses,
                    notice="Offline model-response workflow; inspect which Docker checks ran. No Meta AI request or AI migration/remediation is claimed.")
        # Repeat critical invariants at export, including a possible edit after
        # the language worker's own final check. Never repair/hide a corrupt log.
        try:
            if job.language == "python":
                from backend.core.runs import hashes_for
                current = hashes_for(source)
            else:
                from backend.php.runtime import source_hashes
                current = source_hashes(source)
            unchanged = current == data["original_hashes"]
        except Exception:
            unchanged = False
        data["originals_unchanged"] = data.get("originals_unchanged") is True and unchanged
        data["chain_intact"] = data.get("chain_intact") is True and evidence.verify()
        if not data.get("chain_intact") or not data.get("originals_unchanged"):
            data["status"] = "failed"
            data["error"] = {"code":"evidence_corrupted" if not data["chain_intact"] else "source_changed", "message":"Final evidence/original integrity failed; no result may be trusted."}
            data.update(syntax_passed=None, tests_passed=None, behavior_verified=None)
            if job.language == "python" and not run.verification.get("rollback"):
                from backend.core.pipeline import _rollback_model
                _rollback_model(run, artifact, artifact / "copy", artifact / "migrated", None)
                if run.verification.get("rollback"): data["rollback"] = run.verification["rollback"]
            data.pop("accepted_copy", None); data.pop("accepted_hashes", None)
            if "state" in data:
                data["state"].update(status="failed", chain_intact=data["chain_intact"], error=data["error"])
                data["state"]["hashes"]["unchanged"] = data["originals_unchanged"]
                for module in data["state"]["modules"]: module["status"] = "failed"
        data = session.private.clean(data)
        exported = {**data, "events":evidence.since(0)}
        (artifact / "report.json").write_text(json.dumps(exported, indent=2), encoding="utf-8")
        (artifact / "report.html").write_text('<!doctype html><meta charset="utf-8"><title>Proofport offline model verification</title><h1>Offline model responses; not Live AI</h1><pre>' + escape(json.dumps(exported,indent=2)) + '</pre>',encoding="utf-8")
        return data, artifact
    finally:
        client.close()
