"""Reproduce real P8 failures with the recorded BAD candidate, never a fix."""

import json
from pathlib import Path
import shutil

import pytest

from backend.ai.first_live import FILE, SOURCE, assert_originals, project_hashes, scoped_tests, suite_passed, verify_candidate
from backend.ai.feedback import repair_feedback
from backend.core.evidence import Evidence
from backend.core.recorder import invoke, load_cases
from backend.sandbox.runner import DockerRunner


@pytest.mark.docker
def test_real_recorded_candidate_reproduces_exact_five_failures(tmp_path):
    runner=DockerRunner()
    if not runner.available(): pytest.skip('Docker unavailable; no host execution permitted')
    for image in ('python:2.7','python:3.12-slim'): runner.image_id(image)
    before=project_hashes()
    original=tmp_path/'original'
    (original/'legacy_shop').mkdir(parents=True)
    (original/'tests').mkdir()
    for file in (FILE,'legacy_shop/__init__.py','tests/__init__.py'):
        shutil.copyfile(SOURCE/file,original/file)
    projected,_=scoped_tests((SOURCE/'tests/test_legacy_shop.py').read_text(encoding='utf-8'))
    (original/'tests/test_legacy_shop.py').write_text(projected,encoding='utf-8')
    candidate=tmp_path/'candidate'; shutil.copytree(original,candidate)
    shutil.copyfile(Path(__file__).parent/'fixtures/p8_failed_candidate/mathutils.py',candidate/FILE)
    cases=[c for c in load_cases(Path(__file__).parent/'fixtures/legacy_shop/cases.json') if c['module']=='legacy_shop.mathutils']
    evidence=Evidence(); evidence.bind(tmp_path/'evidence.log')
    golden=invoke(runner,'python:2.7',original,'cases',cases,evidence)
    baseline=invoke(runner,'python:2.7',original,'tests',evidence=evidence)
    assert baseline['tests_run']==3 and suite_passed(baseline)
    checks=verify_candidate(runner,candidate,cases,golden,baseline,evidence)
    assert checks['syntax_passed'] and checks['tests_passed'] and not checks['behavior_verified']
    assert sum(c['matches'] for c in checks['comparisons'])==26
    failures={c['id'] for c in checks['comparisons'] if not c['matches']}
    assert failures=={'mathutils.mean_float','mathutils.median_float','mathutils.round_1','mathutils.round_3','mathutils.tiers_2'}
    feedback=repair_feedback(checks,cases)
    assert {c['id'] for c in feedback['failing_cases']}==failures
    by_id={c['id']:c for c in feedback['failing_cases']}
    for case_id in ('mathutils.mean_float','mathutils.median_float'):
        assert by_id[case_id]['expected'][0]['value']=={'t':'float','v':'1.75'}
        assert by_id[case_id]['actual'][0]['value']=={'t':'float','v':'1.0'}
    for case_id,expected,actual in (('mathutils.round_1',-3,-2),('mathutils.round_3',-1,0)):
        assert by_id[case_id]['expected'][0]['value']=={'t':'int','v':expected}
        assert by_id[case_id]['actual'][0]['value']=={'t':'int','v':actual}
    tiers=by_id['mathutils.tiers_2']
    assert [p[0]['v'] for p in tiers['expected'][0]['value']['v']]==['1.0','2.0','5.0']
    assert [p[0]['v'] for p in tiers['actual'][0]['value']['v']]==['0.0','5.0']
    assert_originals(before)
    assert evidence.verify()
    (tmp_path/'reproduction.json').write_text(json.dumps({'mode':'offline_reproduction_of_real_failed_candidate',
        'model_requests':0,'source_python':golden['python'],'target_python':checks['target_python'],
        'golden_matches':26,'golden_total':31,'source_tests':baseline,'checks':checks,
        'feedback':feedback,'originals_unchanged':True,'chain_intact':True,'images':runner._images},indent=2),encoding='utf-8')
