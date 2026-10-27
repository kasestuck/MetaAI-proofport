from hashlib import sha256
import json

import pytest

from backend.core.translator import FixtureTranslator, parse_code


@pytest.mark.parametrize("bad", ["print('no fence')", "```python\nx = 1\n```\n```python\nx = 2\n```", "Here is code:\n```python\nx = 1\n```"])
def test_reject_malformed_model_text(bad):
    with pytest.raises(ValueError, match="one complete"):
        parse_code(bad)


def test_extract_without_executing():
    source = "raise RuntimeError('must not execute on host')"
    assert parse_code("```python\n" + source + "\n```") == source + "\n"


def test_fixture_candidates_are_bound_to_original_source(tmp_path):
    original = "print 'original'\n"
    fixture = tmp_path / "patches.json"
    fixture.write_text(json.dumps({"mode": "explicit_fixture_patches_not_ai", "files": {
        "module.py": {"sha256": sha256(original.encode()).hexdigest(), "replace": [["print 'original'", "print('original')"]]},
    }}))
    provider = FixtureTranslator(fixture)
    assert provider.translate("module.py", original) == "print('original')\n"
    with pytest.raises(ValueError, match="hash-matching"):
        provider.translate("module.py", "print 'different'\n")
