import json

import pytest

from backend.core.recorder import load_cases
from backend.sandbox.runner import DockerRunner, SandboxError


@pytest.mark.parametrize("case", [
    {"id": "empty", "module": "a", "steps": []},
    {"id": "mislabelled", "module": "a", "steps": [{"call": "b.function"}]},
    {"id": "ambiguous", "module": "a", "steps": [{"call": "a.function", "attribute": "a.other"}]},
])
def test_vacuous_or_mislabelled_cases_cannot_establish_coverage(tmp_path, case):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": [case]}))
    with pytest.raises(ValueError):
        load_cases(path)


@pytest.mark.parametrize("timeout", [float("inf"), float("nan"), 0, -1, 301])
def test_unsafe_timeout_configuration_is_rejected(timeout):
    with pytest.raises(SandboxError, match="bounded"):
        DockerRunner(timeout=timeout)
