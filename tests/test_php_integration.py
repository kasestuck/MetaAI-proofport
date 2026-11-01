"""Bounded real PHP Docker E2E; no downloads, models, host PHP or fake verdicts."""

import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app
from backend.core.evidence import entry_hash
from backend.php.pipeline import PHPJob, execute
from backend.php.receipts import ROOT, DEMO, PROFILES, read_receipt, supported, verify_demo
from backend.php.runtime import local_images, source_hashes
from backend.sandbox.runner import DockerRunner


pytestmark=pytest.mark.docker


@pytest.fixture(scope="module")
def real_proof():
    runner=DockerRunner()
    if not runner.available(): pytest.skip("Docker unavailable; PHP E2E not verified")
    from backend.languages.runtimes import php_runtimes
    if not all(r["available"] for r in php_runtimes(runner,docker=True)):
        pytest.skip("Approved PHP images missing; never pull during tests")
    receipt,result=verify_demo()
    return receipt,result


@pytest.fixture(autouse=True)
def no_meta(monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**k:pytest.fail("Offline PHP may not construct Meta SDK"))
    monkeypatch.setattr("backend.llm.client.LLMClient.complete",lambda *a,**k:pytest.fail("No paid calls"))


def test_real_migration_golden_fix_rollback_and_receipt(real_proof):
    receipt,r=real_proof
    assert r["status"]=="done" and r["source_syntax"]["passed"] and r["syntax_passed"] and r["behavior_verified"]
    assert r["golden_case_count"]==22 and len(r["comparisons"])==22 and all(c["matches"] for c in r["comparisons"])
    assert r["source_tests"]["tests_run"]==r["target_tests"]["tests_run"]==9
    assert r["source_tests"]["passed"] and r["target_tests"]["passed"]
    fix=r["security_fix"]
    assert [a["status"] for a in fix["attempts"]]==["fixed","needs_review","fix_reverted"]
    assert fix["attempts"][1]["checks"]["golden"]["passed"] is False
    assert fix["attempts"][1]["checks"]["existing_tests"]["passed"] is False
    assert fix["attempts"][2]["checks"]["syntax"]["passed"] is False
    assert not fix["attempts"][2]["checks"]["golden"]["ran"]
    assert len(r["security_before"]["findings"])==10 and len(r["security_after"]["findings"])==9
    assert not r["security_after"]["confirmed_findings"]
    assert r["originals_unchanged"] and r["chain_intact"] and r["model_calls"]==0 and not r["ai_migration"]
    artifact=ROOT/"backend/.work"/receipt["artifact_id"]
    exported=json.loads((artifact/"report.json").read_text())
    previous="0"*64
    for event in exported["events"]:
        assert event["prev_hash"]==previous and entry_hash(event)==event["entry_hash"]
        previous=event["entry_hash"]
    assert read_receipt(ROOT)==receipt and all(receipt["checks"].values())
    assert source_hashes(ROOT/DEMO)==receipt["source_hashes"]
    golden=json.loads((artifact/"golden.json").read_text())
    assert {g["status"] for g in golden}=={"return","exception","runtime_error"}
    assert any(g["stdout"] for g in golden) and any(g["warnings"] for g in golden)
    assert any(g["deprecations"] for g in golden)
    assert (artifact/"report.html").exists()


