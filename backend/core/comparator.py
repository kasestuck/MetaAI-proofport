"""Exact golden comparisons with explicit, recorded Python 2/3 allowances."""

import base64
import json


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _normalize(value, allowances, path="root"):
    if isinstance(value, list):
        return [_normalize(item, allowances, f"{path}[{i}]") for i, item in enumerate(value)]
    if not isinstance(value, dict):
        return value
    tag = value.get("t")
    if tag == "bytes_or_text":
        raw = base64.b64decode(value["v"], validate=True)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {"t": "bytes", "v": value["v"]}
        allowances.append({"path": path, "rule": "Python 2 str matched by identical UTF-8 text/bytes"})
        return {"t": "text_or_bytes", "v": decoded}
    if tag == "dict":
        pairs = [[_normalize(k, allowances, path + ".key"), _normalize(v, allowances, path + ".value")]
                 for k, v in value["v"]]
        return {"t": tag, "v": sorted(pairs, key=lambda pair: _canonical(pair[0]))}
    if tag == "set":
        return {"t": tag, "v": sorted(_normalize(value["v"], allowances, path), key=_canonical)}
    result = {key: _normalize(item, allowances, path + "." + key) for key, item in value.items()}
    if "exception" in result:
        exception = result["exception"]
        renamed = {2: "FileNotFoundError", 13: "PermissionError", 17: "FileExistsError", 20: "NotADirectoryError", 21: "IsADirectoryError"}
        if exception["type"] == "IOError" or exception["type"] == renamed.get(exception.get("errno")):
            exception["type"] = "OSError"
            allowances.append({"path": path, "rule": "Python 2 IOError/Python 3 errno-derived OSError name; errno and message must match"})
    return result


def _equal(expected, actual):
    if isinstance(expected, dict) and expected.get("t") == "text_or_bytes":
        if not isinstance(actual, dict):
            return False
        if actual.get("t") == "str":
            return expected["v"] == actual["v"]
        if actual.get("t") in {"bytes", "text_or_bytes"}:
            try:
                text = base64.b64decode(actual["v"], validate=True).decode("utf-8") if actual["t"] == "bytes" else actual["v"]
            except (ValueError, UnicodeDecodeError):
                return False
            return expected["v"] == text
        return False
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        if expected.get("t") in {"dict", "set"} and actual.get("t") == expected["t"]:
            remaining = list(actual["v"])
            for item in expected["v"]:
                for index, candidate in enumerate(remaining):
                    if _equal(item, candidate):
                        remaining.pop(index)
                        break
                else:
                    return False
            return not remaining
        return expected.keys() == actual.keys() and all(_equal(expected[k], actual[k]) for k in expected)
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(_equal(e, a) for e, a in zip(expected, actual))
    return expected == actual


def compare(expected: dict, actual: dict) -> dict:
    allowances = []
    normalized = _normalize(expected, allowances)
    observed = _normalize(actual, [])
    matches = _equal(normalized, observed)
    return {"matches": matches, "allowed_differences": allowances if matches else [],
            **({} if matches else {"expected": expected, "actual": actual})}


def compare_cases(expected: list[dict], actual: list[dict]) -> list[dict]:
    indexed = {case["id"]: case for case in actual}
    if len(indexed) != len(actual) or {case["id"] for case in expected} != set(indexed):
        raise ValueError("Golden and candidate case IDs differ or are duplicated.")
    return [{"id": case["id"], "module": case["module"], **compare(case, indexed[case["id"]])} for case in expected]
