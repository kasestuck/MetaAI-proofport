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


def analyze_python(runner, source, image, version, target=None):
    """Analyze with actual source grammar; no target imports or host parsing."""
    script = "analyze_py2.py" if version == "2.7" else "analyze_py3.py"
    result = runner.run(image, source, ["python", "-B", "/tools/" + script])
    if result.exit_code or result.timed_out or result.output_exceeded:
        raise SandboxError("Selected source-interpreter analysis failed inside Docker.")
    data = json.loads(result.stdout)
    if data.get("python", [])[:2] != [int(part) for part in version.split(".")]:
        raise SandboxError("Analyzer interpreter does not match the selected version.")
    modules = {module["name"]: module for module in data["modules"] if not module["is_test"]}
    graph = {}
    for name, module in modules.items():
        dependencies = set()
        for imported in module["imports"]:
            parts = imported.split(".")
            while parts:
                candidate = ".".join(parts)
                if candidate in modules and candidate != name:
                    dependencies.add(candidate)
                parts.pop()
        graph[name] = sorted(dependencies)
    pending, ordered = set(modules), []
    while pending:
        ready = sorted(name for name in pending if not (set(graph[name]) & pending))
        if not ready:
            break
        ordered.extend(ready)
        pending.difference_update(ready)
    data.update(graph=graph, order=[modules[name] for name in ordered], cyclic_or_blocked=sorted(pending))
    data["migration_plan"] = {
        "source_interpreter": version, "target_requested": target,
        "ordered_files": [modules[name]["file"] for name in ordered],
        "manual_review": sorted(pending),
        "steps": ["Record source hashes and preserve layout", "Review dependencies and obsolete constructs",
                  "Record behavior with the source runtime", "Prepare candidate copy", "Compile, test and compare on verified target"],
        "migration_performed": False, "dependency_installation_performed": False,
    }
    return data
