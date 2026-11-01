"""Real Docker checks with explicitly mocked/replayed model responses, never Meta."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from backend.ai.pipeline import AIJob
from backend.ai.provider import ModelSession, StructuredTranslator
from backend.core.projects import copy_project
from backend.core.runs import hashes_for
from backend.languages.php import analyze_php
from backend.languages.registry import LanguageRegistry
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient
from backend.php.fixtures import NEW_COMMAND
from backend.php.receipts import verify_demo, read_receipt
from backend.php.runtime import source_hashes
from backend.php.security import scan_php
from backend.sandbox.runner import DockerRunner
from backend.security.providers import LLMFixGenerator


pytestmark=pytest.mark.docker
ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT/"tests/fixtures/security_subject"
PHP=ROOT/"tests/fixtures/php_shop"
PROFILES=ROOT/"tests/fixtures/php_profiles"


def limits(calls):
    return LLMLimits(max_calls=calls,max_input_tokens=16384,max_output_tokens=8192,max_total_tokens=24576*calls)


def response(request,code,**updates):
    return json.dumps({**{k:request[k] for k in ("task","language","file","source_sha256","finding_id")},
        "proposed_code":code,"explanation":"Authored offline model-response fixture; no Meta call",
        "behavior_impact":"preserves","confidence":0.9,"review_areas":[],**updates})


@pytest.fixture(autouse=True)
def no_meta(monkeypatch):
    monkeypatch.setattr("backend.llm.client.OpenAI",lambda *a,**k:pytest.fail("A Docker proof may not spend Meta credits"))
    runner=DockerRunner()
    if not runner.available(): pytest.skip("Docker unavailable; model-response execution not verified")


def test_python_mock_syntax_behavior_retry_and_safe_security_fix(tmp_path):
    before=hashes_for(PYTHON); translations=[]
    def respond(system,user):
        req=json.loads(user); code=req["source"]
        if req["task"]=="translate":
            translations.append(req)
            if len(translations)==1: code="def invalid( :\n"
            elif len(translations)==2: code=code.replace("return value + 1","return value + 2")
        else:
            assert req["finding"]["scanner_test"]=="B602"
            code=code.replace("subprocess.check_output('/usr/bin/printf fixture', shell=True)","subprocess.check_output(['/usr/bin/printf', 'fixture'], shell=False)")
        return response(req,code)
    client=LLMClient(tmp_path/"missing.env",mode="mock",limits=limits(4),mock_responder=respond)
    job=AIJob(PYTHON,"python",PYTHON/"cases.json","2.7","3.12",max_iterations=3,security_fixes=True,security_rules=("B602",),max_security_proposals=1)
    result,artifact=LanguageRegistry().get("python").migrate_ai(job,client,work_root=tmp_path)
    assert result["status"]=="done",result.get("error")
    assert [i["syntax_passed"] for i in result["iterations"]]==[False,True,True]
    assert result["iterations"][1]["tests_passed"] is False and result["iterations"][1]["behavior_verified"] is False
    assert result["syntax_passed"] and result["tests_passed"] and result["behavior_verified"]
    assert len(result["comparisons"])==3 and all(c["matches"] for c in result["comparisons"])
    assert result["legacy_tests"]["tests_run"]==result["target_tests"]["tests_run"]==2
    assert result["response_calls"]==4 and result["model_calls"]==0 and result["ai_migration"] is False
    assert len(result["security_fix"]["fixed"])==1 and result["security_fix"]["mode"]=="mock"
    assert "shell=False" in (artifact/"migrated/commands.py").read_text()
    assert (artifact/"model_iteration_01/commands.py").read_text()=="def invalid( :\n"
    assert result["originals_unchanged"] and result["chain_intact"] and hashes_for(PYTHON)==before
    assert result["llm_budget"]["reported_cost_usd"]==0
    assert "private-golden-answer" not in json.dumps(translations)
    assert (artifact/"report.html").exists()


def test_python_security_budget_failure_rolls_back_without_fallback(tmp_path):
    before=hashes_for(PYTHON)
    client=LLMClient(tmp_path/"missing.env",mode="mock",limits=limits(1),mock_responder=lambda s,u:response(json.loads(u),json.loads(u)["source"]))
    job=AIJob(PYTHON,"python",PYTHON/"cases.json","2.7","3.12",security_fixes=True,security_rules=("B602",))
    result,artifact=LanguageRegistry().get("python").migrate_ai(job,client,work_root=tmp_path)
    assert result["status"]=="failed" and result["error"]["code"]=="budget_exceeded",result
    assert result["rollback"]["performed"] and result["rollback"]["restored"]=="verified_translation"
    assert result["security_fix"]["status"]=="failed" and not result["security_fix"]["fixed"]
    assert (artifact/"migrated/commands.py").read_text()==(PYTHON/"commands.py").read_text()
    assert (artifact/"model_rejected_final").is_dir() and hashes_for(PYTHON)==before
    assert result["response_calls"]==1 and result["model_calls"]==0 and result["chain_intact"]


def test_php_bound_replay_migration_safe_fix_and_needs_review(tmp_path):
    before=source_hashes(PHP); recorded=[]
    fixture=json.loads((PROFILES/"migration.json").read_text())
    def respond(system,user):
        req=json.loads(user); code=req["source"]; updates={}
        if req["task"]=="translate" and req["file"]=="src/legacy.php": code=fixture["files"][req["file"]]["candidates"][0]
        elif req["task"]=="security":
            if req["finding"]["scope"]=="constant_banner": code=NEW_COMMAND
            else: updates={"behavior_impact":"unknown","review_areas":["api"]}
        text=response(req,code,**updates)
        fingerprint=sha256(json.dumps([system,user,True],ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        recorded.append({"prompt_hash":fingerprint,"response":text}); return text
    # Author explicit replay records without executing any PHP or asking a model.
    staging=tmp_path/"record_inputs"; copy_project(PHP,staging)
    mock=LLMClient(tmp_path/"missing.env",mode="mock",limits=limits(6),mock_responder=respond)
    session=ModelSession(mock,"php"); translator=StructuredTranslator(session)
    for module in analyze_php(staging).analysis["modules"]:
        if module["is_test"]: continue
        file=module["file"]; code=translator.translate(file,(staging/file).read_text(encoding="utf-8"))
        (staging/file).write_bytes(code.encode())
    generator=LLMFixGenerator(session=session,rules=("PHP-CMD",),scopes=("constant_banner","unsafe_command"),max_proposals=2)
    for finding in scan_php(staging)["findings"]:
        proposal=generator.generate(finding,(staging/finding["file"]).read_text(encoding="utf-8"))
        if proposal and finding["scope"]=="constant_banner": (staging/finding["file"]).write_bytes(proposal.proposed_code.encode())
    assert len(recorded)==6
    path=tmp_path/"responses.json"; path.write_text(json.dumps({"mode":"explicit_model_response_replay_not_live","responses":recorded}))
    mock.close()
    client=LLMClient(tmp_path/"missing.env",mode="replay",replay_file=path,limits=limits(6))
    job=AIJob(PHP,"php",PROFILES/"cases.json","7.4","8.3",security_fixes=True,security_rules=("PHP-CMD",),security_scopes=("constant_banner","unsafe_command"))
    result,artifact=LanguageRegistry().get("php").migrate_ai(job,client,work_root=tmp_path)
    assert result["status"]=="done",result.get("error")
    assert result["syntax_passed"] and result["tests_passed"] and result["behavior_verified"]
    assert result["golden_case_count"]==22 and all(c["matches"] for c in result["comparisons"])
    assert result["source_tests"]["tests_run"]==result["target_tests"]["tests_run"]==9
    assert result["response_calls"]==6 and result["response_mode"]=="replay" and result["model_calls"]==0
    fixes=result["security_fix"]
    assert fixes["mode"]=="replay" and len(fixes["fixed"])==1 and len(fixes["needs_review"])==1
    assert fixes["attempts"][1]["rolled_back"] and fixes["attempts"][1]["checks"]["passed"]
    assert len(result["security_after"]["findings"])==9 and not result["security_after"]["confirmed_findings"]
    assert source_hashes(PHP)==before and result["originals_unchanged"] and result["chain_intact"]
    assert (artifact/"report.json").exists() and (artifact/"report.html").exists()
    assert client._replay.position==6


def test_p7_preserves_existing_php_fixture_proof():
    receipt,result=verify_demo()
    assert read_receipt(ROOT)==receipt and all(receipt["checks"].values())
    assert result["status"]=="done" and result["golden_case_count"]==22
    assert [a["status"] for a in result["security_fix"]["attempts"]]==["fixed","needs_review","fix_reverted"]
