"""Bounded, explicit opt-in to observed source/target cases for P8 repair.

Only the local first-module runner enables this. Generic adapters retain their
status/ID-only policy. These are observations, never model acceptance criteria.
"""

from copy import deepcopy
import json

from backend.llm.client import ModelUnavailable


def _observations(outcome):
    # Case ID/module are already bound outside these observations. Empty output
    # channels are omitted to conserve context; nonempty output stays exact.
    return [{k:deepcopy(v) for k,v in step.items() if k not in {"stdout","stderr"} or v != ""}
            for step in outcome["steps"]]


def repair_feedback(checks, cases):
    indexed = {c["id"]:c for c in cases}
    failed = [c for c in checks.get("comparisons", []) if not c["matches"]]
    if len(failed) > 16:
        raise ModelUnavailable("Too many failing cases for bounded first-module feedback.", "input_budget_exceeded")
    details = []
    for comparison in failed:
        case = indexed[comparison["id"]]
        if case["module"] != "legacy_shop.mathutils":
            raise ModelUnavailable("Unexpected repair case scope.", "model_context_invalid")
        details.append({"id":case["id"], "input":deepcopy(case["steps"]),
                        "expected":_observations(comparison["expected"]), "actual":_observations(comparison["actual"])})
    feedback = {"syntax":{"passed":checks["syntax_passed"],
                           "errors":deepcopy(checks.get("syntax", {}).get("errors", [])[:8])},
                "existing_tests":{"passed":checks["tests_passed"],
                    "failed":[{"id":o["id"], "status":o["status"]}
                        for o in checks.get("target_tests", {}).get("outcomes", []) if o["status"] != "passed"][:8]},
                "golden":{"passed":checks["behavior_verified"]},
                "failing_cases":details, "repair_requested":True,
                "requirements":"Preserve original runtime behavior and public APIs; repair the general implementation, not individual case IDs."}
    if len(json.dumps(feedback, ensure_ascii=True).encode()) > 16384:
        raise ModelUnavailable("Repair observations exceed the bounded context; no request sent.", "input_budget_exceeded")
    return feedback
