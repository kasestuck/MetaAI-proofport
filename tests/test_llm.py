from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from backend.llm.client import LLMClient, ModelUnavailable
from backend.llm.budget import LLMLimits


def test_mock_is_offline_deterministic_and_free(tmp_path, monkeypatch):
    def no_network(**kwargs):
        pytest.fail("Mock mode must not construct a network client")
    monkeypatch.setattr("backend.llm.client.OpenAI", no_network)
    with LLMClient(tmp_path / "missing.env") as client:
        first = client.complete("Migrate", "print 'hello'")
        assert client.complete("Migrate", "print 'hello'") == first
        assert json.loads(client.complete("Return JSON", "example", json_mode=True))["mode"] == "mock"
        assert len(client.calls) == 3
        assert client.calls[0].prompt_hash == client.calls[1].prompt_hash
        assert len(client.calls[0].prompt_hash) == 64
        assert client.tokens_in == client.tokens_out == client.cost_usd == 0
        assert all(call.seconds >= 0 and call.mode == "mock" for call in client.calls)


def test_default_is_mock_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODE")
    client = LLMClient(tmp_path / "absent.env")
    assert client.mode == "mock"
    assert "Mock response" in client.complete("system", "user")


def test_live_requires_key_and_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODE", "live")
    with pytest.raises(ModelUnavailable, match="MODEL_API_KEY and MODEL_NAME"):
        LLMClient(tmp_path / "absent.env")


def test_dotenv_sdk_settings_usage_and_env_override(tmp_path, monkeypatch):
    env = tmp_path / "settings.env"
    env.write_text("LLM_MODE=live\nMODEL_API_KEY=test-only-not-a-secret\nMODEL_NAME=from-file\nPRICE_IN_PER_MTOK=2\nPRICE_OUT_PER_MTOK=8\n")
    monkeypatch.delenv("LLM_MODE")
    monkeypatch.setenv("MODEL_NAME", "from-environment")
    captured = {}

    def complete(**kwargs):
        captured["request"] = kwargs
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
        )
        return SimpleNamespace(parse=lambda: response, http_response=SimpleNamespace(json=lambda: {"usage": {
            "prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
            "choices":[{"finish_reason":"stop","message":{"content":'{"ok":true}'}}]}))

    def fake_sdk(**kwargs):
        captured["settings"] = kwargs
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=complete))),
            close=lambda: captured.update(closed=True),
        )

    monkeypatch.setattr("backend.llm.client.OpenAI", fake_sdk)
    with LLMClient(env, allow_live=True, limits=LLMLimits(max_calls=2, max_output_tokens=512, max_total_tokens=5120, max_cost_usd="0.03")) as client:
        assert client.complete("system", "user", json_mode=True) == '{"ok":true}'
        client.complete("system", "second")
        assert client.calls[0].cost_usd == pytest.approx(0.006)
        assert client.cost_usd == pytest.approx(0.012)
        assert (client.tokens_in, client.tokens_out) == (2000, 1000)
        assert "test-only-not-a-secret" not in json.dumps([asdict(c) for c in client.calls])
    assert captured["settings"]["base_url"] == "https://api.meta.ai/v1"
    assert captured["settings"]["max_retries"] == 0
    assert captured["settings"]["timeout"] == 15
    assert captured["settings"]["http_client"].follow_redirects is False
    assert captured["settings"]["http_client"]._trust_env is False
    assert captured["request"]["model"] == "from-environment"
    assert captured["closed"] is True


@pytest.mark.parametrize("price", ["-1", "NaN", "Infinity", "oops"])
def test_invalid_prices(tmp_path, monkeypatch, price):
    monkeypatch.setenv("PRICE_IN_PER_MTOK", price)
    with pytest.raises(ModelUnavailable, match="Token prices"):
        LLMClient(tmp_path / "absent.env")


def test_live_timeout_is_safe(tmp_path, monkeypatch):
    from openai import APITimeoutError
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("MODEL_API_KEY", "test-only-not-a-secret")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("PRICE_IN_PER_MTOK", "1.25")
    monkeypatch.setenv("PRICE_OUT_PER_MTOK", "4.25")

    def timeout(**kwargs):
        raise APITimeoutError(request=SimpleNamespace())

    monkeypatch.setattr("backend.llm.client.OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=timeout))), close=lambda: None,
    ))
    with LLMClient(tmp_path / "absent.env", allow_live=True, limits=LLMLimits()) as client:
        with pytest.raises(ModelUnavailable, match="no automatic retry") as exc:
            client.complete("system", "user")
        assert "test-only-not-a-secret" not in str(exc.value)
        assert not client.calls
