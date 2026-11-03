"""Admission/catalog tests: fake HTTP and Docker metadata; no model/project execution."""
import asyncio
import json
import subprocess
import time
import logging
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.ai import demo as module
from backend.llm.client import LLMClient,ModelUnavailable

KEY = "unit-only-p13-new-key"
TEXT = ("MODEL_API_KEY="+KEY+"\nLLM_MODE=live\nMODEL_NAME=muse-spark-1.3\nMODEL_BASE_URL=https://api.meta.ai/v1\n"
        "PRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\nLIVE_DEMO_KEY_CONFIRMED_NEW=true\nLIVE_DEMO_APPROVED=true\n")


@pytest.fixture
def setup(project, monkeypatch):
    scoped = project/"samples/legacy_shop/legacy_shop"
    scoped.mkdir()
    (scoped/"mathutils.py").write_text("# Unit admission input only; not executed\n")
    cases=project/"tests/fixtures/legacy_shop";cases.mkdir(parents=True)
    (cases/"cases.json").write_text('{"cases":[]}')
    subprocess.run(["git","init","-q",str(project)],check=True)
    (project/".gitignore").write_text("backend/.tmp/\n")
    folder=project/"backend/.tmp"; folder.mkdir(parents=True)
    config=folder/"meta-demo.env"; config.write_text(TEXT)
    monkeypatch.setattr("backend.api.main.docker_available",lambda:False)
    monkeypatch.setattr(module.DockerRunner,"available",lambda self:True)
    monkeypatch.setattr(module.DockerRunner,"image_id",lambda self,tag:"sha256:"+"1"*64)
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda **kw:pytest.fail("No real model client in admission tests"))
    app=create_app(project); demo=app.state.live_demo
    async def waiting(run_id): await asyncio.Event().wait()
    demo.store.live_demo_worker=waiting
    calls=[]
    def reply(request):
        calls.append(request)
        assert request.method=="GET" and str(request.url)=="https://api.meta.ai/v1/models"
        return httpx.Response(200,json={"data":[{"id":"muse-spark-1.3"}]})
    demo.catalog_client=lambda **kw:httpx.Client(transport=httpx.MockTransport(reply),**kw)
    with TestClient(app) as client: yield client,demo,config,calls


def authorize(client):
    assert client.post("/api/v1/live-demo/model-check").json()["status"]=="available"
    r=client.post("/api/v1/live-demo/confirm",json={"profile":"python_mathutils","consent":True})
    assert r.status_code==200,r.text
    return {"profile":"python_mathutils","approval_id":r.json()["approval_id"]}


def test_missing_new_key_never_uses_old_env_or_sdk(setup):
    client,demo,config,calls=setup;config.unlink()
    r=client.get("/api/v1/live-demo").json()
    assert r["enabled"] is False and r["error"]["code"]=="key_required" and not calls
    assert client.get("/api/health").status_code==200


def test_retired_key_is_refused_locally(setup):
    client,demo,config,calls=setup
    (config.parent/"meta-smoke.env").write_text("MODEL_API_KEY="+KEY)
    r=client.post("/api/v1/live-demo/model-check")
    assert r.status_code==503 and r.json()["error"]["code"]=="revoked_key" and not calls
    assert KEY not in r.text


@pytest.mark.parametrize("status",[401,403,429,500])
def test_catalog_failure_is_not_generation_or_retry(setup,status):
    client,demo,config,calls=setup
    def reply(req): calls.append(req);return httpx.Response(status,json={"error":{"message":KEY}})
    demo.catalog_client=lambda **kw:httpx.Client(transport=httpx.MockTransport(reply),**kw)
    r=client.post("/api/v1/live-demo/model-check")
    assert len(calls)==1 and r.json()["generation_calls"]==0 and r.json()["error"]
    assert KEY not in r.text and not client.get("/api/v1/live-demo").json()["enabled"]


@pytest.mark.parametrize("kind",["timeout","json","empty","missing_model"])
def test_catalog_invalid_and_timeout_fail_closed(setup,kind):
    client,demo,config,calls=setup
    def reply(req):
        calls.append(req)
        if kind=="timeout":raise httpx.ReadTimeout(KEY,request=req)
        if kind=="json":return httpx.Response(200,content=b'{"data":')
        return httpx.Response(200,json={} if kind=="empty" else {"data":[]})
    demo.catalog_client=lambda **kw:httpx.Client(transport=httpx.MockTransport(reply),**kw)
    r=client.post("/api/v1/live-demo/model-check")
    assert r.json()["error"] and len(calls)==1 and KEY not in r.text


