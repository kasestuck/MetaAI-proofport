"""Observed repair context, redaction and replay; no network or project execution."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.ai.feedback import repair_feedback
from backend.ai.provider import ModelSession, StructuredTranslator
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient, ModelUnavailable


LIMITS=LLMLimits(max_calls=2,max_input_tokens=16384,max_output_tokens=4096,max_total_tokens=40960)
SOURCE="def mean(values):\n    return sum(values) / len(values)\n"
PREVIOUS="def mean(values):\n    return sum(values) // len(values)\n"


def observations():
    case={"id":"mathutils.mean_float","module":"legacy_shop.mathutils",
          "steps":[{"call":"legacy_shop.mathutils.mean","args":[[1.5,2.0]]}]}
    expected={"id":case["id"],"module":case["module"],"steps":[{"value":{"t":"float","v":"1.75"},"stdout":"","stderr":""}]}
    actual={**expected,"steps":[{"value":{"t":"float","v":"1.0"},"stdout":"","stderr":""}]}
    checks={"syntax_passed":True,"tests_passed":True,"behavior_verified":False,
            "comparisons":[{"id":case["id"],"matches":False,"expected":expected,"actual":actual}]}
    return checks,[case]


def reply(context):
    # Deliberately return the known WRONG previous code. Testing the prompt does
    # not pretend to fix behavior or supply a canned successful model candidate.
    return json.dumps({**{k:context[k] for k in ("task","language","file","source_sha256","finding_id")},
        "explanation":"Explicit offline protocol replay; candidate is still incorrect",
        "proposed_code":PREVIOUS,"behavior_impact":"preserves","confidence":0.5,"review_areas":[]})


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**kw:pytest.fail("No Meta SDK/network allowed"))
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run",lambda *a,**kw:pytest.fail("No host/unit sample execution"))


def test_detailed_prompt_contains_inputs_expected_actual_and_constraints_then_replays(tmp_path):
    checks,cases=observations(); feedback=repair_feedback(checks,cases)
    captured=[]
    def responder(system,user):
        captured.append((system,user)); return reply(json.loads(user))
    client=LLMClient(tmp_path/'none.env',mode='mock',limits=LIMITS,mock_responder=responder)
    session=ModelSession(client,'python',case_feedback=True)
    assert StructuredTranslator(session).translate('legacy_shop/mathutils.py',SOURCE,PREVIOUS,feedback)==PREVIOUS
    system,user=captured[0]; context=json.loads(user)
    assert context['source']==SOURCE and context['previous']==PREVIOUS
    observed=context['failures']['failing_cases'][0]
    assert observed['input']==cases[0]['steps']
    assert observed['expected'][0]['value']['v']=='1.75'
    assert observed['actual'][0]['value']['v']=='1.0'
    assert 'BOTH operands' in system and 'negative halves' in system and 'public signatures' in system
    assert 'No expected golden outputs' not in system and 'Do not hardcode' in system
    replay_file=tmp_path/'responses.json'
    replay_file.write_text(json.dumps({'mode':'explicit_model_response_replay_not_live','responses':[
        {'prompt_hash':client.attempts[0].prompt_hash,'response':reply(context)}]}))
    with LLMClient(tmp_path/'none.env',mode='replay',replay_file=replay_file,limits=LIMITS) as replay:
        translator=StructuredTranslator(ModelSession(replay,'python',case_feedback=True))
        assert translator.translate('legacy_shop/mathutils.py',SOURCE,PREVIOUS,feedback)==PREVIOUS
        assert replay.cost_usd==replay.tokens_in==replay.tokens_out==0
    client.close()


def test_generic_pipeline_keeps_detailed_case_data_out(tmp_path):
    captured=[]
    def responder(system,user): captured.append(json.loads(user)); return reply(json.loads(user))
    c=LLMClient(tmp_path/'none.env',mode='mock',limits=LIMITS,mock_responder=responder)
    StructuredTranslator(ModelSession(c,'python')).translate('legacy_shop/mathutils.py',SOURCE,PREVIOUS,repair_feedback(*observations()))
    assert 'failing_cases' not in captured[0]['failures']
    c.close()


def test_private_values_in_observations_are_redacted(tmp_path):
    feedback=repair_feedback(*observations())
    secret='unit-only-context-secret'
    feedback['failing_cases'][0]['actual'][0]['stdout']=secret
    seen=[]
    def responder(s,u):
        seen.append(u)
        context=json.loads(u)
        result=json.loads(reply(context)); result['proposed_code']=context['source']
        return json.dumps(result)
    c=LLMClient(tmp_path/'none.env',mode='mock',limits=LIMITS,mock_responder=responder)
    source="PASSWORD='"+secret+"'\n"+SOURCE
    # Use request directly: this unit checks context redaction, not patch restore.
    ModelSession(c,'python',case_feedback=True).request('translate','legacy_shop/mathutils.py',source,previous=PREVIOUS,failures=feedback)
    assert secret not in seen[0] and '__PROOFPORT_PRIVATE_1__' in seen[0]
    c.close()


def test_oversized_feedback_is_rejected_before_any_model_request():
    checks,cases=observations()
    checks['comparisons'][0]['actual']['steps'][0]['stdout']='x'*20000
    with pytest.raises(ModelUnavailable,match='bounded context'): repair_feedback(checks,cases)


def test_failed_candidate_fixture_has_exact_recorded_hash():
    folder=Path(__file__).parent/'fixtures/p8_failed_candidate'
    meta=json.loads((folder/'provenance.json').read_text())
    assert meta['provenance']=='real_meta_p8_failed_candidate_not_a_fix'
    assert sha256((folder/'mathutils.py').read_text(encoding='utf-8').encode()).hexdigest()==meta['fixture_utf8_lf_sha256']
