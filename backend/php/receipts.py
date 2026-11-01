"""Explicit demo E2E receipts; GET/preflight never executes tests or writes them."""

from hashlib import sha256
import json
from pathlib import Path

from backend.core.projects import linked
from backend.languages.base import AdapterError
from backend.languages.runtimes import IMAGE_ID, PHP_RUNTIMES
from backend.php.protocol import digest


ROOT = Path(__file__).resolve().parents[2]
DEMO = "tests/fixtures/php_shop"
PROFILES = "tests/fixtures/php_profiles"
CHECKS = {"source_syntax", "source_tests", "golden_recorded", "target_syntax", "target_tests", "behavior",
          "security_scan", "supported_fix", "syntax_rollback", "behavior_rejection", "originals_unchanged", "evidence", "reports", "zero_model_calls"}


def revision(root=ROOT):
    files = [*sorted((root / "backend/php").glob("*.py")), root / "backend/sandbox/php_harness.php",
             *sorted((root / "backend/languages").glob("*.py")), root / "backend/core/control_models.py",
             root / "backend/core/projects.py", root / "backend/core/control.py", root / "backend/core/runs.py",
             root / "backend/core/report.py", root / "backend/sandbox/runner.py",
             *sorted((root / PROFILES).glob("*.json"))]
    return digest({p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in files})


def read_receipt(root=ROOT):
    try:
        path = root / "backend/.work/php_registry.json"
        if linked(path) or any(linked(p) for p in path.parents if p.is_relative_to(root)): return None
        if path.stat().st_size > 131072: return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("receipt_hash") != digest({k:v for k,v in data.items() if k != "receipt_hash"}): return None
        pins = data.get("images")
        if not isinstance(pins, dict) or set(pins) != {r.version for r in PHP_RUNTIMES} or any(not isinstance(v, str) or not IMAGE_ID.fullmatch(v) for v in pins.values()): return None
        if data.get("revision") != revision(root) or not isinstance(data.get("checks"), dict) or set(data["checks"]) != CHECKS or any(v is not True for v in data["checks"].values()): return None
        from backend.php.runtime import source_hashes
        if source_hashes(root / DEMO) != data.get("source_hashes"): return None
        name = data.get("artifact_id", "")
        if not isinstance(name,str) or not name.startswith("php-run-") or not name.removeprefix("php-run-").isalnum(): return None
        artifact = root / "backend/.work" / name
        if any(linked(p) for p in (artifact,*artifact.parents) if p.is_relative_to(root)): return None
        for file, expected in data["artifacts"].items():
            if file not in {"report.json", "report.html", "evidence.jsonl", "golden.json"}: return None
            if linked(artifact / file): return None
            if sha256((artifact / file).read_bytes()).hexdigest() != expected: return None
        if set(data["artifacts"]) != {"report.json", "report.html", "evidence.jsonl", "golden.json"}: return None
        if type(data.get("golden_cases")) is not int or data["golden_cases"] < 1 or type(data.get("target_tests")) is not int or data["target_tests"] < 1: return None
        return data
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def supported(root, states):
    receipt = read_receipt(root)
    if receipt is None: return {"receipt_valid": False, "migration": False, "compatibility": False, "audit": False}
    pins = receipt.get("images", {})
    runtime_ready = all(any(s["version"] == r.version and s.get("available") is True and s.get("image_id") == pins.get(r.version) for s in states) for r in PHP_RUNTIMES)
    return {"receipt_valid": True, "migration": runtime_ready, "compatibility": runtime_ready, "audit": True}


def verify_demo(root=ROOT):
    from backend.php.pipeline import PHPJob, execute
    from backend.php.runtime import local_images, source_hashes
    from backend.sandbox.runner import DockerRunner
    runner = DockerRunner(); images = local_images(runner)
    result, artifact = execute(PHPJob(root / DEMO, cases=root / PROFILES / "cases.json", fixture=root / PROFILES / "migration.json",
                                     security_fixture=root / PROFILES / "security.json", max_iterations=1), runner=runner, images=images)
    fix = result.get("security_fix", {}); attempts = fix.get("attempts", [])
    checks = {"source_syntax": result.get("source_syntax", {}).get("passed") is True,
              "source_tests": result.get("source_tests", {}).get("passed") is True,
              "golden_recorded": result.get("golden_case_count", 0) > 0,
              "target_syntax": result.get("syntax_passed") is True, "target_tests": result.get("tests_passed") is True,
              "behavior": result.get("behavior_verified") is True,
              "security_scan": len({f["scanner_test"] for f in result.get("security_before", {}).get("findings", [])}) == 8,
              "supported_fix": len(fix.get("fixed", [])) == 1,
              "syntax_rollback": any(a["rolled_back"] and a["checks"]["syntax"]["passed"] is False for a in attempts),
              "behavior_rejection": any(a["rolled_back"] and a["checks"]["golden"]["passed"] is False and a["status"] == "needs_review" for a in attempts),
              "originals_unchanged": result.get("originals_unchanged") is True,
              "evidence": result.get("chain_intact") is True,
              "reports": all((artifact / n).is_file() and (artifact / n).stat().st_size for n in ("report.json", "report.html", "golden.json")),
              "zero_model_calls": result.get("model_calls") == 0 and result.get("ai_migration") is False}
    checks = {k: bool(v) for k,v in checks.items()}
    if result["status"] != "done" or not all(checks.values()):
        raise AdapterError("php_e2e_not_verified", "PHP demo proof failed; receipt was not written. Retained artifact: " + artifact.name)
    data = {"revision": revision(root), "images": images, "checks": checks, "source_hashes": source_hashes(root / DEMO),
            "artifact_id": artifact.name, "golden_cases": result["golden_case_count"], "target_tests": result["target_tests"]["tests_run"],
            "scope": "Owned offline fixture demo and finite recorded inputs, not arbitrary PHP projects, AI migration or complete security.",
            "artifacts": {n:sha256((artifact/n).read_bytes()).hexdigest() for n in ("report.json", "report.html", "evidence.jsonl", "golden.json")}}
    data["receipt_hash"] = digest(data)
    output = root / "backend/.work/php_registry.json"; output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix(".json.tmp"); temporary.write_text(json.dumps(data,indent=2),encoding="utf-8"); temporary.replace(output)
    return data, result
