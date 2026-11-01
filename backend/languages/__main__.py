"""Operator-only P6.1 PHP inventory. No image pull, migration or model calls."""

import argparse
import json
from pathlib import Path

from backend.core.evidence import Evidence
from backend.languages.base import AdapterError
from backend.languages.registry import LanguageRegistry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--language", choices=["php"], default="php")
    parser.add_argument("--source-version")
    parser.add_argument("--target-version")
    parser.add_argument("--lint-version", help="Explicit opt-in; requires an already installed official PHP image")
    args = parser.parse_args(argv)
    evidence = Evidence()
    try:
        adapter = LanguageRegistry().get(args.language)
        result = adapter.analyze(args.source, source_version=args.source_version, target_version=args.target_version, evidence=evidence)
        if args.lint_version:
            result = adapter.lint(args.source, version=args.lint_version, source_version=args.source_version,
                                  target_version=args.target_version, evidence=evidence)
        print(json.dumps({**result.public(), "evidence": evidence.since(0), "chain_intact": evidence.verify()}, ensure_ascii=True, indent=2))
        return 0 if result.verification.syntax_passed is not False else 1
    except (AdapterError, OSError, ValueError) as exc:
        print(json.dumps({"error": {"code": getattr(exc, "code", "analysis_unavailable"),
                                    "message": str(exc) if isinstance(exc, AdapterError) else "Analysis did not complete; no compatibility verdict."}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
