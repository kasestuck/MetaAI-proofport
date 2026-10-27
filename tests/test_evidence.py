from backend.core.evidence import Evidence


def test_tampering_and_caller_mutation():
    evidence = Evidence()
    evidence.append("run_started", "SIMULATED run")
    evidence.append("hashes_recorded", "Real hashes")
    assert evidence.verify()
    public = evidence.since(0)
    public[0]["detail"] = "external modification"
    assert evidence.verify()
    evidence._entries[0]["detail"] = "tampered"
    assert not evidence.verify()


def test_persisted_chain_detects_disk_tampering(tmp_path):
    evidence = Evidence()
    evidence.append("run_started", "Real Docker run")
    log = tmp_path / "evidence.log"
    evidence.bind(log)
    evidence.append("test_result", "A real test passed")
    assert evidence.verify()
    assert len(log.read_text().splitlines()) == 2
    log.write_text(log.read_text().replace("passed", "failed"))
    assert not evidence.verify()
