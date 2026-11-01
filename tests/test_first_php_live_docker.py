"""One genuine PHP baseline, zero model requests; no translated fixture."""

import json
from uuid import uuid4
import pytest

from backend.ai import artifacts, first_php_live as php
from backend.php.protocol import compare, load_cases
from backend.php.runtime import source_hashes
from backend.sandbox.runner import DockerRunner


@pytest.mark.docker
def test_php_baseline(tmp_path,monkeypatch):
    runner=DockerRunner()
    if not runner.available(): pytest.skip('Docker unavailable; no host execution')
    monkeypatch.setattr('backend.llm.client.OpenAI',lambda *a,**k:pytest.fail('No Meta client in baseline preparation'))
    monkeypatch.setattr(php,'ROOT',tmp_path)
    monkeypatch.setenv('LLM_MODE','live')
    env=tmp_path/'unit.env'
    env.write_text('MODEL_API_KEY=unit-only-'+uuid4().hex+'\nLLM_MODE=live\nMODEL_NAME=muse-spark-1.3\nMODEL_BASE_URL=https://api.meta.ai/v1\nPRICE_IN_PER_MTOK=1.25\nPRICE_OUT_PER_MTOK=4.25\n')
    before=source_hashes(php.SOURCE)
    report,workspace=php.prepare(env,runner=runner)
    assert report['status']=='awaiting_paid_approval' and report['model_calls']==0
    assert report['source_php']=='7.4.33' and report['source_syntax']['passed']
    assert report['source_tests']['tests_run']==9 and report['source_tests']['passed']
    assert report['golden_case_count']==22 and report['module_golden_cases']==5
    assert report['target_runtime']['php']=='8.3.36'
    failed=[f['file'] for f in report['target_original_syntax']['files'] if not f['passed']]
    assert failed==['src/legacy.php']
    profile=load_cases(workspace/'cases.json')
    golden=json.loads((workspace/'golden.json').read_text(encoding='utf-8'))
    assert len(golden)==22 and all(c['matches'] for c in compare(profile,golden,golden))
    assert not report['ai_migration'] and report['syntax_passed'] is report['tests_passed'] is report['behavior_verified'] is None
    assert artifacts.verify(workspace,php.unchanged,stem='baseline-report')
    assert php.validate_prepared(workspace,runner)['limits']==php.public_limits(php.LIMITS)
    assert source_hashes(php.SOURCE)==before and not (workspace/'execution_started.json').exists()
