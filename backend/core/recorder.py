"""Run the same trusted harness against legacy and candidate working copies."""

import json
import re

from backend.sandbox.runner import SandboxError


def invoke(runner, image, source, action, cases=None, evidence=None, *, version=None):
    result = runner.run(image, source, ["python", "-B", "/tools/harness.py"],
                        {"action": action, **({"cases": cases} if cases is not None else {})})
    if evidence:
        evidence.append("sandbox_run", json.dumps({"action": action, **result.summary()}, sort_keys=True))
    if result.exit_code or result.timed_out or result.output_exceeded:
        raise SandboxError(f"Docker harness {action} failed (exit {result.exit_code}, timeout={result.timed_out}, output_limit={result.output_exceeded}).")
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise SandboxError("Docker harness returned invalid JSON.") from None
    if "harness_error" in data:
        raise SandboxError("Docker harness failed: " + data["harness_error"])
    if version is None:
        match = re.fullmatch(r"python:(\d+\.\d+)(?:-[a-z0-9.-]+)?", image)
        if not match:
            raise SandboxError("An explicit interpreter version is required for an image ID/custom tag.")
        version = match.group(1)
    expected = [int(part) for part in version.split(".")]
    if data.get("python", [])[:2] != expected:
        raise SandboxError("Docker image does not provide the required Python interpreter version.")
    return data


def load_cases(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_cases(data["cases"])


def validate_cases(cases):
    if not isinstance(cases, list) or not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Golden inputs must have nonempty, unique case IDs.")
    for case in cases:
        if not isinstance(case.get("id"), str) or not isinstance(case.get("module"), str) or not case.get("steps"):
            raise ValueError("Each golden case needs an ID, module and nonempty steps.")
        operations = {"call", "attribute", "method", "builtin"}
        for step in case["steps"]:
            if len(operations & step.keys()) != 1:
                raise ValueError("Each golden step must specify exactly one supported operation.")
        if not any(str(step.get("call", step.get("attribute", ""))).startswith(case["module"] + ".") for step in case["steps"]):
            raise ValueError("A golden case must exercise its declared module directly.")
    return cases
