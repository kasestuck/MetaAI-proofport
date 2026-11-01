"""Bounded PHP golden inputs and strict typed comparison. No expected answers sent."""

from hashlib import sha256
import base64
import json
from pathlib import PurePosixPath
import re

from backend.languages.base import AdapterError


def relative_php(value, *, tests=False):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\0" in value:
        raise ValueError("Use a relative PHP file path.")
    parts = value.split("/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"", ".", ".."} or p.startswith(".") for p in parts) or path.suffix != ".php":
        raise ValueError("Invalid PHP profile path.")
    if not tests and ("tests" in parts or "vendor" in parts):
        raise ValueError("Fixtures/cases cannot target tests or dependencies.")
    return value


def _argument(value, depth=0):
    if depth > 12:
        raise ValueError("PHP input nesting limit exceeded.")
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int and -(2 ** 53) < value < 2 ** 53:
        return
    if isinstance(value, list) and len(value) <= 128:
        for item in value: _argument(item, depth + 1)
        return
    if isinstance(value, dict) and len(value) <= 128 and all(isinstance(k, str) and not re.fullmatch(r"-?\d+", k) for k in value):
        for item in value.values(): _argument(item, depth + 1)
        return
    raise ValueError("PHP inputs support bounded JSON scalar/array/map values; ambiguous floats/numeric map keys require a new explicit codec.")


def cases_profile(data):
    if not isinstance(data, dict) or data.get("mode") != "php_golden_inputs" or set(data) - {"mode", "cases", "allowed_differences"}:
        raise ValueError("Invalid PHP golden profile.")
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
        raise ValueError("PHP golden inputs require 1..64 cases.")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "file", "call", "args", "expected_status"}:
            raise ValueError("Malformed PHP golden case.")
        if not isinstance(case["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["id"]) or case["id"] in ids:
            raise ValueError("PHP case IDs must be unique.")
        ids.add(case["id"]); relative_php(case["file"])
        if not isinstance(case["call"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\\[A-Za-z_][A-Za-z0-9_]*)*", case["call"]):
            raise ValueError("Use a project function, not a method/expression.")
        if not isinstance(case["args"], list) or len(case["args"]) > 16 or case["expected_status"] not in {"return", "exception", "runtime_error"}:
            raise ValueError("Unsupported PHP case arguments/status.")
        _argument(case["args"])
    allowed = data.get("allowed_differences", [])
    if not isinstance(allowed, list) or set(allowed) - {"deprecation_notices"}:
        raise ValueError("Unknown PHP normalization allowance.")
    if len(json.dumps(data).encode()) > 131072:
        raise ValueError("PHP inputs exceed the profile size limit.")
    return data


def load_cases(path):
    return cases_profile(json.loads(path.read_text(encoding="utf-8")))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def normalized_value(value, depth=0):
    if depth > 16 or not isinstance(value, dict): raise ValueError("Invalid normalized PHP value")
    kind = value.get("type")
    if kind == "null" and set(value) == {"type"}: return
    if kind == "bool" and set(value) == {"type", "value"} and type(value["value"]) is bool: return
    if kind == "int" and set(value) == {"type", "value"} and isinstance(value["value"], str) and re.fullmatch(r"0|-?[1-9]\d*", value["value"]) and -(2**63) <= int(value["value"]) < 2**63: return
    if kind == "float" and set(value) == {"type", "value"} and isinstance(value["value"], str) and re.fullmatch(r"[a-f0-9]{16}", value["value"]): return
    if kind == "bytes" and set(value) == {"type", "base64"} and isinstance(value["base64"], str):
        base64.b64decode(value["base64"], validate=True); return
    if kind == "array" and set(value) == {"type", "items"} and isinstance(value["items"], list) and len(value["items"]) <= 256:
        keys = set()
        for item in value["items"]:
            if not isinstance(item, dict) or set(item) != {"key", "value"}: raise ValueError("Invalid PHP array item")
            normalized_value(item["key"], depth+1); normalized_value(item["value"], depth+1)
            if item["key"]["type"] not in {"int", "bytes"} or digest(item["key"]) in keys: raise ValueError("Duplicate/invalid PHP array key")
            keys.add(digest(item["key"]))
        return
    raise ValueError("Unsupported/malformed PHP value codec")


def validate_outcome(result):
    if not isinstance(result, dict) or not {"id", "status", "stdout", "warnings", "deprecations"} <= set(result): raise ValueError("Incomplete PHP case result")
    base64.b64decode(result["stdout"], validate=True)
    if result["status"] == "return": normalized_value(result.get("value"))
    elif result["status"] in {"exception", "runtime_error"}:
        error = result.get("error")
        if not isinstance(error, dict) or set(error) != {"class", "message", "code"} or not isinstance(error["class"], str): raise ValueError("Missing PHP error")
        normalized_value(error["message"]); normalized_value(error["code"])
    elif result["status"] not in {"harness_error", "unsupported_result"}: raise ValueError("Unknown PHP outcome")
    for field in ("warnings", "deprecations"):
        if not isinstance(result[field], list): raise ValueError("Invalid PHP warnings")
        for warning in result[field]:
            if set(warning) != {"level", "message"} or type(warning["level"]) is not int: raise ValueError("Invalid PHP warning")
            if field == "deprecations" and warning["level"] not in {8192, 16384}: raise ValueError("Non-deprecation cannot be ignored")
            normalized_value(warning["message"])


def compare(profile, expected, actual):
    profile = cases_profile(profile)
    wanted = [c["id"] for c in profile["cases"]]
    if not isinstance(expected, list) or not isinstance(actual, list) or [c.get("id") for c in expected] != wanted or [c.get("id") for c in actual] != wanted:
        raise AdapterError("php_case_protocol_invalid", "PHP result count/order/IDs do not match recorded inputs.")
    comparisons = []
    for case, old, new in zip(profile["cases"], expected, actual):
        validate_outcome(old); validate_outcome(new)
        valid = old.get("status") == case["expected_status"] == new.get("status") and old["status"] in {"return", "exception", "runtime_error"}
        before, after, differences = dict(old), dict(new), []
        if "deprecation_notices" in profile.get("allowed_differences", []):
            a, b = before.pop("deprecations", []), after.pop("deprecations", [])
            if a != b: differences.append({"rule": "deprecation_notices", "source_count": len(a), "target_count": len(b)})
        matches = valid and before == after
        comparisons.append({"id": case["id"], "module": case["file"], "matches": matches,
                            "allowed_differences": differences, "expected_sha256": digest(old), "observed_sha256": digest(new),
                            "reason": None if matches else "Typed return/exception/runtime error/output/warnings differ, or expected status was not exercised."})
    return comparisons
