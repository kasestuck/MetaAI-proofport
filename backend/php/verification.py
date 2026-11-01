"""Finite, independently reported syntax/tests/golden checks on one immutable copy."""

import json
from uuid import uuid4

from backend.php.protocol import compare
from backend.php.runtime import source_hashes


def test_runner(project):
    if (project / "tests/proofport.php").is_file(): return "proofport"
    if any((project / n).is_file() for n in ("phpunit.xml", "phpunit.xml.dist", "phpunit.dist.xml")):
        return "phpunit"  # Missing/incompatible dependencies fail; never auto-install/fallback.
    raise ValueError("No supported local PHP test suite")


def verify(executor, project, version, *, profile=None, golden=None, baseline_tests=None, level="behavior"):
    before = source_hashes(project)
    checks = {"syntax": executor.lint(project, version), "existing_tests": {"ran": False, "passed": None},
              "golden": {"ran": False, "passed": None}, "checked_hashes": before}
    if checks["syntax"]["passed"]:
        if level in {"tests", "behavior"}:
            tests = executor.tests(project, version, test_runner=test_runner(project))
            checks["existing_tests"] = {"ran": True, **tests}
            if baseline_tests and {o["id"] for o in tests["outcomes"]} != {o["id"] for o in baseline_tests["outcomes"]}:
                checks["existing_tests"]["passed"] = False
        if level == "behavior":
            observed = executor.cases(project, version, profile)
            comparisons = compare(profile, golden, observed)
            checks["golden"] = {"ran": True, "passed": bool(comparisons) and all(c["matches"] for c in comparisons),
                                "total": len(comparisons), "matched": sum(c["matches"] for c in comparisons), "comparisons": comparisons}
    checks["passed"] = checks["syntax"]["passed"] and (level == "syntax" or checks["existing_tests"]["passed"] is True) and (level != "behavior" or checks["golden"]["passed"] is True)
    if source_hashes(project) != before: raise ValueError("Verified working copy changed during Docker checks")
    recordings = project.parent / (project.name + "-verification-" + uuid4().hex)
    recordings.mkdir()
    if checks["golden"]["ran"]:
        (recordings / "observed-cases.json").write_text(json.dumps(observed, indent=2), encoding="utf-8")
    checks["recording_id"] = recordings.name
    (recordings / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return checks
