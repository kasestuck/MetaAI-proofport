"""One synthetic, opt-in Meta request. Default is an offline readiness preview.

Never invoked by pytest collection, startup, preflight, Translator or frontend.
No source code is sent and generated text is never printed or executed.
"""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess

from dotenv import dotenv_values

from backend.llm.budget import LLMLimits, decimal_amount
from backend.llm.client import LLMClient, ModelUnavailable


ROOT = Path(__file__).resolve().parents[2]
SYSTEM = 'Return one JSON object with exactly one field: "proofport_smoke": "ok". No tools, code, explanations or other content.'
USER = "Confirm this synthetic API connectivity smoke test. No project migration or security fixes are requested."


def credential_git_check(root: Path, env_file: Path, key: str):
    """Never put the key in process arguments, stdout or a temporary file."""
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    tracked = [root / os.fsdecode(name) for name in result.stdout.split(b"\0") if name]
    if env_file.resolve() in {path.resolve() for path in tracked}:
        raise ModelUnavailable("Credential file is tracked by Git. Stop and arrange reviewed cleanup/rotation.", "tracked_credentials")
    if env_file.is_file() and env_file.resolve().is_relative_to(root.resolve()):
        ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", str(env_file.resolve())], cwd=root, capture_output=True)
        if ignored.returncode != 0:
            raise ModelUnavailable("Credential file must be ignored locally before a live smoke test.", "unignored_credentials")
    if key and any(key.encode() in path.read_bytes() for path in tracked if path.is_file()):
        raise ModelUnavailable("Credential found in tracked content. Stop and arrange reviewed cleanup/rotation.", "tracked_credentials")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-paid-api", action="store_true")
    parser.add_argument("--max-cost-usd", help="Explicit operator cap, at most 0.05 USD for this single smoke request")
    args = parser.parse_args(argv)
    client = None
    try:
        if args.execute and (not args.acknowledge_paid_api or args.max_cost_usd is None):
            raise ModelUnavailable("A paid request needs separate permission, --acknowledge-paid-api and --max-cost-usd.", "approval_required")
        if args.acknowledge_paid_api and not args.execute:
            raise ModelUnavailable("No execution requested. Omit the paid acknowledgment for a dry run.", "approval_required")
        maximum = decimal_amount(args.max_cost_usd or "0.01", positive=True)
        if maximum > decimal_amount("0.05"):
            raise ModelUnavailable("First-call smoke cap must not exceed 0.05 USD.", "invalid_budget")
        limits = LLMLimits(max_cost_usd=maximum)
        settings = {**dotenv_values(args.env_file), **os.environ}
        configured = {name: bool(settings.get(name)) for name in ("MODEL_API_KEY", "MODEL_NAME", "PRICE_IN_PER_MTOK", "PRICE_OUT_PER_MTOK")}
        if not args.execute:
            print(json.dumps({"executed": False, "provider_validated": False, "configured": configured,
                              "mode_is_live": settings.get("LLM_MODE") == "live", "limits": {**asdict(limits), "max_cost_usd": str(maximum)},
                              "notice": "Offline preview only. No SDK/client constructed or model request made."}))
            return 0
        if (settings.get("LLM_MODE") or "mock").strip().lower() != "live":
            raise ModelUnavailable("The smoke test requires explicit LLM_MODE=live; no mock fallback.", "live_not_selected")
        credential_git_check(ROOT, args.env_file, settings.get("MODEL_API_KEY") or "")
        client = LLMClient(args.env_file, allow_live=True, limits=limits)
        with client:
            answer = client.complete(SYSTEM, USER, json_mode=True)
            if json.loads(answer) != {"proofport_smoke": "ok"}:
                raise ModelUnavailable("Smoke response did not match the synthetic expected object.", "smoke_response_mismatch")
        print(json.dumps({"executed": True, "answer_validated": True, "scope": "One synthetic connectivity request only; not AI migration/security verification.",
                          "usage": [asdict(call) for call in client.calls], "budget": client.budget_snapshot()}))
        return 0
    except (ModelUnavailable, ValueError, OSError, subprocess.SubprocessError) as exc:
        # Never print provider exceptions, configuration values, prompts or content.
        error = exc if isinstance(exc, ModelUnavailable) else ModelUnavailable("Local smoke configuration or credential-safety check failed.", "smoke_configuration_error")
        result = {"ok": False, "error": {"code": error.code, "message": str(error)}}
        if client is not None:
            result["budget"] = client.budget_snapshot()
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
