"""Transactional offline PHP fixtures. Rollback retains the previous accepted copy."""

import difflib
from hashlib import sha256
import json

from backend.core.projects import copy_project
from backend.php.fixtures import constant_command_policy
from backend.php.protocol import relative_php
from backend.php.runtime import source_hashes
from backend.php.security import scan_php
from backend.php.verification import verify


def verify_fixes(*, working, original, original_hashes, artifacts, profile, golden, baseline_tests, executor, evidence, proposals_file=None, generator=None):
    if (proposals_file is None) == (generator is None): raise ValueError("Select exactly one explicit proposal source")
    mode = getattr(generator, "mode", "fixture")
    if mode not in {"fixture", "mock", "replay"}: raise ValueError("Live PHP security generation is disabled")
    if generator is None:
        data = json.loads(proposals_file.read_text(encoding="utf-8"))
        if data.get("mode") != "fixture" or data.get("not_ai") is not True or not isinstance(data.get("proposals"), list) or len(data["proposals"]) > 8:
            raise ValueError("Only bounded explicit PHP security fixtures are allowed")
    initial = scan_php(working, evidence)
    decisions = {f["id"]: dict(f) for f in initial["findings"]}
    def proposals():
        if generator is None:
            yield from data["proposals"]
            return
        baseline = verify(executor, working, "8.3", profile=profile, golden=golden, baseline_tests=baseline_tests)
        if not baseline["passed"] or initial["errors"]:
            from backend.languages.base import AdapterError
            raise AdapterError("needs_review", "Insufficient passing baseline/scan coverage; no model patch may be applied.")
        for finding in initial["findings"]:
            source = (working / finding["file"]).read_text(encoding="utf-8")
            item = generator.generate(finding, source)
            if item is None: continue
            if item.finding_id != finding["id"] or item.mode != mode: raise ValueError("Unbound PHP proposal")
            yield {**item.model_dump(), "file":finding["file"], "scanner_test":finding["scanner_test"], "scope":finding["scope"],
                   "source_sha256":sha256(source.encode()).hexdigest(), "policy":"constant_argv"}
    attempts, accepted, last_checks = [], [], None
    for index, proposal in enumerate(proposals()):
        relative_php(proposal["file"])
        candidates = [f for f in decisions.values() if f["file"] == proposal["file"] and f["scanner_test"] == proposal["scanner_test"] and f["scope"] == proposal["scope"] and f["status"] != "fixed"]
        if len(candidates) != 1: raise ValueError("Security fixture must identify exactly one current finding")
        finding = candidates[0]
        before = source_hashes(working)
        old = (working / proposal["file"]).read_bytes()
        new = proposal.get("proposed_code")
        if sha256(old).hexdigest() != proposal.get("source_sha256") or not isinstance(new, str) or not 1 <= len(new.encode()) <= 262144:
            raise ValueError("PHP security proposal is not source-hash bound")
        attempt_root = artifacts / ("attempt_%02d" % (index + 1)); attempt_root.mkdir()
        candidate = attempt_root / "project"; copy_project(working, candidate)
        (candidate / proposal["file"]).write_bytes(new.encode())
        checks = verify(executor, candidate, "8.3", profile=profile, golden=golden, baseline_tests=baseline_tests)
        rescan = scan_php(candidate, evidence) if checks["syntax"]["passed"] else None
        supported = constant_command_policy(old.decode("utf-8"), new, proposal)
        anchor = lambda f: (f["scanner_test"], f["file"], f["scope"])
        current_scan = scan_php(working)
        removed = rescan is not None and anchor(finding) not in {anchor(f) for f in rescan["findings"]}
        no_new = rescan is not None and {anchor(f) for f in rescan["findings"]} <= {anchor(f) for f in current_scan["findings"]}
        coverage_ok = rescan is not None and not rescan["errors"] and not current_scan["errors"] and rescan["coverage"] == current_scan["coverage"] == "limited_lexical"
        originals_ok = source_hashes(original) == original_hashes
        previous_ok = source_hashes(working) == before
        accepted_patch = supported and checks["passed"] and removed and no_new and coverage_ok and originals_ok and previous_ok
        needs_review = proposal.get("behavior_impact") == "changes" or bool(proposal.get("review_areas")) or (checks["syntax"]["passed"] and proposal.get("behavior_impact") == "unknown") or (checks["passed"] and not supported)
        if mode != "fixture" and checks["syntax"]["passed"] and (not checks["passed"] or not coverage_ok): needs_review = True
        status = "fixed" if accepted_patch else "needs_review" if needs_review else "fix_reverted"
        reasons = []
        if not checks["passed"]: reasons.append("Verification failed; candidate rejected.")
        if not supported: reasons.append("Outside the supported constant-argv policy; behavior/API/configuration changes require review.")
        if not removed: reasons.append("Target warning was not confirmed removed.")
        if not no_new: reasons.append("No-new-warning condition was not confirmed.")
        if not coverage_ok: reasons.append("Scanner coverage has errors or is incomplete; no automatic acceptance.")
        # Do not put credential-containing source literals into exported diffs.
        secret_file = any(f["file"] == proposal["file"] and f["scanner_test"] == "PHP-SECRET" for f in initial["findings"])
        diff = "Diff withheld: possible embedded credential in this file; inspect the retained copy privately." if secret_file else "".join(difflib.unified_diff(old.decode().splitlines(True), new.splitlines(True), fromfile="before", tofile="candidate"))
        attempt = {"finding_id": finding["id"], "mode": mode, "not_ai": True, "explanation": proposal.get("explanation", "Offline proposal"),
                   "status": status, "applied": bool(accepted_patch), "rolled_back": not accepted_patch, "diff": diff, "checks": checks,
                   "security_rescan": {"ran": rescan is not None, "target_removed": removed, "no_new_findings": no_new},
                   "originals_unchanged": originals_ok, "previous_copy_unchanged": previous_ok, "reasons": reasons}
        attempts.append(attempt); decisions[finding["id"]]["status"] = status
        (attempt_root / "attempt.json").write_text(json.dumps(attempt, indent=2), encoding="utf-8")
        evidence.append("security_fix" if accepted_patch else "fix_reverted", json.dumps({"language": "php", "finding_id": finding["id"], "status": status,
                                                                                       "mode": mode, "fixture": mode == "fixture", "checks_passed": bool(checks["passed"]), "rolled_back": not accepted_patch}, sort_keys=True))
        if not originals_ok or not previous_ok: raise ValueError("Original/accepted project changed during security verification")
        if accepted_patch:
            working, last_checks = candidate, checks; accepted.append(finding["id"])
    final = scan_php(working, evidence)
    return working, {"mode": mode, "not_ai": True, "isolation": "docker", "attempts": attempts,
                     "findings_before": initial["findings"], "findings_after": final["findings"], "decisions": list(decisions.values()),
                     "fixed": accepted, "needs_review": [f["id"] for f in decisions.values() if f["status"] == "needs_review"],
                     "rejected": [a["finding_id"] for a in attempts if not a["applied"]], "source_unchanged": source_hashes(original) == original_hashes,
                     "evidence_chain_intact": evidence.verify(), "verified": True, "scan_after": {"results": final["findings"], "errors": final["errors"]}}, last_checks
