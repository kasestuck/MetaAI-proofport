"""Real eval baseline and literal-only regression; no model or successful fix."""

import json
from uuid import uuid4
import pytest

from backend.ai import artifacts,first_security_live as sec
from backend.core.evidence import Evidence
from backend.security.engine import SecurityFixEngine,project_hashes
from backend.security.models import FixProposal
from backend.core.projects import copy_project
from backend.sandbox.runner import DockerRunner


@pytest.mark.docker
def test_eval_baseline(tmp_path,monkeypatch):
    runner=DockerRunner()
    if not runner.available(): pytest.skip('Docker unavailable; no host execution')
    monkeypatch.setattr('backend.llm.client.OpenAI',lambda *a,**k:pytest.fail('No Meta SDK during baseline/regression'))
    monkeypatch.setattr(sec,'ROOT',tmp_path)
    monkeypatch.setenv('LLM_MODE','live')
    env=tmp_path/'unit.env'
    env.write_text('MODEL_API_KEY=unit-only-'+uuid4().hex+'\nMODEL_NAME=muse-spark-1.3\nMODEL_BASE_URL=https://api.meta.ai/v1\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    before=project_hashes(sec.SOURCE)
    report,workspace=sec.prepare(env,runner=runner)
    assert report['source_python']==[2,7,18] and report['golden_cases']==9
    assert report['source_tests']['tests_run']==1 and report['source_tests']['outcomes'][0]['status']=='passed'
    assert report['finding']['scanner_test']=='B307' and report['finding']['cwe']['id']==78
    assert report['cross_runtime_matches']==8 and report['cross_runtime_total']==9
    working=workspace/'diagnostic';copy_project(workspace/'original',working)
    evidence=Evidence(); evidence.bind(workspace/'diagnostic.log')
    engine=SecurityFixEngine(runner=runner,working=working,original=sec.SOURCE,original_hashes=before,
        artifacts=workspace/'attempts',cases=sec.load_cases(workspace/'cases.json'),
        golden=json.loads((workspace/'golden.json').read_text())['cases'],existing_tests=report['source_tests'],
        evidence=evidence,runtime_version='2.7',extra_syntax_versions=('3.12',))
    engine.artifacts.mkdir()
    baseline_checks=engine._verify(working)
    assert all(baseline_checks[stage]['passed'] for stage in ('syntax','golden','existing_tests'))
    source=(working/sec.FILE).read_text(encoding='utf-8')
    # Authored DIAGNOSTIC only, never represented as a model response or fix.
    lines=source.splitlines(keepends=True);lines.insert(1,'import ast\n')
    changed=''.join(lines).replace('return eval(raw)','return ast.literal_eval(raw)')
    proposal=FixProposal(finding_id=report['finding']['id'],explanation='Authored regression diagnostic, not AI',
        proposed_code=changed,behavior_impact='changes',confidence=1,mode='fixture')
    attempt=engine._attempt(report['finding'],proposal,json.loads((workspace/'bandit-before.json').read_text()))
    assert attempt['status']=='needs_review' and attempt['rolled_back'] and not attempt['applied']
    assert attempt['checks']['syntax']['passed'] and attempt['checks']['existing_tests']['passed']
    assert attempt['checks']['golden']['matched']==8 and attempt['checks']['golden']['total']==9
    assert [c['id'] for c in attempt['checks']['golden']['comparisons'] if not c['matches']]==['config.parse_6']
    assert attempt['rescan']['passed'] and attempt['target_warning_removed']
    assert project_hashes(working)==project_hashes(workspace/'original') and project_hashes(sec.SOURCE)==before
    assert evidence.verify() and artifacts.verify(workspace,sec.unchanged,stem='baseline-report')
    (workspace/'diagnostic-summary.json').write_text(json.dumps({'mode':'authored_diagnostic_not_model','model_calls':0,
        'baseline':report['source_tests'],'attempt':attempt,'originals_unchanged':True,'chain_intact':True},indent=2))
