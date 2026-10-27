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
