"""Host tests validate protocol data only; PHP code is never executed here."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.php.protocol import cases_profile, compare, load_cases, normalized_value, relative_php
from backend.languages.base import AdapterError


PROFILE = {"mode": "php_golden_inputs", "cases": [{"id": "a", "file": "src/a.php", "call": "Demo\\a", "args": [], "expected_status": "return"}], "allowed_differences": ["deprecation_notices"]}


def result(value=None):
    return {"id": "a", "status": "return", "value": value or {"type": "int", "value": "1"}, "stdout": "", "warnings": [], "deprecations": []}


@pytest.mark.parametrize("value", [{"type":"null"}, {"type":"bool","value":False}, {"type":"int","value":"-9223372036854775808"},
    {"type":"float","value":"3ff0000000000000"}, {"type":"bytes","base64":"/wA="}, {"type":"array","items":[]}])
def test_codec_preserves_php_types(value):
    normalized_value(value)
    assert compare(PROFILE, [result(value)], [result(value)])[0]["matches"]


@pytest.mark.parametrize("value", [{"type":"int","value":"01"}, {"type":"int","value":str(2**63)}, {"type":"bool","value":1},
    {"type":"bytes","base64":"!!"}, {"type":"object"}, {"type":"float","value":"NaN"}])
def test_malformed_codec_cannot_verify(value):
    with pytest.raises(ValueError): normalized_value(value)


@pytest.mark.parametrize("field,new", [("value", {"type":"bool","value":True}), ("stdout","eA=="),
    ("warnings",[{"level":512,"message":{"type":"bytes","base64":"eA=="}}]), ("status","unsupported_result")])
def test_behavior_changes_are_mismatches(field, new):
    changed = result(); changed[field] = new
    assert not compare(PROFILE,[result()],[changed])[0]["matches"]


def test_array_order_is_behavior_not_json_map_sorting():
    entries = [{"key":{"type":"int","value":str(i)},"value":{"type":"int","value":str(i)}} for i in (1,2)]
    assert not compare(PROFILE, [result({"type":"array","items":entries})], [result({"type":"array","items":entries[::-1]})])[0]["matches"]


def test_only_declared_deprecations_can_differ():
    old = result(); old["deprecations"] = [{"level":8192,"message":{"type":"bytes","base64":"ZGVwcmVjYXRlZA=="}}]
    checked = compare(PROFILE,[old],[result()])[0]
    assert checked["matches"] and checked["allowed_differences"][0]["source_count"] == 1
    strict = {**PROFILE,"allowed_differences":[]}
    assert not compare(strict,[old],[result()])[0]["matches"]
    old["deprecations"][0]["level"] = 512
    with pytest.raises(ValueError): compare(PROFILE,[old],[result()])


@pytest.mark.parametrize("name", ["../x.php", "C:/x.php", "/x.php", "src\\x.php", ".env.php", "tests/a.php", "vendor/a.php"])
def test_profile_cannot_target_service_or_test_files(name):
    with pytest.raises(ValueError): relative_php(name)


@pytest.mark.parametrize("change", ["missing", "duplicate", "float_arg", "numeric_key", "builtin_expression", "expected_value"])
def test_bad_case_profiles_do_not_run(change):
    p = deepcopy(PROFILE)
    if change == "missing": p["cases"] = []
    if change == "duplicate": p["cases"] *= 2
    if change == "float_arg": p["cases"][0]["args"] = [float("nan")]
    if change == "numeric_key": p["cases"][0]["args"] = [{"1":"ambiguous"}]
    if change == "builtin_expression": p["cases"][0]["call"] = "system('x')"
    if change == "expected_value": p["cases"][0]["expected"] = 1
    with pytest.raises(ValueError): cases_profile(p)


def test_actual_demo_inputs_have_no_canned_answers():
    p = load_cases(Path(__file__).parent / "fixtures/php_profiles/cases.json")
    assert len(p["cases"]) == 22 and {c["expected_status"] for c in p["cases"]} == {"return","exception","runtime_error"}
    with pytest.raises(AdapterError): compare(PROFILE, [result()], [])


@pytest.mark.parametrize("status",["exception","runtime_error"])
def test_exception_class_message_and_code_are_compared(status):
    p = deepcopy(PROFILE); p["cases"][0]["expected_status"] = status
    old = result(); old.pop("value"); old.update(status=status,error={"class":"Error","message":{"type":"bytes","base64":"eA=="},"code":{"type":"int","value":"0"}})
    assert compare(p,[old],[deepcopy(old)])[0]["matches"]
    new = deepcopy(old); new["error"]["class"] = "TypeError"
    assert not compare(p,[old],[new])[0]["matches"]
