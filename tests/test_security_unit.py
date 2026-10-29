from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from backend.core.models import Finding
from backend.core.security import findings_for
from backend.security.engine import checked_file
from backend.security.models import FixProposal
from backend.security.policy import constant_argv_only, constant_shell_to_argv, public_api, review_reasons
from backend.security.providers import LLMFixGenerator, OfflineOnlyError


OLD = "import subprocess\ndef output():\n    return subprocess.check_output('/usr/bin/printf fixture', shell=True)\n"
NEW = "import subprocess\ndef output():\n    return subprocess.check_output(['/usr/bin/printf', 'fixture'], shell=False)\n"


def proposal(**changes):
    return FixProposal(finding_id="example-id", explanation="Offline fixture", proposed_code=NEW,
                       behavior_impact="preserves", confidence=1.0).model_copy(update=changes)


def test_finding_identity_is_stable_when_lines_shift_and_unique():
    def item(line):
        return {"test_id": "B602", "filename": "commands.py", "line_number": line, "scope": "output",
                "issue_severity": "HIGH", "issue_confidence": "HIGH", "issue_text": "Potential shell issue", "issue_cwe": {"id": 78}}
    first = {"results": [item(4), item(7)]}
    shifted = deepcopy(first)
    for finding in shifted["results"]:
        finding["line_number"] += 10
    _, a = findings_for(first)
    _, b = findings_for(shifted)
    assert [f["id"] for f in a] == [f["id"] for f in b]
    assert len({f["id"] for f in a}) == 2
    assert a[0]["cwe"]["id"] == 78
    assert a[0]["verification_status"] == "potential_risk_not_confirmed"
    assert "shell=False" in a[0]["proposed_fix"]
    assert set(Finding.model_fields) == {"id", "file", "line", "severity", "status", "note"}


@pytest.mark.parametrize("confidence", [-1, 1.1, float("nan"), float("inf")])
def test_proposal_confidence_is_validated(confidence):
    data = proposal().model_dump()
    data["confidence"] = confidence
    with pytest.raises(ValidationError):
        FixProposal.model_validate(data)


def test_only_exact_constant_command_transform_is_supported():
    assert constant_shell_to_argv(OLD, NEW)
    assert not constant_shell_to_argv(OLD, NEW.replace("'fixture'", "'changed'"))
    assert not constant_shell_to_argv(OLD.replace("printf fixture", "printf fixture; id"), NEW)
    assert not constant_shell_to_argv(OLD, NEW + "\nextra = 42\n")
    assert constant_shell_to_argv(OLD, NEW, line=3)
    assert not constant_shell_to_argv(OLD, NEW, line=99)
    duplicate = OLD + "\ndef second():\n    return subprocess.check_output('/usr/bin/printf fixture', shell=True)\n"
    changed_first = duplicate.replace("subprocess.check_output('/usr/bin/printf fixture', shell=True)", "subprocess.check_output(['/usr/bin/printf', 'fixture'], shell=False)", 1)
    assert not constant_shell_to_argv(duplicate, changed_first, line=6)
    assert not constant_shell_to_argv(OLD.replace("/usr/bin/printf", "/bin/sh"), NEW.replace("/usr/bin/printf", "/bin/sh"))
    assert not constant_argv_only("import subprocess\ndef unsafe():\n return subprocess.check_output(['/bin/sh', '-c', 'eval $UNTRUSTED'], shell=False)\n")


def test_oversized_proposal_is_rejected_before_execution():
    data = proposal().model_dump()
    data["proposed_code"] = "x" * 262145
    with pytest.raises(ValidationError):
        FixProposal.model_validate(data)


@pytest.mark.parametrize("changes", [{"proposed_code": None}, {"disposition": "false_positive"}])
def test_proposals_cannot_confuse_classification_and_code_changes(changes):
    data = proposal().model_dump()
    data.update(changes)
    with pytest.raises(ValidationError):
        FixProposal.model_validate(data)


def test_api_and_protected_semantics_require_review():
    changed = NEW.replace("def output():", "def output(arg=None):")
    reasons = review_reasons({"scanner_test": "B602"}, proposal(proposed_code=changed), OLD, changed)
    assert any("Public signatures" in reason for reason in reasons)
    assert public_api("class A:\n def __init__(self, a): pass\n") != public_api("class A:\n def __init__(self, a=1): pass\n")
    assert any("manual review" in reason for reason in review_reasons({"scanner_test": "B105"}, proposal(), OLD, NEW))


def test_future_llm_adapter_cannot_spend_api_credits():
    class ForbiddenClient:
        def complete(self, *args, **kwargs):
            pytest.fail("API must never be called in offline P2")
    adapter = LLMFixGenerator(ForbiddenClient())
    with pytest.raises(OfflineOnlyError):
        adapter.generate({"id": "example-id"}, "untrusted source")
    parsed = adapter.parse_response(proposal().model_dump_json(), "example-id")
    assert parsed.mode == "live"  # A model response cannot label itself a trusted fixture.
    with pytest.raises(ValueError, match="another finding"):
        adapter.parse_response(proposal().model_dump_json(), "other-id")
    request = adapter.build_request({"id": "example-id"}, "[REDACTED]")
    assert request["json_mode"] is True
    assert "proposed_code" in json.loads(request["user"])["schema"]["properties"]


@pytest.mark.parametrize("relative", ["../outside.py", "/tmp/file.py", "C:/outside.py", "dir\\file.py"])
def test_patch_paths_cannot_escape_copy(tmp_path, relative):
    with pytest.raises(ValueError):
        checked_file(tmp_path, relative)
