"""Release boundaries with synthetic unit records, never actual Meta results."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend import release


def record():
    return {'mode':'live','model_calls':1,'chain_intact':True,'originals_unchanged':True,'status':'done','ai_migration':True,
        'model':'unit-synthetic','file':'legacy_shop/mathutils.py','isolation':'docker','original_hashes':{},'events':[],
        'source_tests':{'tests_run':3,'outcomes':[{'id':'unit','status':'passed'}]},'source_python':[2,7,18],
        'limits':{'max_calls':2},'usage':[{'tokens_in':1,'tokens_out':1,'cost_usd':0}],
        'iterations':[{'syntax_passed':True,'tests_passed':True,'behavior_verified':True,
            'comparisons':[{'id':str(i),'matches':True} for i in range(31)],
            'target_tests':{'tests_run':3,'outcomes':[{'id':'unit','status':'passed'}]}}]}


def test_projection_preserves_evidence_and_marks_zero_new_calls():
    raw=record();before=deepcopy(raw)
    raw['events']=[{'unit_marker':'not real proof'}];before['events']=deepcopy(raw['events'])
    shown=release.projection('python',raw)
    assert shown['events']==raw['events'] and raw==before
    assert shown['verification']['historical']['new_api_calls']==0 and not shown['simulation']
    assert 'seconds' not in shown['state']['metrics'] and 'lines_migrated' not in shown['state']['metrics']


def test_verbose_historical_isolation_is_preserved_without_breaking_state_enum():
    raw=record();raw['isolation']='docker: network none; read-only mounts'
    shown=release.projection('python',raw)
    assert shown['state']['isolation']=='docker'
    assert shown['verification']['isolation_description']==raw['isolation']


@pytest.mark.parametrize('change',[{'mode':'mock'},{'ai_migration':False},{'chain_intact':False},{'model_calls':0}])
def test_projection_cannot_upgrade_unverified_or_mock_results(change):
    raw=record();raw.update(change)
    with pytest.raises(ValueError): release.projection('python',raw)


def test_projection_rejects_failed_checks_even_if_summary_claims_success():
    raw=record();raw['iterations'][0]['tests_passed']=False
    with pytest.raises(ValueError): release.projection('python',raw)


@pytest.mark.parametrize('path',['../outside','/outside','C:/outside','folder\\outside','a/./b'])
def test_pack_rejects_unsafe_artifact_paths(tmp_path,path):
    with pytest.raises(ValueError): release.checked_path(tmp_path,path)


def test_byte_and_encoded_credential_checks_never_need_network():
    import base64
    value=b'unit-private-only'
    assert not release.secret_free(b'payload '+value,{value})
    assert not release.secret_free(base64.b64encode(value),{base64.b64encode(value)})
    assert release.secret_free(b'ordinary source',set())


def test_pack_manifest_cannot_hide_changed_bytes_or_extra_files(tmp_path):
    (tmp_path/'one').write_text('unit')
    m={'format':release.FORMAT,'new_api_calls':0,'files':{'one':'0'*64}}
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError,match='bytes differ'): release.verify_demo(tmp_path)
    (tmp_path/'extra').write_text('unit')
    with pytest.raises(ValueError,match='inventory'): release.verify_demo(tmp_path)


def test_pack_manifest_size_is_bounded_before_parsing(tmp_path):
    (tmp_path/'manifest.json').write_bytes(b' '*2_000_001)
    with pytest.raises(ValueError,match='size bound'): release.verify_demo(tmp_path)


def test_full_git_audit_finds_retired_key_in_unreachable_commit_without_printing_it(tmp_path):
    import subprocess
    import base64
    from uuid import uuid4
    from backend import release
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'.gitignore').write_text('backend/.tmp/\n')
    private=tmp_path/'backend/.tmp/retired-keys.env';private.parent.mkdir(parents=True)
    key='unit-disclosed-'+uuid4().hex
    private.write_text('MODEL_API_KEY_RETIRED_1='+key+'\n')
    tree=release.git(tmp_path,'mktree',input=b'').strip()
    content=b'tree '+tree+b'\nauthor Unit <unit@example.invalid> 1 +0000\ncommitter Unit <unit@example.invalid> 1 +0000\n\n'+key.encode()+b'\n'
    release.git(tmp_path,'hash-object','-w','-t','commit','--stdin',input=content)
    release.git(tmp_path,'hash-object','-w','--stdin',input=base64.b64encode(key.encode()))
    report=release.audit(tmp_path,retired_keys_file=private)
    assert report['historical_credential_hits']==2 and report['includes_unreachable_objects']
    assert not report['technical_checks_passed'] and key not in json.dumps(report)


def test_retired_key_file_cannot_be_a_tracked_or_external_file(tmp_path):
    import subprocess
    from backend import release
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    outside=tmp_path/'retired.env';outside.write_text('MODEL_API_KEY_RETIRED_1=unit-only\n')
    with pytest.raises(ValueError): release.credential_forms(tmp_path,outside)


def test_missing_or_empty_retired_key_file_cannot_claim_coverage(tmp_path):
    import subprocess
    from backend import release
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'.gitignore').write_text('backend/.tmp/\n')
    private=tmp_path/'backend/.tmp/retired-keys.env';private.parent.mkdir(parents=True)
    with pytest.raises(ValueError): release.credential_forms(tmp_path,private)
    private.write_text('MODEL_API_KEY_RETIRED_1=\n')
    with pytest.raises(ValueError): release.credential_forms(tmp_path,private)
