"""Offline model contracts and safety; no generated code is executed by host tests."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.ai.models import ModelPatch
from backend.ai.pipeline import AIJob
from backend.ai.provider import ModelSession, StructuredTranslator, PrivateContext, failure_summary
from backend.api.main import create_app
from backend.core.evidence import Evidence
from backend.core.pipeline import _rollback_model
from backend.languages.registry import LanguageRegistry
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient, ModelUnavailable
from backend.security.providers import LLMFixGenerator


LIMITS = LLMLimits(max_calls=4,max_input_tokens=16384,max_output_tokens=8192,max_total_tokens=98304)
SOURCE = "def total(a, b):\n    return a + b\n"


def answer(request, **updates):
    return {**{k:request[k] for k in ("task","language","file","source_sha256","finding_id")},
            "explanation":"Offline response fixture, not Meta AI", "proposed_code":request["source"],
            "behavior_impact":"preserves", "confidence":0.9, "review_areas":[], **updates}


def responder(system, user): return json.dumps(answer(json.loads(user)))


@pytest.fixture(autouse=True)
def no_sdk_or_project_execution(monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**k:pytest.fail("No Meta SDK/network in offline contracts"))
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.run",lambda *a,**k:pytest.fail("No host/unit project execution"))


def client(tmp_path, responder=responder, **options):
    return LLMClient(tmp_path/"missing.env",mode="mock",limits=options.pop("limits",LIMITS),mock_responder=responder,**options)


@pytest.mark.parametrize("language,file,source",[("python","module.py",SOURCE),("php","src/module.php","<?php function total($a,$b) { return $a+$b; }")])
def test_structured_translator_uses_language_prompt_and_preserves_bindings(tmp_path,language,file,source):
    observed=[]
    def respond(system,user):
        observed.append((system,json.loads(user))); return responder(system,user)
    c=client(tmp_path,respond); session=ModelSession(c,language,evidence=Evidence())
    assert StructuredTranslator(session).translate(file,source)==source
    assert ("Python 2.7" if language=="python" else "PHP 7.4") in observed[0][0]
    assert observed[0][1]["source_sha256"]==sha256(source.encode()).hexdigest()
    assert session.responses[0]["mode"]=="mock" and session.evidence.verify()
    assert c.cost_usd==c.tokens_in==c.tokens_out==0 and len(c.attempts)==1


@pytest.mark.parametrize("change",[{"language":"php"},{"source_sha256":"0"*64},{"file":"tests/test.py"},
    {"finding_id":"another"},{"task":"security"},{"proposed_code":""},{"extra":"field"},{"confidence":True},{"confidence":2.0}])
def test_invalid_or_unbound_model_response_stops_without_fallback(tmp_path,change):
    c=client(tmp_path,lambda s,u:json.dumps(answer(json.loads(u),**change)))
    session=ModelSession(c,"python")
    with pytest.raises(ModelUnavailable): session.request("translate","module.py",SOURCE)
    assert len(c.calls)==1 and not session.responses
    with pytest.raises(ModelUnavailable,match="stopped"): session.request("translate","module.py",SOURCE)
    assert len(c.calls)==1


@pytest.mark.parametrize("response",["bad json",'{"task":"translate","task":"security"}',"[]","",'{"confidence":NaN}'])
def test_invalid_json_empty_or_duplicate_response_is_terminal(tmp_path,response):
    c=client(tmp_path,lambda *args:response)
    with pytest.raises(ModelUnavailable): ModelSession(c,"python").request("translate","module.py",SOURCE)
    assert c.budget_snapshot()["stopped"] and c.cost_usd==0


@pytest.mark.parametrize("file",["../escape.py","/tmp/file.py","C:/file.py","tests/test.py","vendor/file.py",".env.py","test_file.py","src\\file.py"])
def test_model_cannot_choose_tests_dependencies_or_escaping_paths(tmp_path,file):
    c=client(tmp_path)
    with pytest.raises(ModelUnavailable): ModelSession(c,"python").request("translate",file,SOURCE)
    assert not c.calls and not c.attempts


def test_unknown_semantics_are_not_silently_accepted_as_translation(tmp_path):
    c=client(tmp_path,lambda s,u:json.dumps(answer(json.loads(u),behavior_impact="unknown")))
    with pytest.raises(ModelUnavailable) as error: StructuredTranslator(ModelSession(c,"python")).translate("a.py",SOURCE)
    assert error.value.code=="needs_review"


def test_run_budget_shared_across_translation_and_security(tmp_path):
    limits=LLMLimits(max_calls=1,max_input_tokens=16384,max_output_tokens=8192,max_total_tokens=24576)
    c=client(tmp_path,limits=limits); session=ModelSession(c,"python")
    StructuredTranslator(session).translate("a.py",SOURCE)
    generator=LLMFixGenerator(session=session,rules=("B602",))
    finding={"id":"one","file":"a.py","scanner_test":"B602","scope":"total"}
    with pytest.raises(ModelUnavailable) as error: generator.generate(finding,SOURCE)
    assert error.value.code=="budget_exceeded" and len(c.calls)==len(c.attempts)==1


def test_input_and_output_budgets_fail_closed(tmp_path):
    c=client(tmp_path,limits=LLMLimits())
    with pytest.raises(ModelUnavailable) as error: ModelSession(c,"python").request("translate","a.py",SOURCE)
    assert error.value.code=="input_budget_exceeded" and not c.calls
    c=client(tmp_path,lambda s,u:"x"*8193)
    with pytest.raises(ModelUnavailable) as error: ModelSession(c,"python").request("translate","a.py",SOURCE)
    assert error.value.code=="output_budget_exceeded" and c.cost_usd==0


def test_live_missing_key_or_mode_switch_cannot_authorize_model_requests(tmp_path):
    with pytest.raises(ModelUnavailable): LLMClient(tmp_path/"absent.env",mode="live")
    c=client(tmp_path); session=ModelSession(c,"python"); c.mode="live"
    with pytest.raises(ModelUnavailable) as error: session.request("translate","a.py",SOURCE)
    assert error.value.code=="live_disabled" and not c.calls
    with pytest.raises(ModelUnavailable) as error: ModelSession(c,"python")
    assert error.value.code=="live_disabled"


def test_default_mock_is_not_a_translation_or_fixture_fallback(tmp_path):
    c=LLMClient(tmp_path/"absent.env",mode="mock",limits=LIMITS)
    with pytest.raises(ModelUnavailable): StructuredTranslator(ModelSession(c,"python")).translate("a.py",SOURCE)
    assert len(c.attempts)==1 and not c.tokens_in


def test_security_generator_uses_minimal_finding_and_returns_typed_bound_proposal(tmp_path):
    observed=[]
    def respond(system,user): observed.append(json.loads(user)); return responder(system,user)
    c=client(tmp_path,respond); session=ModelSession(c,"python")
    generator=LLMFixGenerator(session=session,rules=("B602",),max_proposals=1)
    finding={"id":"finding","file":"a.py","scanner_test":"B602","scope":"total","line":2,"note":"PRIVATE RAW SCAN","unrelated":"never send"}
    proposal=generator.generate(finding,SOURCE)
    assert proposal.mode=="mock" and proposal.finding_id==finding["id"]
    assert "note" not in observed[0]["finding"] and "unrelated" not in observed[0]["finding"]
    assert generator.generate(finding,SOURCE) is None and len(c.calls)==1


def test_private_literals_round_trip_but_model_credential_never_enters_prompt_or_evidence(tmp_path):
    observed=[]; key="unit-private-model-key-do-not-export"
    source="API_KEY = 'fake-application-secret'\n"+SOURCE
    def respond(system,user): observed.append(user); return responder(system,user)
    c=client(tmp_path,respond); c._api_key=key; evidence=Evidence()
    translated=StructuredTranslator(ModelSession(c,"python",evidence=evidence)).translate("a.py",source)
    assert translated==source and "fake-application-secret" not in observed[0]
    assert "__PROOFPORT_PRIVATE_1__" in observed[0] and key not in json.dumps(evidence.since(0))
    with pytest.raises(ModelUnavailable) as error: ModelSession(c,"python").request("translate","a.py",f"API_KEY='{key}'")
    assert error.value.code=="credential_in_prompt" and len(c.calls)==1


def test_sensitive_response_is_not_exported_and_placeholders_cannot_change(tmp_path):
    c=client(tmp_path,lambda s,u:json.dumps(answer(json.loads(u),explanation="fake-application-secret")))
    with pytest.raises(ModelUnavailable) as error: StructuredTranslator(ModelSession(c,"python")).translate("a.py","API_KEY='fake-application-secret'\n"+SOURCE)
    assert error.value.code=="model_sensitive_response"
    c=client(tmp_path,lambda s,u:json.dumps(answer(json.loads(u),proposed_code="API_KEY='changed'\n"+SOURCE)))
    with pytest.raises(ModelUnavailable): StructuredTranslator(ModelSession(c,"python")).translate("a.py","API_KEY='fake-application-secret'\n"+SOURCE)


def test_retry_feedback_never_contains_golden_answers_or_raw_failure_bodies(tmp_path):
    feedback={"syntax":{"ran":True,"passed":False,"errors":["raw source"]},"golden":{"ran":True,"passed":False,"comparisons":[{"id":"one","matches":False,"expected":"private-golden-answer","actual":"bad"}]},"existing_tests":{"ran":True,"passed":False,"outcomes":[{"id":"test.one","status":"failed","reason":"private-body"}]}}
    summary=failure_summary(feedback)
    assert summary["mismatched_cases"]==["one"] and "private" not in json.dumps(summary)
    observed=[]
    def respond(s,u): observed.append(u); return responder(s,u)
    StructuredTranslator(ModelSession(client(tmp_path,respond),"python")).translate("a.py",SOURCE,previous=SOURCE,failures={"cases":[{"expected":"private-answer"}]})
    assert "private-answer" not in observed[0]


def test_ai_job_immutable_pairs_and_adapter_selection(tmp_path,monkeypatch):
    job=AIJob(tmp_path,"python",tmp_path/"cases.json","2.7","3.12")
    with pytest.raises(FrozenInstanceError): job.target_version="3.13"
    with pytest.raises(ValueError): AIJob(tmp_path,"php",tmp_path/"cases.json","8.3","8.4")
    seen=[]; monkeypatch.setattr("backend.ai.pipeline.execute",lambda *a,**k:seen.append((a,k)))
    LanguageRegistry().get("python").migrate_ai(job,"client")
    assert seen[0][0]==(job,) and seen[0][1]["client"]=="client"
    with pytest.raises(Exception): LanguageRegistry().get("php").migrate_ai(job,"client")


def test_rollback_retains_bad_candidate_and_restores_only_working_copy(tmp_path):
    from types import SimpleNamespace
    original=tmp_path/"copy"; original.mkdir(); (original/"a.py").write_text(SOURCE)
    working=tmp_path/"migrated"; working.mkdir(); (working/"a.py").write_text("not valid code")
    run=SimpleNamespace(verification={},evidence=Evidence())
    _rollback_model(run,tmp_path,original,working,None)
    assert (working/"a.py").read_text()==SOURCE and (original/"a.py").read_text()==SOURCE
    assert (tmp_path/"model_rejected_final/a.py").read_text()=="not valid code" and run.evidence.verify()


def test_capabilities_do_not_expose_model_modes_or_enable_live_api(project,monkeypatch):
    monkeypatch.setattr("backend.sandbox.runner.DockerRunner.available",lambda self:False)
    with TestClient(create_app(project)) as api:
        caps=api.get("/api/v1/capabilities").json()
        assert not caps["live"]["enabled"] and not caps["live"]["provider_validated"] and not caps["ai_security_fix"]["enabled"]
        assert caps["model_workflows"]["public_launchable"] is False
        assert "replay" not in caps["operations"]["migration"]["execution_modes"]
        r=api.post("/api/v1/runs/preflight",json={"operation":"migration","project_id":"legacy_shop","execution_mode":"live"})
        assert not r.json()["can_start"] and r.json()["errors"][0]["code"]=="live_disabled"


def test_final_export_rejects_tampered_model_evidence_and_restores_copy(tmp_path,monkeypatch):
    from backend.ai.pipeline import execute
    from backend.core.projects import copy_project
    source=tmp_path/"project"; source.mkdir(); (source/"a.py").write_text(SOURCE)
    def fake_worker(run,run_id,root,*args,**kwargs):
        # Explicit fake worker: test finalization only, no execution evidence.
        run.workspace=root/"backend/.work"/run_id; run.workspace.mkdir(parents=True)
        copy_project(source,run.workspace/"copy"); copy_project(source,run.workspace/"migrated")
        (run.workspace/"migrated/a.py").write_text("rejected candidate")
        run.evidence.bind(run.workspace/"evidence.log"); run.evidence.append("test_result","UNIT DOUBLE, not execution")
        run.evidence.path.write_text('{}\n')
        run.pending_status="done"; run.state.hashes["unchanged"]=True
        run.verification["iterations"]=[{"syntax_passed":True,"tests_passed":True,"behavior_verified":True}]
    monkeypatch.setattr("backend.core.pipeline.execute",fake_worker)
    result,artifact=execute(AIJob(source,"python",tmp_path/"unused.json","2.7","3.12"),client=client(tmp_path),work_root=tmp_path)
    assert result["status"]==result["state"]["status"]=="failed"
    assert result["error"]["code"]=="evidence_corrupted" and not result["chain_intact"]
    assert result["behavior_verified"] is None and result["rollback"]["performed"]
    assert (artifact/"migrated/a.py").read_text()==SOURCE and (source/"a.py").read_text()==SOURCE


def test_api_credential_in_non_source_data_is_blocked_before_execution(tmp_path):
    from backend.ai.pipeline import execute
    source=tmp_path/"project"; source.mkdir(); (source/"a.py").write_text(SOURCE)
    key="unit-only-model-credential-private"; (source/"data.txt").write_text(key)
    c=client(tmp_path); c._api_key=key
    with pytest.raises(ModelUnavailable) as error: execute(AIJob(source,"python",tmp_path/"unused.json","2.7","3.12"),client=c,work_root=tmp_path)
    assert error.value.code=="credential_in_prompt" and not c.calls


def test_private_placeholder_expansion_cannot_amplify_candidate_size():
    private=PrivateContext(); source="API_KEY='"+"x"*100000+"'\n"
    redacted=private.protect(source)
    assert len(redacted)<100
    with pytest.raises(ModelUnavailable): private.restore("__PROOFPORT_PRIVATE_1__"*3,source,"security")
