"""Offline CLI; no SDK construction, project imports or automatic image pulls."""

import argparse
import asyncio
import json
from pathlib import Path

from backend.core.detection import detect
from backend.core.report import report_data
from backend.core.runs import RunError, RunStore
from backend.core.versions import ROOT, VersionRegistry


async def workflow(args):
    mode = "compatibility" if args.command == "check" else args.command
    settings = {"PROOFPORT_SOURCE_VERSION": args.source_version,
                "PROOFPORT_TARGET_VERSION": args.target_version,
                "PROOFPORT_VERIFY_RUNTIME": "1" if args.verify_runtime else "0",
                "PROOFPORT_CASES_FILE": args.cases}
    store = RunStore(ROOT, pipeline=mode, settings=settings)
    try:
        run_id = store.start(str(Path(args.path).resolve()), 1)
        await asyncio.gather(*list(store.tasks))
        data = report_data(store.get(run_id))
        print(json.dumps({"run_id": run_id, "artifact_directory": str(store.get(run_id).workspace), **data}, indent=2))
        return int(data["state"]["status"] != "done")
    finally:
        await store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    registry = commands.add_parser("registry", help="Local image metadata; --verify executes trusted runtime self-tests")
    registry.add_argument("--verify", metavar="VERSION")
    detection = commands.add_parser("detect", help="Static heuristics, never proof of compatibility")
    detection.add_argument("path")
    detection.add_argument("--source-version")
    for command in ("analyze", "audit", "check"):
        operation = commands.add_parser(command)
        operation.add_argument("path")
        operation.add_argument("--source-version")
        operation.add_argument("--target-version", required=command == "check")
        operation.add_argument("--verify-runtime", action="store_true", help="Run shipped self-tests for required local images; never pull")
        operation.add_argument("--cases", help="Authored JSON inputs, not expected outputs; check mode only")
    args = parser.parse_args(argv)
    try:
        if args.command == "registry":
            registry = VersionRegistry()
            if args.verify:
                registry.verify(args.verify)
            print(json.dumps(registry.snapshot(), indent=2))
            return 0
        if args.command == "detect":
            print(json.dumps(detect(Path(args.path), args.source_version), indent=2))
            return 0
        return asyncio.run(workflow(args))
    except (ValueError, OSError, RuntimeError, RunError) as exc:
        print(json.dumps({"error": {"code": getattr(exc, "code", "offline_workflow_failed"), "message": exc.message if isinstance(exc, RunError) else str(exc)}}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