def test_real_php_http_migration_audit_and_compatibility(real_proof):
    original=source_hashes(ROOT/DEMO)
    body={"language":"php","operation":"migration","project_id":"php_shop","source_version":"7.4","target_version":"8.3",
          "execution_mode":"offline_fixtures","fixture_profile_id":"php_shop_74_83","cases_profile_id":"php_shop_golden","max_iterations":1}
    with TestClient(create_app(ROOT)) as client:
        caps=client.get("/api/v1/capabilities").json()
        assert set(caps["languages"]["php"]["supported_operations"])=={"migration","audit","compatibility"}
        assert caps["operations"]["migration"]["pairs"]==[["2.7","3.12"]]
        catalog=client.get("/api/v1/projects").json()
        assert next(p for p in catalog["projects"] if p["project_id"]=="php_shop")["language"]=="php"
        def run(request,key):
            preflight=client.post("/api/v1/runs/preflight",json=request).json()
            assert preflight["can_start"],preflight
            response=client.post("/api/v1/runs",json=request,headers={"Idempotency-Key":key})
            assert response.status_code==202,response.text
            run_id=response.json()["run_id"]
            for _ in range(1800):
                details=client.get("/api/v1/runs/"+run_id).json()
                if details["finalized"]: break
                time.sleep(.05)
            assert details["finalized"],details
            report=client.get(f"/api/runs/{run_id}/report?format=json").json()
            assert report["state"]==client.get("/api/runs/"+run_id).json()==details["state"]
            assert details["state"]["chain_intact"] and details["state"]["hashes"]["unchanged"]
            assert client.get(f"/api/runs/{run_id}/report?format=html").status_code==200
            assert client.get(f"/api/runs/{run_id}/events?since=1").json()
            assert not details["execution"]["ai_generated"] and details["state"]["metrics"]["cost_usd"]==0
            assert report["verification"]["control"]["parameters"]==details["parameters"]
            return details,report
        migrated,report=run(body,"p623-php-real-migration")
        assert migrated["state"]["status"]=="done",migrated
        assert migrated["result"]["compatibility"]["level"]=="behavior_verified"
        assert report["verification"]["target_tests"]["tests_run"]==9
        assert migrated["state"]["metrics"]["tests_passed"]==22
        audited,report=run({"language":"php","operation":"audit","project_id":"php_shop","source_version":"7.4"},"p623-php-real-audit")
        assert audited["state"]["status"]=="done" and not report["verification"]["project_executed"]
        assert audited["result"]["compatibility"]["level"]=="not_verified"
        # The unchanged legacy syntax MUST fail on 8.3; never claim compatibility.
        compatibility,report=run({"language":"php","operation":"compatibility","project_id":"php_shop","source_version":"7.4","target_version":"8.3","verification_level":"syntax"},"p623-php-real-negative-compatibility")
        assert compatibility["state"]["status"]=="failed"
        assert compatibility["result"]["compatibility"]["syntax_passed"] is False
        assert compatibility["result"]["compatibility"]["tests_passed"] is None
    assert source_hashes(ROOT/DEMO)==original


def test_real_positive_compatibility_on_retained_verified_candidate():
    receipt=read_receipt(ROOT)
    if receipt is None: pytest.skip("Run the explicit demo proof first; no unverified candidate fallback")
    artifact=ROOT/"backend/.work"/receipt["artifact_id"]
    previous=json.loads((artifact/"report.json").read_text())
    candidate=artifact/previous["accepted_copy"]
    assert source_hashes(candidate)==previous["accepted_hashes"]
    r,_=execute(PHPJob(candidate,operation="compatibility",cases=ROOT/PROFILES/"cases.json"))
    assert r["status"]=="done" and r["syntax_passed"] and r["tests_passed"] and r["behavior_verified"]
    assert r["golden_case_count"]==22 and r["source_tests"]["tests_run"]==r["target_tests"]["tests_run"]==9
    assert not r["migration_performed"] and r["originals_unchanged"] and r["chain_intact"]


def test_php_sandbox_denies_network_and_persistent_writes(tmp_path):
    runner=DockerRunner(); images=local_images(runner)
    project=tmp_path/"readonly"; project.mkdir(); (project/"data.txt").write_text("owned probe")
    # Trusted probe only; all PHP execution is still in the same bounded sandbox.
    code = '''$status=file_get_contents('/proc/self/status');
    $interfaces=array_values(array_diff(scandir('/sys/class/net'),['.','..']));
    $routes=array_values(array_filter(explode("\\n",trim(file_get_contents('/proc/net/route')))));
    preg_match('/^Uid:\\s+(\\d+)/m',$status,$uid);
    echo json_encode(['uid'=>(int)$uid[1], 'only_loopback'=>$interfaces===['lo'], 'no_ipv4_routes'=>count($routes)===1,
      'source_readonly'=>@file_put_contents('/src/probe','x')===false,
      'root_readonly'=>@file_put_contents('/proofport-probe','x')===false,
      'tmp_writable'=>file_put_contents('/tmp/probe','x')===1,
      'no_key'=>getenv('MODEL_API_KEY')===false,'no_socket'=>!file_exists('/var/run/docker.sock')]);'''
    observed=runner.run(images["8.3"],project,["php","-n","-r",code])
    assert observed.exit_code==0 and not observed.timed_out and not observed.output_exceeded
    proof=json.loads(observed.stdout)
    assert proof.pop("uid")==65534 and all(v is True for v in proof.values())
    assert not (project/"probe").exists()
