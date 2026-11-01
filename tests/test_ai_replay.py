"""Local ordered replay tests. No provider request or project execution."""

from hashlib import sha256
import json

import pytest

from backend.ai.provider import ModelSession, StructuredTranslator
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient, ModelUnavailable


LIMITS=LLMLimits(max_calls=2,max_input_tokens=16384,max_output_tokens=8192,max_total_tokens=49152)


def fingerprint(system,user): return sha256(json.dumps([system,user,True],ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def test_replay_binds_exact_prompt_and_never_creates_sdk(tmp_path,monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**k:pytest.fail("No Meta in replay"))
    recorded=[]
    def respond(system,user):
        request=json.loads(user)
        response=json.dumps({**{k:request[k] for k in ("task","language","file","source_sha256","finding_id")},
            "explanation":"Explicit offline response recording", "proposed_code":request["source"],"confidence":0.9,
            "behavior_impact":"preserves","review_areas":[]})
        recorded.append({"prompt_hash":fingerprint(system,user),"response":response}); return response
    source="def answer():\n    return 42\n"
    original=LLMClient(tmp_path/"no.env",mode="mock",limits=LIMITS,mock_responder=respond)
    assert StructuredTranslator(ModelSession(original,"python")).translate("a.py",source)==source
    replay=tmp_path/"responses.json"; replay.write_text(json.dumps({"mode":"explicit_model_response_replay_not_live","responses":recorded}))
    with LLMClient(tmp_path/"no.env",mode="replay",replay_file=replay,limits=LIMITS) as client:
        translator=StructuredTranslator(ModelSession(client,"python"))
        assert translator.translate("a.py",source)==source
        assert client.calls[0].mode=="replay" and client.cost_usd==0
        with pytest.raises(ModelUnavailable) as error: translator.translate("a.py",source)
        assert error.value.code=="model_replay_miss" and len(client.calls)==1


@pytest.mark.parametrize("data",[{}, {"mode":"fixture","responses":[]}, {"mode":"explicit_model_response_replay_not_live","responses":[]},
    {"mode":"explicit_model_response_replay_not_live","responses":[{"prompt_hash":"bad","response":"x"}]}])
def test_missing_or_malformed_replay_cannot_fallback(tmp_path,data):
    path=tmp_path/"bad.json"; path.write_text(json.dumps(data))
    with pytest.raises(ModelUnavailable) as error: LLMClient(tmp_path/"no.env",mode="replay",replay_file=path,limits=LIMITS)
    assert error.value.code=="model_replay_unavailable"


def test_replay_miss_stops_before_any_substitute_response(tmp_path):
    path=tmp_path/"bound.json"; path.write_text(json.dumps({"mode":"explicit_model_response_replay_not_live","responses":[{"prompt_hash":"0"*64,"response":"{}"}]}))
    client=LLMClient(tmp_path/"no.env",mode="replay",replay_file=path,limits=LIMITS)
    with pytest.raises(ModelUnavailable) as error: client.complete("changed","prompt",json_mode=True)
    assert error.value.code=="model_replay_miss" and not client.calls and len(client.attempts)==1


def test_missing_response_has_no_leaking_exception_body(tmp_path):
    key="unit-only-sensitive-provider-value"
    def absent(*args): raise ModelUnavailable("Failed credential="+key)
    client=LLMClient(tmp_path/"no.env",mode="mock",limits=LIMITS,mock_responder=absent)
    with pytest.raises(ModelUnavailable) as error: client.complete("synthetic","synthetic",json_mode=True)
    assert key not in str(error.value) and not client.calls and client.cost_usd==0
