"""Synthetic receipt validation unit tests; these records are never Docker proof."""

from hashlib import sha256
import json

import pytest

from backend.languages.runtimes import PHP_RUNTIMES
from backend.php.protocol import digest
from backend.php.receipts import CHECKS, read_receipt, supported


@pytest.fixture
def synthetic(tmp_path,monkeypatch):
    monkeypatch.setattr("backend.php.receipts.revision",lambda root:"unit-revision")
    monkeypatch.setattr("backend.php.runtime.source_hashes",lambda path:{"unit":"source-hash"})
    artifact=tmp_path/"backend/.work/php-run-unit"; artifact.mkdir(parents=True)
    files={n:b'unit double, not execution evidence' for n in ("report.json","report.html","golden.json","evidence.jsonl")}
    for name,value in files.items(): (artifact/name).write_bytes(value)
    data={"checks":{key:True for key in CHECKS},"revision":"unit-revision","source_hashes":{"unit":"source-hash"},
          "artifact_id":artifact.name,"golden_cases":1,"target_tests":1,"images":{"7.4":"sha256:"+"a"*64,"8.3":"sha256:"+"b"*64},
          "artifacts":{name:sha256(value).hexdigest() for name,value in files.items()}}
    def save():
        data["receipt_hash"]=digest({k:v for k,v in data.items() if k!="receipt_hash"})
        (tmp_path/"backend/.work/php_registry.json").write_text(json.dumps(data))
    save()
    return tmp_path,data,artifact,save


def test_absence_does_not_become_support(tmp_path):
    assert read_receipt(tmp_path) is None and not supported(tmp_path,[])["migration"]


def test_valid_current_receipt_still_requires_exact_local_images(synthetic):
    root,data,artifact,save=synthetic
    states=[{"version":r.version,"available":True,"image_id":data["images"][r.version]} for r in PHP_RUNTIMES]
    assert read_receipt(root) and supported(root,states)["migration"]
    states[0]["image_id"]="sha256:"+"c"*64
    ready=supported(root,states)
    assert ready["receipt_valid"] and ready["audit"] and not ready["migration"] and not ready["compatibility"]


@pytest.mark.parametrize("change",["source","revision","check","path","artifact","digest","zero_cases"])
def test_stale_or_tampered_receipt_fails_closed(synthetic,change):
    root,data,artifact,save=synthetic
    if change=="source": data["source_hashes"]={}
    if change=="revision": data["revision"]="outdated"
    if change=="check": data["checks"]["behavior"]=False
    if change=="path": data["artifact_id"]="php-run-../escape"
    if change=="artifact": (artifact/"golden.json").write_text("edited")
    if change=="zero_cases": data["golden_cases"]=0
    save()
    if change=="digest": (root/"backend/.work/php_registry.json").write_text('{"receipt_hash":"wrong"}')
    assert read_receipt(root) is None and not supported(root,[])["audit"]