def test_catalog_alone_and_forged_consent_cannot_spend(setup):
    client,demo,config,calls=setup
    config.write_text(TEXT.replace("LIVE_DEMO_APPROVED=true","LIVE_DEMO_APPROVED=false"))
    assert client.post("/api/v1/live-demo/model-check").json()["status"]=="available"
    r=client.post("/api/v1/live-demo/confirm",json={"profile":"python_mathutils","consent":True})
    assert r.status_code==403 and not demo.store.runs
    assert client.get("/api/v1/live-demo").json()["model_status"]=="available"


@pytest.mark.parametrize("extra",[{"max_cost_usd":99},{"source_path":"../secret"},{"api_key":KEY}])
def test_browser_cannot_supply_budget_path_or_secret(setup,extra):
    client,demo,config,calls=setup
    r=client.post("/api/v1/live-demo/confirm",json={"profile":"python_mathutils","consent":True,**extra})
    assert r.status_code==422 and KEY not in r.text and not demo.store.runs


def test_real_consent_and_model_access_are_required(setup):
    client,demo,config,calls=setup
    assert client.post("/api/v1/live-demo/confirm",json={"profile":"python_mathutils","consent":False}).status_code==422
    assert client.post("/api/v1/live-demo/confirm",json={"profile":"python_mathutils","consent":True}).status_code==503
    assert not demo.store.runs


def test_single_use_idempotency_and_shared_busy_gate(setup):
    client,demo,config,calls=setup; body=authorize(client)
    headers={"Idempotency-Key":"p13-unit-first"}
    first=client.post("/api/v1/live-demo/runs",json=body,headers=headers)
    assert first.status_code==202,first.text
    assert client.post("/api/v1/live-demo/runs",json=body,headers=headers).json()==first.json()
    assert len(demo.store.runs)==1
    assert client.post("/api/runs",json={"source_path":"samples/legacy_shop"}).status_code==409
    assert client.post("/api/v1/live-demo/runs",json=body,headers={"Idempotency-Key":"p13-another"}).status_code==409
    assert client.get("/api/v1/live-demo").json()["active_run_id"]==first.json()["run_id"]
    assert KEY not in client.get("/api/v1/runs/"+first.json()["run_id"]).text


@pytest.mark.parametrize("change",["source","config","image","expired","restart"])
def test_changed_binding_cannot_reuse_approval(setup,change,monkeypatch):
    client,demo,config,calls=setup;body=authorize(client)
    if change=="source":(demo.root/"samples/legacy_shop/mathutils.py").write_text("# edited unit input")
    elif change=="config":config.write_text(TEXT+"# changed configuration\n")
    elif change=="image":monkeypatch.setattr(module.DockerRunner,"image_id",lambda *a:"sha256:"+"2"*64)
    elif change=="expired":demo.tickets[body["approval_id"]]=(demo.tickets[body["approval_id"]][0],0)
    else:demo.tickets.clear()
    r=client.post("/api/v1/live-demo/runs",json=body,headers={"Idempotency-Key":"p13-binding"})
    assert r.status_code in {409,503} and not demo.store.runs


def test_metadata_has_no_keys_and_no_false_available_flag(setup):
    client,demo,config,calls=setup
    before=client.get("/api/v1/live-demo").json()
    assert before["model_status"]=="not_verified" and not before["enabled"]
    assert before["limits"]["max_calls"]==2 and before["limits"]["max_cost_usd"]=="0.05"
    assert {p["id"] for p in before["profiles"]}=={"python_mathutils","php_legacy"}
    client.post("/api/v1/live-demo/model-check")
    assert client.get("/api/v1/live-demo").json()["enabled"]
    assert KEY not in json.dumps(before)


def test_isolated_client_ignores_global_key_and_mode(setup,monkeypatch):
    _,demo,config,_=setup
    monkeypatch.setenv("MODEL_API_KEY","unit-unrelated-global-key");monkeypatch.setenv("LLM_MODE","mock")
    client=LLMClient(config,mode="live",allow_live=True,limits=module.LIMITS,inherit_environment=False)
    assert client._api_key==KEY and client.mode=="live" and client._client is None
    client.close()


def test_budget_reservation_blocks_before_any_sdk_call(setup):
    _,demo,config,_=setup
    limits=replace(module.LIMITS,max_cost_usd=Decimal("0.001"))
    client=LLMClient(config,mode="live",allow_live=True,limits=limits,inherit_environment=False)
    with pytest.raises(ModelUnavailable) as error:client.complete("unit system","unit user")
    assert error.value.code=="budget_exceeded" and client._client is None and not client.attempts
    client.close()


def test_http_child_debug_logging_blocks_before_sending_key(setup):
    client,demo,config,calls=setup
    logger=logging.getLogger("httpx.unit_child");old=logger.level
    try:
        logger.setLevel(logging.DEBUG)
        r=client.post("/api/v1/live-demo/model-check")
        assert r.status_code==503 and not calls and KEY not in r.text
    finally:logger.setLevel(old)
