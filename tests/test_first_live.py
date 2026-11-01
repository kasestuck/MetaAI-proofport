"""P8 orchestration tests: in-memory HTTP and explicit fake Docker results only."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import httpx2
import pytest

from backend.ai import first_live as p8
from backend.ai.provider import ModelSession, ModuleLiveApproval
from backend.core.evidence import entry_hash
from backend.llm.client import LLMClient, ModelUnavailable


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    # Copy original bytes for orchestration tests; never import/execute samples.
    source = tmp_path / "samples/legacy_shop"
    source.parent.mkdir()
    shutil.copytree(p8.SOURCE, source)
    monkeypatch.setattr(p8, "ROOT", tmp_path)
    monkeypatch.setattr(p8, "SOURCE", source)
    cases = tmp_path / "tests/fixtures/legacy_shop"
    cases.mkdir(parents=True)
    real = Path(__file__).parent / "fixtures/legacy_shop/cases.json"
    shutil.copyfile(real, cases / "cases.json")
    for name in ("LLM_MODE", "MODEL_API_KEY", "MODEL_NAME", "MODEL_BASE_URL", "PRICE_IN_PER_MTOK", "PRICE_OUT_PER_MTOK"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "private.env"
    env.write_text("MODEL_API_KEY=unit-only-private\nLLM_MODE=live\nMODEL_NAME=muse-spark-1.3\n"
                   "MODEL_BASE_URL=https://api.meta.ai/v1\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n")
    monkeypatch.setattr(p8, "credential_git_check", lambda *a:None)

    class Runner:
        _images = {}
        def available(self): return True
        def image_id(self, tag):
            self._images[tag] = "sha256:" + sha256(tag.encode()).hexdigest()
            return self._images[tag]
    runner = Runner()
    fake_tests = {"python":[2,7,18], "tests_run":3,
                  "outcomes":[{"id":"MathTests."+str(i), "status":"passed"} for i in range(3)]}
    def invoke(runner, image, source, action, cases=None, evidence=None):
        if evidence: evidence.append("unit_fake_sandbox", action)
        if action == "tests": return fake_tests
        if action == "compile": return {"python":[3,12,16], "errors":[{"file":p8.FILE,"type":"SyntaxError"}]}
        return {"python":[2,7,18], "cases":[{"id":c["id"], "module":c["module"], "steps":[]} for c in cases]}
    monkeypatch.setattr(p8, "invoke", invoke)
    monkeypatch.setattr(p8, "analyze", lambda *a:{"python":[2,7,18], "modules":[{"name":"legacy_shop.mathutils"}]})
    manifest, workspace = p8.prepare(env, runner=runner)
    assert manifest["paid_requests"] == 0 and manifest["golden_cases"] == 31
    return workspace, env, runner


def model_client(env, *, outcome="success", observed=None):
    def transport(request):
        if observed is not None: observed.append(request)
        if outcome == "timeout": raise httpx2.ReadTimeout("unit-only-private", request=request)
        context = json.loads(json.loads(request.content)["messages"][1]["content"])
        patch = {k:context[k] for k in ("task", "language", "file", "source_sha256", "finding_id")}
        patch.update(explanation="Explicit in-memory unit response, not real AI", proposed_code="def unit_candidate():\n    return 1\n",
                     behavior_impact="preserves", confidence=0.8, review_areas=[])
        content = "not JSON" if outcome == "invalid" else json.dumps(patch)
        return httpx2.Response(200, json={"id":"unit", "object":"chat.completion", "created":1,
            "model":"muse-spark-1.3", "choices":[{"index":0, "finish_reason":"stop", "message":{"role":"assistant", "content":content}}],
            "usage":{"prompt_tokens":100, "completion_tokens":80, "total_tokens":180}})
    return LLMClient(env, allow_live=True, limits=p8.LIMITS,
        http_client=httpx2.Client(transport=httpx2.MockTransport(transport), trust_env=False))


def checks(success=True, syntax=True):
    return {"syntax_passed":syntax, "tests_passed":success if syntax else None,
            "behavior_verified":success if syntax else None,
            "comparisons":[{"id":"unit.case", "matches":success}]}


def test_prepare_has_no_client_and_preserves_existing_assertions(prepared):
    workspace, env, runner = prepared
    original = (p8.SOURCE / "tests/test_legacy_shop.py").read_text()
    projected, body = p8.scoped_tests(original)
    assert body in original and body in projected
    assert (workspace / "original/tests/test_legacy_shop.py").read_text() == projected
    assert not (workspace / "execution_started.json").exists()


def test_live_session_needs_explicit_approval_and_rejects_security(prepared):
    workspace, env, runner = prepared
    client = model_client(env)
    with pytest.raises(ModelUnavailable, match="disabled"): ModelSession(client, "python")
    source = (workspace / "original" / p8.FILE).read_text()
    session = ModelSession(client, "python", live_approval=ModuleLiveApproval(p8.FILE, sha256(source.encode()).hexdigest()))
    with pytest.raises(ModelUnavailable): session.request("security", p8.FILE, source, finding={"id":"one"})
    with pytest.raises(ModelUnavailable): session.request("translate", p8.FILE, source + "\n")
    assert not client.attempts
    client.close()


@pytest.mark.parametrize("cap,calls", [("0.051",3), ("0.05",4)])
def test_approval_rejects_larger_budgets(prepared,cap,calls):
    from decimal import Decimal
    workspace, env, runner = prepared
    client = model_client(env)
    client.limits = replace(p8.LIMITS, max_calls=calls, max_cost_usd=Decimal(cap))
    with pytest.raises(ModelUnavailable):
        ModelSession(client,"python",live_approval=ModuleLiveApproval(p8.FILE,"a"*64))
    assert not client.attempts
    client.close()


def test_no_paid_permission_creates_no_execution_marker(prepared):
    workspace, env, runner = prepared
    with pytest.raises(ModelUnavailable): p8.execute(workspace,env,runner=runner)
    assert not (workspace / "execution_started.json").exists()


def test_mocked_success_seals_response_checks_and_report(prepared,monkeypatch):
    workspace, env, runner = prepared
    monkeypatch.setattr(p8,"verify_candidate",lambda *a:checks())
    report = p8.execute(workspace,env,acknowledged=True,runner=runner,client=model_client(env))
    assert report["status"] == "done" and report["ai_migration"] and report["model_calls"] == 1
    assert report["originals_unchanged"] and report["chain_intact"]
    response=json.loads((workspace / "response_01.json").read_text())
    assert response["mode"] == "live" and len(response["prompt_hash"]) == 64
    assert json.loads((workspace / "report.json").read_text()) == report
    assert "&quot;" in (workspace / "report.html").read_text()
    for name, expected in report["artifact_hashes"].items():
        assert p8.digest(workspace / name) == expected
    events = report["events"]
    assert all(e["entry_hash"] == entry_hash(e) for e in events)
    assert "unit-only-private" not in (workspace / "report.json").read_text()


@pytest.mark.parametrize("first", [checks(False,False),checks(False,True)])
def test_verified_failure_allows_bounded_repair_without_answers(prepared,monkeypatch,first):
    workspace, env, runner = prepared
    results=iter([first, checks()])
    monkeypatch.setattr(p8,"verify_candidate",lambda *a:next(results))
    requests=[]
    report=p8.execute(workspace,env,acknowledged=True,runner=runner,client=model_client(env,observed=requests))
    assert report["status"] == "done" and report["ai_fix_loop_used"] and report["model_calls"] == 2
    context=json.loads(json.loads(requests[1].content)["messages"][1]["content"])
    assert context["previous"] and context["failures"]["repair_requested"]
    assert "expected" not in context["failures"]


def test_three_mismatches_roll_back_and_prevent_restart(prepared,monkeypatch):
    workspace, env, runner = prepared
    monkeypatch.setattr(p8,"verify_candidate",lambda *a:checks(False))
    report=p8.execute(workspace,env,acknowledged=True,runner=runner,client=model_client(env))
    assert report["status"] == "failed" and report["model_calls"] == 3 and report["rollback"]
    assert (workspace / "candidate" / p8.FILE).read_bytes() == (workspace / "original" / p8.FILE).read_bytes()
    assert (workspace / "rejected_final").is_dir()
    with pytest.raises(FileExistsError): p8.execute(workspace,env,acknowledged=True,runner=runner)


@pytest.mark.parametrize("outcome", ["timeout","invalid"])
def test_transport_or_json_error_stops_without_retry(prepared,outcome):
    workspace, env, runner = prepared
    requests=[]
    report=p8.execute(workspace,env,acknowledged=True,runner=runner,client=model_client(env,outcome=outcome,observed=requests))
    assert report["status"] == "failed" and report["model_calls"] == len(requests) == 1
    assert report["rollback"] and report["chain_intact"]
    assert "unit-only-private" not in (workspace / "report.json").read_text()


@pytest.mark.parametrize("file", ["original/legacy_shop/mathutils.py","golden.json","cases.json","preparation.log"])
def test_tampered_preparation_stops_before_client(prepared,file):
    workspace, env, runner = prepared
    with (workspace / file).open("a") as stream: stream.write("\nchanged\n")
    with pytest.raises(ValueError): p8.execute(workspace,env,acknowledged=True,runner=runner)
    assert not (workspace / "execution_started.json").exists()


def test_image_changed_stops_before_client(prepared):
    workspace, env, runner = prepared
    runner._images["python:2.7"]="sha256:changed"
    runner.image_id=lambda tag:runner._images[tag]
    with pytest.raises(ValueError): p8.execute(workspace,env,acknowledged=True,runner=runner)


def test_real_original_changed_stops_before_client(prepared):
    workspace, env, runner = prepared
    with (p8.SOURCE / p8.FILE).open("a") as stream: stream.write("\n# unit copy only\n")
    with pytest.raises(ModelUnavailable): p8.execute(workspace,env,acknowledged=True,runner=runner)


def test_three_full_reservations_fit_approved_budget():
    from decimal import Decimal
    amount=(p8.LIMITS.max_input_tokens*Decimal("1.25")+p8.LIMITS.max_output_tokens*Decimal("4.25"))/1000000
    assert amount*3 == Decimal("0.049344") <= p8.LIMITS.max_cost_usd


def test_syntax_failure_skips_behavior_and_suite(monkeypatch):
    actions=[]
    def invoke(runner,image,source,action,**kw):
        actions.append(action)
        return {"errors":[{"type":"SyntaxError"}]}
    monkeypatch.setattr(p8,"invoke",invoke)
    result=p8.verify_candidate(None,None,[],{}, {},None)
    assert actions == ["compile"] and not result["syntax_passed"]
    assert result["tests_passed"] is result["behavior_verified"] is None


@pytest.mark.parametrize("changed", ["golden","suite","neither"])
def test_comparison_and_existing_test_ids_are_required(monkeypatch,changed):
    expected={"id":"case", "module":"legacy_shop.mathutils", "steps":[{"value":{"t":"int","v":2}}]}
    observed=json.loads(json.dumps(expected))
    if changed == "golden": observed["steps"][0]["value"]["v"]=3
    baseline={"tests_run":1,"outcomes":[{"id":"MathTests.test_mean", "status":"passed"}]}
    tests=json.loads(json.dumps(baseline))
    if changed == "suite": tests["outcomes"][0]["id"]="replacement"
    def invoke(runner,image,source,action,cases=None,evidence=None):
        return {"compile":{"errors":[]},"cases":{"cases":[observed],"python":[3,12,16]},"tests":tests}[action]
    monkeypatch.setattr(p8,"invoke",invoke)
    result=p8.verify_candidate(None,None,[],{"cases":[expected]},baseline,None)
    assert result["syntax_passed"]
    assert result["behavior_verified"] == (changed != "golden")
    assert result["tests_passed"] == (changed != "suite")


@pytest.mark.parametrize("file", ["report.json", "report.html", "evidence.log", "response_01.json", "candidate/legacy_shop/mathutils.py"])
def test_export_verifier_detects_tampering(prepared,monkeypatch,file):
    workspace, env, runner = prepared
    monkeypatch.setattr(p8,"verify_candidate",lambda *a:checks())
    p8.execute(workspace,env,acknowledged=True,runner=runner,client=model_client(env))
    assert p8.verify_export(workspace)
    with (workspace / file).open("a") as stream: stream.write("\nchanged\n")
    with pytest.raises(ValueError): p8.verify_export(workspace)
