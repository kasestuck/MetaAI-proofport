"""Source-interpreter analysis and deterministic dependency ordering."""

import json

from backend.sandbox.runner import SandboxError


def analyze(runner, source):
    result = runner.run("python:2.7", source, ["python", "-B", "/tools/analyze_py2.py"])
    if result.exit_code or result.timed_out or result.output_exceeded:
        raise SandboxError("Python 2.7 source analysis failed inside Docker.")
    data = json.loads(result.stdout)
    if data.get("python", [])[:2] != [2, 7]:
        raise SandboxError("Source analyzer requires an actual Python 2.7 interpreter.")
    modules = {module["name"]: module for module in data["modules"] if not module["is_test"]}
    pending, ordered = set(modules), []
    while pending:
        ready = sorted(name for name in pending if not (set(modules[name]["imports"]) & (pending - {name})))
        if not ready:
            raise ValueError("Cyclic project imports require review before migration.")
        ordered.extend(modules[name] for name in ready)
        pending.difference_update(ready)
    data["order"] = ordered
    return data
