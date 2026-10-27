from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.api.main import create_app


@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch):
    for key in ("MODEL_API_KEY", "MODEL_NAME", "MODEL_BASE_URL", "PRICE_IN_PER_MTOK", "PRICE_OUT_PER_MTOK", "PROOFPORT_CASES_FILE", "PROOFPORT_FIXTURE_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("PROOFPORT_PIPELINE", "simulation")


@pytest.fixture
def project(tmp_path: Path):
    source = tmp_path / "samples" / "legacy_shop"
    source.mkdir(parents=True)
    # Original fixtures written for this project; include actual Python 2 syntax.
    (source / "mathutils.py").write_text(
        'def mean(values):\n    return sum(values) / len(values)\n\nprint "legacy"\n', encoding="utf-8",
    )
    (source / "config.py").write_text(
        'def parse_value(value):\n    return eval(value)\n', encoding="utf-8",
    )
    (source / "storage.py").write_text(
        'import hashlib\nimport pickle\n\ndef digest(value):\n    return hashlib.md5(value).hexdigest()\n'
        '\ndef load(stream):\n    return pickle.load(stream)\n', encoding="utf-8",
    )
    (source / "inventory.csv").write_bytes(b"name,quantity\r\nBook,5\r\n")
    return tmp_path


@pytest.fixture
def client(project, monkeypatch):
    monkeypatch.setattr("backend.api.main.docker_available", lambda: False)
    with TestClient(create_app(project, step_seconds=0.05)) as client:
        yield client


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: real Docker integration; enable with PROOFPORT_DOCKER_TESTS=1")


def pytest_collection_modifyitems(items):
    import os
    if os.environ.get("PROOFPORT_DOCKER_TESTS") != "1":
        skip = pytest.mark.skip(reason="Set PROOFPORT_DOCKER_TESTS=1 for real Docker integration")
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(skip)
