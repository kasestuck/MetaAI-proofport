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
