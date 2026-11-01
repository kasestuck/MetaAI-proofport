"""Explicit local replay CLI. It cannot activate live Meta or fallback to fixtures."""

import argparse
import json
from pathlib import Path

from backend.ai.pipeline import AIJob
from backend.languages.registry import LanguageRegistry
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient, ModelUnavailable


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--language",choices=("python","php"),required=True)
    p.add_argument("--project",type=Path,required=True)
    p.add_argument("--cases",type=Path,required=True)
    p.add_argument("--responses",type=Path,required=True)
    p.add_argument("--iterations",type=int,default=1)
    p.add_argument("--max-calls",type=int,default=1)
    p.add_argument("--max-input-tokens",type=int,default=16384)
    p.add_argument("--max-output-tokens",type=int,default=8192)
    p.add_argument("--security-fixes",action="store_true")
    p.add_argument("--security-rule",action="append",default=[])
    p.add_argument("--security-scope",action="append",default=[])
    args=p.parse_args(argv)
    try:
        limits=LLMLimits(max_calls=args.max_calls,max_input_tokens=args.max_input_tokens,max_output_tokens=args.max_output_tokens,
                         max_total_tokens=(args.max_input_tokens+args.max_output_tokens)*args.max_calls)
        source,target=("2.7","3.12") if args.language=="python" else ("7.4","8.3")
        job=AIJob(args.project,args.language,args.cases,source,target,args.iterations,args.security_fixes,
                  tuple(args.security_rule),tuple(args.security_scope))
        with LLMClient(mode="replay",replay_file=args.responses,limits=limits) as client:
            result,artifact=LanguageRegistry().get(args.language).migrate_ai(job,client)
        print(json.dumps({k:result.get(k) for k in ("status","response_mode","response_calls","model_calls","ai_migration","syntax_passed","tests_passed","behavior_verified","error")}))
        print("Retained artifacts: " + str(artifact))
        return 0 if result["status"]=="done" else 2
    except (ModelUnavailable,ValueError,OSError) as exc:
        print(json.dumps({"status":"failed","code":getattr(exc,"code","invalid_job"),"notice":"No live request/fallback. Inspect local configuration; raw details withheld."}))
        return 2


if __name__ == "__main__": raise SystemExit(main())
