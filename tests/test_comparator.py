import base64

import pytest

from backend.core.comparator import compare, compare_cases


def tagged(kind, value):
    return {"t": kind, "v": value}


def old_text(value):
    return tagged("bytes_or_text", base64.b64encode(value.encode()).decode())


@pytest.mark.parametrize("expected,actual,matches", [
    (tagged("int", 2), tagged("float", "2.0"), False),
    (tagged("float", "2.0"), tagged("float", "2.00"), False),
    (tagged("int", 2), tagged("int", 2), True),
    (old_text("hi"), tagged("str", "hi"), True),
    (old_text("hi"), tagged("bytes", "aGk="), True),
    (old_text("hi"), tagged("str", "HI"), False),
    (tagged("str", "hi"), tagged("bytes", "aGk="), False),
    (tagged("bytes_or_text", "/w=="), tagged("bytes", "/w=="), True),
    (tagged("list", [1, 2]), tagged("list", [2, 1]), False),
    (tagged("tuple", [1, 2]), tagged("list", [1, 2]), False),
    (tagged("set", [1, 2]), tagged("set", [2, 1]), True),
    (tagged("dict", [[old_text("b"), 2], [old_text("a"), 1]]), tagged("dict", [[tagged("str", "a"), 1], [tagged("str", "b"), 2]]), True),
    (tagged("dict", [[old_text("a"), 1]]), tagged("dict", [[tagged("str", "a"), 2]]), False),
    ({"exception": {"type": "IOError", "errno": 2, "message": "missing"}}, {"exception": {"type": "FileNotFoundError", "errno": 2, "message": "missing"}}, True),
    ({"exception": {"type": "IOError", "errno": 2, "message": "missing"}}, {"exception": {"type": "FileNotFoundError", "errno": 2, "message": "different"}}, False),
    ({"exception": {"type": "ValueError", "message": "bad"}}, {"exception": {"type": "TypeError", "message": "bad"}}, False),
])
def test_comparison_rules(expected, actual, matches):
    assert compare(expected, actual)["matches"] is matches


def test_allowed_differences_are_reported():
    result = compare(old_text("café"), tagged("str", "café"))
    assert result["matches"]
    assert "UTF-8" in result["allowed_differences"][0]["rule"]


def test_missing_or_extra_cases_cannot_pass():
    with pytest.raises(ValueError, match="IDs differ"):
        compare_cases([{"id": "a"}], [])
