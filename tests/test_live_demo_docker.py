"""Real Docker verification of explicit retained-response HTTP replay, NEVER Meta.

An isolated ignored Git test root prevents mock transport artifacts from being
confused with genuine retained runs. No fixture is substituted if a real saved
candidate is absent. All project code executes only in the Docker harness.
"""
import json
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import httpx2
import pytest

from backend import release
from backend.ai import first_live,first_php_live
from backend.api.main import create_app
from backend.llm.client import LLMClient
from backend.sandbox.runner import DockerRunner
KEY="unit-only-p13-docker-replay"
TEXT=("MODEL_API_KEY="+KEY+"\nLLM_MODE=live\nMODEL_NAME=muse-spark-1.3\nMODEL_BASE_URL=https://api.meta.ai/v1\n"
      "PRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\nLIVE_DEMO_KEY_CONFIRMED_NEW=true\nLIVE_DEMO_APPROVED=true\n")

pytestmark=pytest.mark.docker


@pytest.mark.parametrize("kind,mismatch,fault",[("python",False,None),("php",False,None),("python",True,None),
    ("python",False,"timeout"),("python",False,"invalid_json")])
def test_live_demo_api_real_docker_with_explicit_http_replay(kind,mismatch,fault,monkeypatch):
    runner=DockerRunner()
    if not runner.available():pytest.skip("Docker unavailable; no host fallback")
    folder,source,_=release.SAVED[kind];recording=release.ROOT/"backend/.work"/folder
    if not recording.is_dir():pytest.skip("Genuine retained candidate absent; no authored patch substitute")
    release.verify_recording(kind,recording,release.ROOT/source)
    file=first_live.FILE if kind=="python" else first_php_live.FILE
    code=(recording/"candidate"/file).read_text(encoding="utf-8")
    if mismatch:
        assert "def mean(values):" in code
        code=code.replace("def mean(values):","def mean(values):\n    return 12345",1)
    root=release.ROOT/"backend/.tmp"/("d13-"+uuid4().hex[:8]);root.mkdir()
    shutil.copytree(release.ROOT/"samples/legacy_shop",root/"samples/legacy_shop")
    for name in ("legacy_shop","php_shop","php_profiles"):
        shutil.copytree(release.ROOT/"tests/fixtures"/name,root/"tests/fixtures"/name)
    subprocess.run(["git","init","-q",str(root)],check=True)
    (root/".gitignore").write_text("backend/.tmp/\nbackend/.work/\n")
    private=root/"backend/.tmp";private.mkdir(parents=True);env=private/"meta-demo.env";env.write_text(TEXT)
    monkeypatch.setattr(first_live,"ROOT",root);monkeypatch.setattr(first_live,"SOURCE",root/"samples/legacy_shop")
    monkeypatch.setattr(first_php_live,"ROOT",root);monkeypatch.setattr(first_php_live,"SOURCE",root/"tests/fixtures/php_shop")
    monkeypatch.setattr(first_php_live,"CASES",root/"tests/fixtures/php_profiles/cases.json")
    # Any accidental ordinary HTTP transport is a test failure, not a fallback.
    def forbidden(*a,**kw):pytest.fail("Real HTTP forbidden during P13 tests")
    monkeypatch.setattr(httpx.HTTPTransport,"handle_request",forbidden)
    monkeypatch.setattr(httpx2.HTTPTransport,"handle_request",forbidden)
    calls=[]
    def answer(request):
        calls.append(request)
        if fault=="timeout":raise httpx2.ReadTimeout(KEY,request=request)
        body=json.loads(request.content);context=json.loads(body["messages"][1]["content"])
        patch={k:context[k] for k in ("task","language","file","source_sha256","finding_id")}
        patch.update(explanation="Explicit retained-code HTTP replay TEST, no Meta request",proposed_code=code,
            behavior_impact="preserves",confidence=0.8,review_areas=[])
        return httpx2.Response(200,json={"id":"p13-http-replay-test","object":"chat.completion","created":1,"model":"muse-spark-1.3",
            "choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":'{"incomplete":' if fault=="invalid_json" else json.dumps(patch)}}],
            "usage":{"prompt_tokens":100,"completion_tokens":80,"total_tokens":180}})
    app=create_app(root);demo=app.state.live_demo
    demo.catalog_client=lambda **kw:httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={"data":[{"id":"muse-spark-1.3"}]})),**kw)
    demo.client_factory=lambda *a,**kw:LLMClient(*a,http_client=httpx2.Client(transport=httpx2.MockTransport(answer),trust_env=False),**kw)
    name="python_mathutils" if kind=="python" else "php_legacy"
    with TestClient(app) as client:
        assert client.post("/api/v1/live-demo/model-check").json()["status"]=="available"
        approved=client.post("/api/v1/live-demo/confirm",json={"profile":name,"consent":True})
        assert approved.status_code==200,approved.text
        started=client.post("/api/v1/live-demo/runs",json={"profile":name,"approval_id":approved.json()["approval_id"]},headers={"Idempotency-Key":"p13-replay-test"})
        assert started.status_code==202,started.text
        run_id=started.json()["run_id"];deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            details=client.get("/api/v1/runs/"+run_id).json()
            if details["finalized"]:break
            time.sleep(0.05)
        assert details["finalized"],details
        report=client.get(f"/api/runs/{run_id}/report?format=json").json()
        assert report["state"]["hashes"]["unchanged"] and report["state"]["chain_intact"]
        assert KEY not in json.dumps(report) and "No security audit/fix" in report["notice"]
        assert client.get(f"/api/runs/{run_id}/report?format=html").status_code==200
        assert client.get(f"/api/runs/{run_id}/events?since=2").json()
        v=report["verification"];scope=v["live_demo"]
        if fault:
            assert len(calls)==1 and report["state"]["status"]=="failed" and not v["ai_migration"] and v["rollback"]
            assert report["state"]["error"]["code"]==("model_timeout" if fault=="timeout" else "model_invalid_response")
            assert scope["billing_unknown"] is (fault=="timeout")
        elif mismatch:
            assert len(calls)==2 and report["state"]["status"]=="failed" and v["rollback"] and not v["ai_migration"]
            assert scope["golden_matched"]<31
        else:
            assert len(calls)==1 and report["state"]["status"]=="done" and v["ai_migration"]
            assert report["state"]["metrics"]["lines_migrated"]>0
            assert scope["golden_matched"]==scope["golden_total"]==(31 if kind=="python" else 22)
            assert v["target_tests"]["tests_run"]==(3 if kind=="python" else 9)
        run=app.state.runs.get(run_id)
        assert v["model_calls"]==len(calls)<=2 and report["state"]["metrics"]["cost_usd"]<=0.05
        if fault or mismatch:
            raw=root/"backend/.work"/scope["raw_artifact_id"]
            assert (raw/"candidate"/file).read_bytes()==(raw/"original"/file).read_bytes()
        # Corruption of the app bridge chain cannot preserve a successful label.
        if not mismatch and not fault:
            with (run.workspace/"evidence.log").open("a") as stream:stream.write('{"corrupted":true}\n')
            assert client.get("/api/v1/runs/"+run_id).json()["state"]["status"]=="failed"
        assert app.state.runs.active is None and not run.runner._active
