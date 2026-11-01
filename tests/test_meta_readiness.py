"""Real pinned SDK parsing against in-memory HTTP responses. No network allowed."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import logging
import socket
import subprocess
import traceback
from uuid import uuid4

import httpx2
import pytest

from backend.core.translator import LiveTranslator, parse_code
from backend.llm.budget import LLMLimits
from backend.llm.client import LLMClient, ModelUnavailable
from backend.llm import smoke
from backend.security.providers import LLMFixGenerator, OfflineOnlyError


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No socket connection or paid API request is permitted in P5.1 tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def settings(monkeypatch, tmp_path):
    key = "unit-only-" + uuid4().hex
    for name, value in {"LLM_MODE": "live", "MODEL_API_KEY": key, "MODEL_NAME": "unit-model",
                        "PRICE_IN_PER_MTOK": "1.25", "PRICE_OUT_PER_MTOK": "4.25"}.items():
        monkeypatch.setenv(name, value)
    return tmp_path / "missing.env", key


def completion(text='{"ok":true}', **changes):
    data = {"id": "unit-completion", "object": "chat.completion", "created": 1, "model": "unit-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}}
    data.update(changes)
    return data


def client_for(settings, handler, limits=None):
    calls = []
    def transport(request):
        calls.append(request)
        return handler(request)
    http = httpx2.Client(transport=httpx2.MockTransport(transport), trust_env=False, follow_redirects=False)
    client = LLMClient(settings[0], allow_live=True, limits=limits or LLMLimits(), http_client=http)
    return client, calls


def test_success_uses_actual_sdk_and_bounded_meta_request(settings):
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion()))
    with client:
        assert client.complete("Return JSON", "Synthetic test", json_mode=True) == '{"ok":true}'
        assert len(client.calls) == len(client.attempts) == 1
        assert (client.tokens_in, client.tokens_out) == (30, 10)
        assert client.cost_usd == pytest.approx(0.00008)
        assert client.budget_snapshot()["usage_complete"] is True
    assert len(calls) == 1 and str(calls[0].url) == "https://api.meta.ai/v1/chat/completions"
    assert calls[0].headers["authorization"] == "Bearer " + settings[1]
    payload = json.loads(calls[0].content)
    assert payload["max_completion_tokens"] == 256
    assert payload["n"] == 1 and payload["stream"] is False
    assert payload["reasoning_effort"] == "minimal"
    assert payload["response_format"] == {"type": "json_object"}
    assert settings[1] not in calls[0].content.decode()


@pytest.mark.parametrize("status,code", [(401, "model_authentication_failed"), (403, "model_permission_denied"),
                                        (429, "model_rate_limited"), (400, "model_bad_request"),
                                        (404, "model_not_found"), (500, "model_service_error")])
def test_http_failures_are_safe_never_retried_and_retain_unknown_reservation(settings, caplog, status, code):
    client, calls = client_for(settings, lambda request: httpx2.Response(status,
        json={"error": {"message": "provider echoed " + settings[1], "type": "test_error"}}, headers={"Retry-After": "1"}))
    with client:
        with pytest.raises(ModelUnavailable) as caught:
            client.complete("system", "synthetic")
        assert caught.value.code == code
        rendered = "".join(traceback.format_exception(caught.value))
        assert settings[1] not in rendered + caplog.text + json.dumps(client.budget_snapshot())
        assert client.attempts[0].outcome == code and not client.attempts[0].usage_known
        assert client.budget_snapshot()["reserved_cost_usd"] > 0
        assert client.budget_snapshot()["usage_complete"] is False
        with pytest.raises(ModelUnavailable, match="closed/stopped"):
            client.complete("system", "second")
        assert len(calls) == 1


@pytest.mark.parametrize("exception,code", [(httpx2.ReadTimeout, "model_timeout"), (httpx2.ConnectError, "model_connection_error")])
def test_timeout_connection_fail_closed(settings, exception, code):
    def fail(request):
        raise exception(settings[1], request=request)
    client, calls = client_for(settings, fail)
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == code and settings[1] not in str(caught.value)
    assert len(calls) == 1
    assert not client.calls and not client.budget_snapshot()["usage_complete"]


def test_non_json_http_success_is_rejected_without_body_leak(settings):
    client, calls = client_for(settings, lambda request: httpx2.Response(200, text="not JSON " + settings[1], headers={"Content-Type": "application/json"}))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "model_invalid_response"
    assert settings[1] not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("text", ["not JSON", "{broken", "[]", "null", '{"bad":NaN}', '{"same":1,"same":2}'])
def test_invalid_generated_json_is_charged_but_never_returned(settings, text):
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion(text)))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("Return JSON", "user", json_mode=True)
    assert caught.value.code == "model_invalid_response"
    assert client.tokens_out == 10 and client.cost_usd > 0
    assert client.attempts[0].usage_known is True and len(calls) == 1


@pytest.mark.parametrize("text", [None, "", "  "])
def test_empty_content_not_accepted(settings, text):
    client, _ = client_for(settings, lambda request: httpx2.Response(200, json=completion(text)))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "model_empty_response"
    assert client.tokens_out == 10


@pytest.mark.parametrize("finish", ["length", "content_filter", "tool_calls"])
def test_truncated_refused_or_tool_response_is_not_candidate_code(settings, finish):
    data = completion(); data["choices"][0]["finish_reason"] = finish
    client, _ = client_for(settings, lambda request: httpx2.Response(200, json=data))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "model_incomplete_response"


@pytest.mark.parametrize("finish,text,at_limit,code,valid_json", [
    ("length", '{"partial":', True, "model_incomplete_response", False),
    ("length", '{"complete":true}', True, "model_incomplete_response", True),
    ("length", '{"complete":true}', False, "model_incomplete_response", True),
    ("content_filter", '{"complete":true}', False, "model_incomplete_response", True),
    ("stop", '{"partial":', False, "model_invalid_response", False),
    ("stop", '{"complete":true}', True, None, True),
])
def test_wire_diagnostics_distinguish_truncation_json_and_exact_limit(settings,finish,text,at_limit,code,valid_json):
    usage={"prompt_tokens":30,"completion_tokens":256 if at_limit else 10,"total_tokens":286 if at_limit else 40}
    data=completion(text,usage=usage)
    data["choices"][0]["finish_reason"]=finish
    client,calls=client_for(settings,lambda request:httpx2.Response(200,json=data))
    with client:
        if code:
            with pytest.raises(ModelUnavailable) as caught: client.complete("Return JSON","unit",json_mode=True)
            assert caught.value.code==code
            with pytest.raises(ModelUnavailable): client.complete("Return JSON","second",json_mode=True)
        else:
            assert client.complete("Return JSON","unit",json_mode=True)==text
    diagnostic=asdict(client.attempts[0])
    assert diagnostic["finish_reason"]==finish and diagnostic["finish_reason_matches_sdk"] is True
    assert diagnostic["json_object_valid"] is valid_json and diagnostic["output_limit_reached"] is at_limit
    assert diagnostic["completion_tokens"]==usage["completion_tokens"] and diagnostic["output_token_limit"]==256
    from hashlib import sha256
    assert diagnostic["content_sha256"]==sha256(text.encode()).hexdigest()
    assert diagnostic["content_bytes"]==len(text.encode())
    assert settings[1] not in json.dumps(diagnostic) and len(calls)==1
    assert client.tokens_out==usage["completion_tokens"]


def test_untrusted_finish_reason_cannot_leak_provider_text(settings):
    data=completion()
    data["choices"][0]["finish_reason"]=settings[1]
    client,calls=client_for(settings,lambda request:httpx2.Response(200,json=data))
    with client,pytest.raises(ModelUnavailable): client.complete("system","user",json_mode=True)
    assert client.attempts[0].finish_reason=="unrecognized"
    assert settings[1] not in json.dumps(asdict(client.attempts[0])) and len(calls)==1


@pytest.mark.parametrize("reasoning,expected", [(6,6),(None,None),(True,None),(11,None),("private-provider-text",None)])
def test_reasoning_usage_diagnostics_are_optional_bounded_integers(settings,reasoning,expected):
    data=completion()
    data['usage']['completion_tokens_details']={'reasoning_tokens':reasoning}
    client,calls=client_for(settings,lambda request:httpx2.Response(200,json=data))
    with client: client.complete('Return JSON','unit',json_mode=True)
    assert client.attempts[0].reasoning_tokens==expected and len(calls)==1


@pytest.mark.parametrize('mismatch',['finish','content'])
def test_deliberate_sdk_wire_mismatch_is_rejected(settings,mismatch):
    from types import SimpleNamespace
    wire=completion()
    parsed=SimpleNamespace(choices=[SimpleNamespace(
        finish_reason='length' if mismatch=='finish' else 'stop',
        message=SimpleNamespace(content='different' if mismatch=='content' else '{"ok":true}'))])
    raw=SimpleNamespace(parse=lambda:parsed,http_response=SimpleNamespace(json=lambda:wire))
    client,calls=client_for(settings,lambda request:pytest.fail('No real HTTP in the deliberate SDK double'))
    client._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        with_raw_response=SimpleNamespace(create=lambda **kwargs:raw))),close=lambda:None)
    with client,pytest.raises(ModelUnavailable) as caught: client.complete('Return JSON','unit',json_mode=True)
    assert caught.value.code=='model_invalid_response' and len(client.attempts)==1 and not calls
    assert client.attempts[0].finish_reason_matches_sdk is (mismatch!='finish')


@pytest.mark.parametrize("usage", [None, {"prompt_tokens": -1, "completion_tokens": 10, "total_tokens": 9},
                                   {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 41},
                                   {"prompt_tokens": True, "completion_tokens": 10, "total_tokens": 11},
                                   {"prompt_tokens": "30", "completion_tokens": 10, "total_tokens": 40}])
def test_invalid_usage_blocks_further_requests(settings, usage):
    client, _ = client_for(settings, lambda request: httpx2.Response(200, json=completion(usage=usage)))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code in {"model_usage_invalid", "model_invalid_response"}
    assert not client.budget_snapshot()["usage_complete"]


@pytest.mark.parametrize("kind", ["calls", "tokens", "cost"])
def test_pre_request_budget_enforced_and_attempts_never_refunded(settings, kind):
    limits = {"calls": LLMLimits(), "tokens": LLMLimits(max_calls=2),
              "cost": LLMLimits(max_calls=2, max_total_tokens=4608, max_cost_usd="0.005")}[kind]
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion()), limits)
    with client:
        client.complete("system", "user")
        with pytest.raises(ModelUnavailable) as caught:
            client.complete("system", "second")
    assert caught.value.code == "budget_exceeded" and len(calls) == 1


def test_zero_requests_when_cost_reservation_already_exceeds_cap(settings):
    client, calls = client_for(settings, lambda request: pytest.fail("Budget must reject before HTTP"), LLMLimits(max_cost_usd="0.00001"))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "budget_exceeded" and not calls and not client.attempts


def test_large_input_blocked_before_send(settings):
    client, calls = client_for(settings, lambda request: pytest.fail("Oversized input must not be sent"))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "x" * 3000)
    assert caught.value.code == "input_budget_exceeded" and not calls


def test_provider_overrun_recorded_and_session_stopped(settings):
    usage = {"prompt_tokens": 30, "completion_tokens": 257, "total_tokens": 287}
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion(usage=usage)))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "provider_budget_exceeded" and len(calls) == 1
    assert client.tokens_out == 257 and client.budget_snapshot()["stopped"]


def test_parallel_calls_cannot_overspend_one_reservation(settings):
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion()))
    def send(_):
        try:
            return client.complete("system", "user")
        except ModelUnavailable as error:
            return error.code
    with client, ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(send, range(2)))
    assert sorted(outcomes) == sorted(['{"ok":true}', "budget_exceeded"]) and len(calls) == 1


def test_live_mode_and_keys_alone_do_not_authorize_requests(settings):
    with pytest.raises(ModelUnavailable) as caught:
        LLMClient(settings[0])
    assert caught.value.code == "live_not_authorized"


def test_missing_key_fails_before_sdk(settings, monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY")
    monkeypatch.setattr("backend.llm.client.OpenAI", lambda **kw: pytest.fail("No SDK without key"))
    with pytest.raises(ModelUnavailable, match="MODEL_API_KEY and MODEL_NAME"):
        LLMClient(settings[0], allow_live=True, limits=LLMLimits())


@pytest.mark.parametrize("url", ["http://api.meta.ai/v1", "https://evil.invalid/v1", "https://api.meta.ai.evil.invalid/v1",
                                "https://api.meta.ai/v1?key=private", "https://user:pass@api.meta.ai/v1", "https://api.meta.ai:8443/v1"])
def test_credentials_cannot_be_redirected_by_configuration(settings, monkeypatch, url):
    monkeypatch.setenv("MODEL_BASE_URL", url)
    with pytest.raises(ModelUnavailable) as caught:
        LLMClient(settings[0], allow_live=True, limits=LLMLimits())
    assert caught.value.code == "unsafe_model_url"


def test_http_redirect_never_followed(settings):
    client, calls = client_for(settings, lambda request: httpx2.Response(302, headers={"Location": "https://evil.invalid/collect"}))
    with client, pytest.raises(ModelUnavailable):
        client.complete("system", "user")
    assert len(calls) == 1 and calls[0].url.host == "api.meta.ai"


@pytest.mark.parametrize("logger", ["openai._base_client", "httpx2", "httpcore2.connection"])
def test_debug_logging_blocks_live_before_sensitive_headers(settings, caplog, logger):
    client, calls = client_for(settings, lambda request: pytest.fail("Debug logging must block live"))
    with caplog.at_level(logging.DEBUG, logger=logger), client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "unsafe_model_logging" and not calls
    assert settings[1] not in caplog.text


def test_key_echo_never_returned_or_recorded(settings, caplog):
    client, _ = client_for(settings, lambda request: httpx2.Response(200, json=completion(settings[1])))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", "user")
    assert caught.value.code == "model_sensitive_response"
    assert settings[1] not in caplog.text + str(caught.value) + json.dumps([asdict(c) for c in client.calls])


def test_key_in_prompt_is_blocked(settings):
    client, calls = client_for(settings, lambda request: pytest.fail("Credential must not be sent as prompt"))
    with client, pytest.raises(ModelUnavailable) as caught:
        client.complete("system", settings[1])
    assert caught.value.code == "credential_in_prompt" and not calls


def test_translator_wire_compatibility_without_executing_generated_code(settings, monkeypatch):
    code = "```python\nraise RuntimeError('never execute on host')\n```"
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion(code)))
    monkeypatch.setattr("backend.core.translator.LLMClient", lambda path: client)
    translator = LiveTranslator(settings[0].parent)
    try:
        assert translator.translate("module.py", "print 'legacy'") == "raise RuntimeError('never execute on host')\n"
        assert "response_format" not in json.loads(calls[0].content)
    finally:
        translator.close()
    with pytest.raises(ValueError):
        parse_code("not fenced code")


def test_security_schema_compatibility_does_not_enable_generation(settings):
    proposal = {"finding_id": "finding-one", "explanation": "Unit proposal; not verified", "proposed_code": "pass\n",
                "behavior_impact": "unknown", "confidence": 0.5, "mode": "fixture"}
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion(json.dumps(proposal))))
    with client:
        text = client.complete("Return proposal JSON", "synthetic", json_mode=True)
        parsed = LLMFixGenerator.parse_response(text, "finding-one")
        assert parsed.mode == "live" and parsed.behavior_impact == "unknown"
        with pytest.raises(ValueError):
            LLMFixGenerator.parse_response(text, "another-finding")
        with pytest.raises(OfflineOnlyError):
            LLMFixGenerator(client).generate({"id": "finding-one"}, "pass")
    assert len(calls) == 1


def test_smoke_default_is_offline_even_when_key_present(settings, monkeypatch, capsys):
    monkeypatch.setattr(smoke, "LLMClient", lambda *a, **kw: pytest.fail("Dry run must not construct client"))
    assert smoke.main(["--env-file", str(settings[0])]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["executed"] is False and result["provider_validated"] is False
    assert settings[1] not in json.dumps(result)


@pytest.mark.parametrize("args", [["--execute"], ["--execute", "--max-cost-usd", "0.01"], ["--acknowledge-paid-api"]])
def test_smoke_requires_explicit_paid_acknowledgment(settings, monkeypatch, capsys, args):
    monkeypatch.setattr(smoke, "LLMClient", lambda *a, **kw: pytest.fail("Approval absent"))
    assert smoke.main(["--env-file", str(settings[0]), *args]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "approval_required"


def test_smoke_single_request_uses_only_in_memory_http(settings, monkeypatch, capsys):
    client, calls = client_for(settings, lambda request: httpx2.Response(200, json=completion('{"proofport_smoke":"ok"}')))
    monkeypatch.setattr(smoke, "LLMClient", lambda *a, **kw: client)
    assert smoke.main(["--env-file", str(settings[0]), "--execute", "--acknowledge-paid-api", "--max-cost-usd", "0.01"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["answer_validated"] and result["budget"]["attempts"] == len(calls) == 1
    assert settings[1] not in json.dumps(result)
    assert "legacy_shop" not in calls[0].content.decode()


def test_git_guard_detects_key_in_tracked_content_without_echoing(settings, tmp_path, monkeypatch):
    tracked = tmp_path / "tracked.py"; tracked.write_text(settings[1])
    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, b"tracked.py\0", b""))
    with pytest.raises(ModelUnavailable) as caught:
        smoke.credential_git_check(tmp_path, tmp_path / "missing.env", settings[1])
    assert caught.value.code == "tracked_credentials" and settings[1] not in str(caught.value)


def test_git_guard_requires_ignore_rule_for_credential_file(settings, tmp_path, monkeypatch):
    env = tmp_path / ".env"; env.write_text("MODEL_API_KEY=" + settings[1])
    def git(args, **kwargs):
        return subprocess.CompletedProcess(args, 1 if "check-ignore" in args else 0, b"", b"")
    monkeypatch.setattr(smoke.subprocess, "run", git)
    with pytest.raises(ModelUnavailable) as caught:
        smoke.credential_git_check(tmp_path, env, settings[1])
    assert caught.value.code == "unignored_credentials"


def test_git_guard_rejects_tracked_env_even_if_key_missing(settings, tmp_path, monkeypatch):
    env = tmp_path / ".env"; env.write_text("MODEL_API_KEY=")
    monkeypatch.setattr(smoke.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, b".env\0", b""))
    with pytest.raises(ModelUnavailable) as caught:
        smoke.credential_git_check(tmp_path, env, "")
    assert caught.value.code == "tracked_credentials"


@pytest.mark.parametrize("price", [None, "0"])
def test_live_requires_explicit_positive_model_pricing(settings, monkeypatch, price):
    if price is None:
        monkeypatch.delenv("PRICE_OUT_PER_MTOK")
    else:
        monkeypatch.setenv("PRICE_OUT_PER_MTOK", price)
    with pytest.raises(ModelUnavailable) as caught:
        LLMClient(settings[0], allow_live=True, limits=LLMLimits())
    assert caught.value.code == "pricing_required"


@pytest.mark.parametrize("changes", [{"max_calls": True}, {"max_calls": 0}, {"max_output_tokens": 0},
                                    {"max_total_tokens": 1}, {"max_cost_usd": "NaN"}, {"max_cost_usd": "-1"},
                                    {"timeout_seconds": float("nan")}, {"timeout_seconds": 31}])
def test_limits_reject_invalid_configuration(changes):
    with pytest.raises(ValueError):
        LLMLimits(**changes)
