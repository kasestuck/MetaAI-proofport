"""Explicit offline developer entry point; never pulls images or calls models."""

import argparse
import json
from pathlib import Path

from backend.php.pipeline import PHPJob, execute
from backend.php.receipts import ROOT, DEMO, PROFILES, verify_demo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify-demo", "migration", "compatibility", "audit"))
    parser.add_argument("--project", type=Path, default=ROOT / DEMO)
    parser.add_argument("--source", default="7.4", choices=("7.4", "8.3"))
    parser.add_argument("--target", default="8.3", choices=("7.4", "8.3"))
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--security-fixture", type=Path)
    parser.add_argument("--level", choices=("syntax", "tests", "behavior"), default="behavior")
    args = parser.parse_args()
    if args.operation == "verify-demo":
        receipt, result = verify_demo()
        print(json.dumps({"receipt": "backend/.work/php_registry.json", "artifact_id": receipt["artifact_id"], "checks": receipt["checks"], "golden_cases": receipt["golden_cases"], "target_tests": receipt["target_tests"]}, indent=2))
        return 0
    demo = args.project.absolute() == ROOT / DEMO
    result, artifact = execute(PHPJob(args.project, operation=args.operation, source_version=args.source,
        target_version=None if args.operation == "audit" else args.target,
        cases=args.cases or (ROOT / PROFILES / "cases.json" if demo and args.operation != "audit" else None),
        fixture=args.fixture or (ROOT / PROFILES / "migration.json" if demo and args.operation == "migration" else None),
        security_fixture=args.security_fixture, verification_level=args.level))
    print(json.dumps({"status": result["status"], "error": result.get("error"), "artifact_id": artifact.name,
        "syntax_passed": result["syntax_passed"], "tests_passed": result["tests_passed"], "behavior_verified": result["behavior_verified"]}, indent=2))
    return int(result["status"] != "done")


if __name__ == "__main__":
    raise SystemExit(main())
