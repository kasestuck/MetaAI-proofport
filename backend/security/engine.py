"""Transactional fixes checked against Docker behavior and scans; live is opt-in."""

import ast
import base64
from copy import deepcopy
import difflib
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from uuid import uuid4

from backend.core.comparator import compare_cases
from backend.core.recorder import invoke, validate_cases
from backend.core.security import findings_for, scan
from backend.security.models import FixProposal
from backend.security.policy import PROTECTED, constant_argv_only, constant_shell_to_argv, review_reasons


def project_hashes(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()
            and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts)}


def checked_file(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in {"..", "."} for part in path.parts) or "\\" in relative or ":" in relative:
        raise ValueError("Security target must be a project-relative file.")
    target = root.joinpath(*path.parts)
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise ValueError("Security target must not traverse symbolic links.")
    if not target.resolve(strict=True).is_relative_to(root.resolve(strict=True)) or not target.is_file():
        raise ValueError("Security target escapes its working copy.")
    if "tests" in path.parts or path.name.startswith("test_") or target.suffix != ".py":
        raise ValueError("Security patches cannot edit tests or non-Python inputs.")
    return target


def _atomic_write(target, data):
    temporary = target.with_name(".proofport-" + uuid4().hex)
    try:
        temporary.write_bytes(data)
        temporary.chmod(stat.S_IMODE(target.stat().st_mode))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _secret_values(source, findings):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines = {finding["line"] for finding in findings if finding["scanner_test"] in {"B105", "B106", "B107"}}
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value and node.lineno in lines}


class SecurityFixEngine:
    def __init__(self, *, runner, working: Path, original: Path, original_hashes: dict,
                 artifacts: Path, cases: list, golden: list, existing_tests: dict, evidence,
                 runtime_version="3.12", extra_syntax_versions=(), live_session=None):
        images = {"2.7":"python:2.7", "3.12":"python:3.12-slim"}
        if runtime_version not in images or not isinstance(extra_syntax_versions, tuple) or any(v not in images for v in extra_syntax_versions):
            raise ValueError("Only explicitly checked Python runtimes are allowed")
        self.runtime_version, self.runtime_image = runtime_version, images[runtime_version]
        self.extra_syntax_images = tuple(images[v] for v in extra_syntax_versions)
        self.live_session = live_session
        self.runner, self.working, self.original = runner, working.resolve(), original.resolve()
        self.artifacts = artifacts.resolve()
        if (self.working == self.original or self.working.is_relative_to(self.original)
                or self.original.is_relative_to(self.working) or self.artifacts.is_relative_to(self.original)
                or self.artifacts.is_relative_to(self.working)):
            raise ValueError("Fixes and staging must be separate from original sources and the accepted project.")
        for root in (self.working, self.original):
            if any(path.is_symlink() for path in root.rglob("*")):
                raise ValueError("Security verification does not follow source links.")
        self.original_hashes = original_hashes
        self.cases = validate_cases(cases)
        self.golden, self.existing = golden, existing_tests
        if not golden or not existing_tests.get("tests_run") or any(t["status"] != "passed" for t in existing_tests["outcomes"]):
            raise ValueError("Nonempty, actually passing baseline tests and golden recordings are required.")
        self.evidence = evidence
        self.secrets = set()
        self.committed = {}

    def _redact(self, value):
        if isinstance(value, str):
            for secret in sorted(self.secrets, key=len, reverse=True):
                for form in {secret, repr(secret)[1:-1], json.dumps(secret)[1:-1], base64.b64encode(secret.encode()).decode()}:
                    value = value.replace(form, "[REDACTED]")
            return value
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        return value

    def _write(self, path, data):
        path.write_text(json.dumps(self._redact(data), indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")

    def _original_ok(self):
        try:
            return project_hashes(self.original) == self.original_hashes
        except OSError:
            return False

    def _verify(self, project):
        checks = {}
        compilation = invoke(self.runner, self.runtime_image, project, "compile", evidence=self.evidence)
        checks["syntax"] = {"ran": True, "passed": not compilation["errors"], "errors": compilation["errors"]}
        for image in self.extra_syntax_images:
            other = invoke(self.runner, image, project, "compile", evidence=self.evidence)
            checks.setdefault("additional_syntax", []).append({"image":image,"passed":not other["errors"],"errors":other["errors"]})
            if other["errors"]:
                checks["syntax"]["passed"] = False
                compilation["errors"].extend(other["errors"])
        if compilation["errors"]:
            for stage in ("golden", "existing_tests"):
                checks[stage] = {"ran": False, "passed": False, "reason": "Syntax check failed; no dynamic results invented."}
            return checks
        try:
            actual = invoke(self.runner, self.runtime_image, project, "cases", self.cases, self.evidence)["cases"]
            comparisons = compare_cases(self.golden, actual)
            matched = sum(case["matches"] for case in comparisons)
            checks["golden"] = {"ran": True, "passed": matched == len(self.golden), "matched": matched,
                                "total": len(self.golden), "comparisons": comparisons}
        except Exception as exc:
            checks["golden"] = {"ran": True, "passed": False, "error_type": type(exc).__name__}
        try:
            tests = invoke(self.runner, self.runtime_image, project, "tests", evidence=self.evidence)
            ids = [test["id"] for test in tests["outcomes"]]
            expected = {test["id"] for test in self.existing["outcomes"]}
            passed = (tests["tests_run"] == self.existing["tests_run"] == len(ids) == len(set(ids))
                      and set(ids) == expected and all(test["status"] == "passed" for test in tests["outcomes"]))
            checks["existing_tests"] = {"ran": True, "passed": passed, **tests}
        except Exception as exc:
            checks["existing_tests"] = {"ran": True, "passed": False, "error_type": type(exc).__name__}
        return checks

    @staticmethod
    def _passed(checks):
        return all(checks[stage]["passed"] for stage in ("syntax", "golden", "existing_tests"))

    def _attempt(self, finding, proposal, current_scan):
        if proposal.finding_id != finding["id"] or proposal.mode not in {"fixture", "mock", "replay", "live"}:
            raise ValueError("A bound proposal is required; live verification needs explicit finding approval.")
        current = project_hashes(self.working)
        target = checked_file(self.working, finding["file"])
        old_bytes = target.read_bytes()
        old = target.read_text(encoding="utf-8")
        if proposal.mode == "live":
            from backend.ai.provider import ModelSession, SecurityLiveApproval
            session = self.live_session
            if not isinstance(session, ModelSession) or session.mode != "live" or session.client.mode != "live" or not isinstance(session.live_approval, SecurityLiveApproval):
                raise ValueError("Live verification needs the explicitly approved security session")
            session.live_approval.validate(session.client, "python")
            approval = session.live_approval
            if (approval.runtime_version != self.runtime_version or approval.file != finding["file"]
                    or approval.finding_id != finding["id"] or approval.source_sha256 != sha256(old.encode()).hexdigest()
                    or not session.responses or session.responses[-1]["task"] != "security"
                    or session.responses[-1]["finding_id"] != finding["id"]
                    or session.responses[-1]["proposed_sha256"] != sha256(proposal.proposed_code.encode()).hexdigest()):
                raise ValueError("Live proposal differs from approved/generated source binding")
        attempt_id = uuid4().hex
        folder = self.artifacts / attempt_id
        folder.mkdir()
        staged = folder / "candidate"
        shutil.copytree(self.working, staged)
        new = old if proposal.proposed_code is None else proposal.proposed_code
        checked_file(staged, finding["file"]).write_text(new, encoding="utf-8")
        attempt = {
            "id": attempt_id, "finding_id": finding["id"], "file": finding["file"], "mode": proposal.mode,
            "ai_generated": proposal.mode == "live", "explanation": proposal.explanation, "behavior_impact": proposal.behavior_impact,
            "confidence": proposal.confidence, "review_areas": proposal.review_areas,
            "source_sha256": sha256(old.encode()).hexdigest(), "proposed_sha256": sha256(new.encode()).hexdigest(),
            "diff": "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=finding["file"], tofile=finding["file"])),
            "status": "open", "applied": False, "rolled_back": False, "reasons": [],
        }
        self.evidence.append("patch_applied", f"Staged {proposal.mode} attempt {attempt_id}; accepted copy is unchanged.", finding["file"])
        try:
            checks = self._verify(staged)
            attempt["checks"] = checks
            after_scan = scan(self.runner, staged, self.evidence)
            _, before_details = findings_for(current_scan)
            _, after_details = findings_for(after_scan)
            attempt["rescan"] = {"ran": True, "passed": not after_scan["errors"], "findings": after_details, "errors": after_scan["errors"]}
            attempt["original_unchanged"] = self._original_ok()
            target_remains = any(item["id"] == finding["id"] for item in after_details)
            attempt["target_warning_removed"] = not target_remains
            allowed_new = []
            new_findings = [item for item in after_details if item["id"] not in {item["id"] for item in before_details}]
            policy_ok = checks["syntax"]["passed"] and constant_shell_to_argv(old, new, finding["line"], finding.get("column"))
            if policy_ok:
                allowed_new = [item["id"] for item in new_findings if item["scanner_test"] == "B603" and item["severity"] == "LOW"
                               and item["file"] == finding["file"] and item["scope"] == finding["scope"]]
            escalated = [item for item in after_details for prior in before_details if item["id"] == prior["id"]
                         and {"LOW": 1, "MEDIUM": 2, "HIGH": 3}[item["severity"]] > {"LOW": 1, "MEDIUM": 2, "HIGH": 3}[prior["severity"]]]
            unsafe_new = [item for item in new_findings if item["id"] not in allowed_new] + escalated
            attempt["new_findings"] = new_findings
            attempt["contextually_triaged_new_ids"] = allowed_new
            reasons = review_reasons(finding, proposal, old, new) if checks["syntax"]["passed"] else []
            if not attempt["original_unchanged"]:
                attempt.update(status="fix_reverted", reasons=["Original file hash check failed."])
            elif not checks["syntax"]["passed"]:
                attempt.update(status="fix_reverted", reasons=["Candidate syntax failed; dynamic checks were not run."])
            elif not self._passed(checks):
                review = proposal.mode != "fixture" or proposal.behavior_impact != "preserves" or finding["scanner_test"] in PROTECTED
                attempt.update(status="needs_review" if review else "fix_reverted", reasons=["Real golden or existing tests changed/failed.", *reasons])
            elif after_scan["errors"]:
                attempt.update(status="needs_review" if proposal.mode != "fixture" else "fix_reverted", reasons=["Rescan is incomplete."])
            elif proposal.disposition == "false_positive":
                if (proposal.proposed_code is None and proposal.behavior_impact == "preserves" and not proposal.review_areas
                        and finding["scanner_test"] in {"B404", "B603"} and constant_argv_only(old) and target_remains):
                    attempt.update(status="false_positive", reasons=["Contextual subprocess advisory: literal absolute argv, shell=False, unchanged code and passing recorded behavior. Not a general scanner dismissal."])
                else:
                    attempt.update(status="open", reasons=["Insufficient independent evidence to dismiss this warning."])
            elif reasons:
                attempt.update(status="needs_review", reasons=reasons)
            elif unsafe_new:
                attempt.update(status="fix_reverted", reasons=["Rescan introduced/escalated unreviewed findings."])
            elif target_remains:
                attempt.update(status="fix_reverted", reasons=["Target warning remains after the candidate scan."])
            else:
                if project_hashes(self.working) != current:
                    raise RuntimeError("Accepted project changed during candidate verification.")
                self.committed.setdefault(finding["file"], target.read_bytes())
                _atomic_write(target, checked_file(staged, finding["file"]).read_bytes())
                attempt.update(status="fixed", applied=True, reasons=["Exact supported constant-shell to argv transformation; real syntax, golden, existing tests, original hashes and rescan passed. This is verified hardening, not proof of a previously exploitable vulnerability."])
                self.evidence.append("security_fix", f"Accepted {proposal.mode} candidate {attempt_id} for finding {finding['id']} after real checks.", finding["file"])
        except Exception as exc:
            if attempt["applied"]:
                _atomic_write(target, old_bytes)
                attempt.update(applied=False, rolled_back=True)
            attempt.update(status="fix_reverted", reasons=["Verification could not complete: " + type(exc).__name__])
        finally:
            if not attempt["applied"]:
                attempt["rolled_back"] = proposal.proposed_code is not None
                if project_hashes(self.working) != current:
                    raise RuntimeError("Rejected attempt altered the accepted project.")
                self.evidence.append("fix_reverted" if attempt["rolled_back"] else "security_finding", f"{proposal.mode} attempt {attempt_id}: {attempt['status']}; no candidate changes accepted.", finding["file"])
            attempt["accepted_copy_unchanged"] = project_hashes(self.working) == current
            attempt["original_unchanged"] = self._original_ok()
            self._write(folder / "attempt.json", attempt)
        return self._redact(attempt)

    def run(self, generator):
        mode = getattr(generator, "mode", "fixture")
        if mode not in {"fixture", "mock", "replay"}: raise ValueError("Offline generator required")
        self.artifacts.mkdir(parents=True, exist_ok=False)
        baseline_hashes = project_hashes(self.working)
        report = {"mode": mode, "ai_generated": False, "isolation": "docker", "status": "failed",
                  "attempts": [], "findings_before": [], "findings_after": [], "fixed": [], "needs_review": [], "rejected": []}
        history = {}
        try:
            baseline = scan(self.runner, self.working, self.evidence)
            _, details = findings_for(baseline)
            for file in {finding["file"] for finding in details}:
                source = checked_file(self.working, file).read_text(encoding="utf-8")
                self.secrets.update(_secret_values(source, [finding for finding in details if finding["file"] == file]))
            report["findings_before"] = deepcopy(details)
            history = {finding["id"]: deepcopy(finding) for finding in details}
            report["baseline_checks"] = self._verify(self.working)
            if baseline["errors"] or not self._passed(report["baseline_checks"]) or not self._original_ok():
                if mode != "fixture":
                    for item in history.values(): item.update(status="needs_review", note="Insufficient baseline/scan coverage; no model proposal may be accepted.")
                raise RuntimeError("Security verification requires a passing baseline and complete scan.")
            current_scan = baseline
            for finding in details:
                source = checked_file(self.working, finding["file"]).read_text(encoding="utf-8")
                proposal = generator.generate(deepcopy(finding), source)
                if proposal is None:
                    continue
                proposal = FixProposal.model_validate(proposal.model_dump() if isinstance(proposal, FixProposal) else proposal)
                if proposal.mode != mode: raise ValueError("Proposal provenance differs from generator")
                attempt = self._attempt(finding, proposal, current_scan)
                report["attempts"].append(attempt)
                history[finding["id"]].update(status=attempt["status"], verification_status="real_docker_" + mode + "_decision",
                                               note=" ".join(attempt["reasons"]))
                if attempt["applied"]:
                    current_scan = scan(self.runner, self.working, self.evidence)
                    _, current_details = findings_for(current_scan)
                    for new in current_details:
                        if new["id"] in attempt.get("contextually_triaged_new_ids", []):
                            new.update(status="false_positive", verification_status="constant_argv_context_verified",
                                       note="Literal absolute argv, no shell; independently checked transformation and real behavior tests. Advisory retained, not treated as a confirmed vulnerability.")
                            history[new["id"]] = new
            report["final_checks"] = self._verify(self.working)
            final_scan = scan(self.runner, self.working, self.evidence)
            _, final_details = findings_for(final_scan)
            if final_scan["errors"] or not self._passed(report["final_checks"]) or not self._original_ok():
                raise RuntimeError("Final security validation failed.")
            report["status"] = "verified"
            report["scan_after"] = final_scan
            report["findings_after"] = [{**item, "status": history.get(item["id"], item)["status"],
                                         "verification_status": history.get(item["id"], item)["verification_status"],
                                         "note": history.get(item["id"], item)["note"]} for item in final_details]
        except Exception as exc:
            report["error_type"] = type(exc).__name__
            report["error_code"] = getattr(exc, "code", "security_verification_failed")
            for relative, original in self.committed.items():
                _atomic_write(checked_file(self.working, relative), original)
            for finding in history.values():
                if finding["status"] == "fixed":
                    finding.update(status="fix_reverted", note="Final validation failed; accepted fixture changes were rolled back.")
            for attempt in report["attempts"]:
                if attempt["applied"]:
                    attempt.update(status="fix_reverted", applied=False, rolled_back=True)
            self.evidence.append("fix_reverted", "Security pass failed; committed security changes restored to the verified migration baseline.")
        report["decisions"] = list(history.values())
        report["fixed"] = [finding["id"] for finding in history.values() if finding["status"] == "fixed"]
        report["needs_review"] = [finding["id"] for finding in history.values() if finding["status"] == "needs_review"]
        report["rejected"] = [attempt["id"] for attempt in report["attempts"] if attempt["rolled_back"]]
        report["original_unchanged"] = self._original_ok()
        self.evidence.append("test_result", f"Offline security verification: status={report['status']}, accepted={len(report['fixed'])}, needs_review={len(report['needs_review'])}; no model calls.")
        report["evidence_chain_intact"] = self.evidence.verify()
        if not report["evidence_chain_intact"] or not report["original_unchanged"]:
            report["status"] = "failed"
            for relative, original in self.committed.items():
                _atomic_write(checked_file(self.working, relative), original)
            for attempt in report["attempts"]:
                if attempt["applied"]:
                    attempt.update(status="fix_reverted", applied=False, rolled_back=True)
            for finding in report["decisions"]:
                if finding["status"] == "fixed":
                    finding.update(status="fix_reverted", note="Original hashes or evidence integrity failed; accepted changes restored.")
            report["fixed"] = []
            report["findings_after"] = []  # No verified post-rollback scan can be asserted.
            self.evidence.append("fix_reverted", "Original hashes or evidence integrity failed; all committed fixture changes restored. Original files and log history were not repaired or hidden.")
        report["baseline_project_hashes"] = baseline_hashes
        report["accepted_project_hashes"] = project_hashes(self.working)
        report["rejected"] = [attempt["id"] for attempt in report["attempts"] if attempt["rolled_back"]]
        for attempt in report["attempts"]:
            self._write(self.artifacts / attempt["id"] / "attempt.json", attempt)
        self._write(self.artifacts / "security_report.json", report)
        return self._redact(report)
