"""Meta-compatible text client. Live calls require explicit authorization/limits.

No retry, redirect, proxy inheritance, response-body logging or fixture fallback.
Mock mode remains deterministic and does not construct an HTTP/SDK client.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from threading import Lock
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import APIError, APIConnectionError, APITimeoutError, DefaultHttpxClient, OpenAI

from backend.llm.budget import CallAttempt, LLMLimits, decimal_amount


class ModelUnavailable(RuntimeError):
    """A safe, actionable error without credentials or provider response bodies."""

    def __init__(self, message, code="model_unavailable"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CallUsage:
    prompt_hash: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    seconds: float
    mode: str


class LLMClient:
    def __init__(self, env_file: str | Path | None = None, *, allow_live=False,
                 limits: LLMLimits | None = None, http_client=None):
        env_file = env_file or Path(__file__).resolve().parents[2] / ".env"
        settings = {**dotenv_values(env_file), **os.environ}
        self.mode = (settings.get("LLM_MODE") or "mock").strip().lower()
        if self.mode not in {"live", "mock"}:
            raise ModelUnavailable("LLM_MODE must be live or mock for this milestone.")
        self.model = (settings.get("MODEL_NAME") or "").strip()
        self.base_url = (settings.get("MODEL_BASE_URL") or "https://api.meta.ai/v1").strip()
        self.calls: list[CallUsage] = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.attempts: list[CallAttempt] = []
        self.limits = limits
        self._reserved_cost = Decimal(0)
        self._reserved_tokens = 0
        self._lock = Lock()
        self._halted = self._closed = False
        self._http_client = http_client
        try:
            self._price_in = decimal_amount(settings.get("PRICE_IN_PER_MTOK", "1.25"))
            self._price_out = decimal_amount(settings.get("PRICE_OUT_PER_MTOK", "4.25"))
        except (ValueError, ArithmeticError):
            raise ModelUnavailable("Token prices must be finite, non-negative numbers.") from None
        self._client = None
        if self.mode == "live":
            self._api_key = settings.get("MODEL_API_KEY") or ""
            if not self._api_key.strip() or not self.model:
                raise ModelUnavailable("Set MODEL_API_KEY and MODEL_NAME in .env, or use LLM_MODE=mock.")
            if allow_live is not True or not isinstance(limits, LLMLimits):
                raise ModelUnavailable("Live calls require separate explicit authorization and LLMLimits.", "live_not_authorized")
            if not all(settings.get(k) for k in ("PRICE_IN_PER_MTOK", "PRICE_OUT_PER_MTOK")) or min(self._price_in, self._price_out) <= 0:
                raise ModelUnavailable("Supply verified positive PRICE_IN_PER_MTOK and PRICE_OUT_PER_MTOK for this model.", "pricing_required")
            try:
                url = urlsplit(self.base_url)
                safe = (url.scheme == "https" and url.hostname == "api.meta.ai" and url.port in {None, 443}
                        and url.path.rstrip("/") == "/v1" and not any((url.username, url.password, url.query, url.fragment)))
            except ValueError:
                safe = False
            if not safe:
                raise ModelUnavailable("Live credentials may only be sent to https://api.meta.ai/v1.", "unsafe_model_url")
            if self._api_key in self.model:
                raise ModelUnavailable("Credential detected in model configuration.", "unsafe_model_configuration")

    def _reserve(self, system, user, prompt_hash):
        limits = self.limits
        if self._api_key in system or self._api_key in user:
            raise ModelUnavailable("Credential detected in prompt; no request sent.", "credential_in_prompt")
        # Diagnostic HTTP logs may contain provider headers or input bodies.
        names = {"openai", "openai._base_client", "httpx", "httpx2", "httpcore", "httpcore2"}
        names.update(name for name in list(logging.Logger.manager.loggerDict)
                     if name.startswith(("openai.", "httpx.", "httpx2.", "httpcore.", "httpcore2.")))
        if any(logging.getLogger(name).isEnabledFor(logging.DEBUG) for name in names):
            raise ModelUnavailable("Disable SDK/HTTP debug logging before authorizing a live request.", "unsafe_model_logging")
        # UTF-8 bytes plus framing allowance is deliberately conservative, not
        # a verified tokenizer. Reserve the full input allowance, not this estimate.
        estimated = len(json.dumps([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                   ensure_ascii=False).encode("utf-8")) + 256
        tokens = limits.max_input_tokens + limits.max_output_tokens
        cost = (limits.max_input_tokens * self._price_in + limits.max_output_tokens * self._price_out) / 1_000_000
        if estimated > limits.max_input_tokens:
            raise ModelUnavailable("Input exceeds the conservative input allowance; no request sent.", "input_budget_exceeded")
        if (len(self.attempts) >= limits.max_calls or self._reserved_tokens + tokens > limits.max_total_tokens
                or self._reserved_cost + cost > limits.max_cost_usd):
            raise ModelUnavailable("LLM call/token/cost reservation budget exceeded; no request sent.", "budget_exceeded")
        self._reserved_tokens += tokens
        self._reserved_cost += cost
        self.attempts.append(CallAttempt(prompt_hash, tokens, float(cost)))

    @staticmethod
    def _api_failure(exc):
        if isinstance(exc, APITimeoutError):
            return ModelUnavailable("Model request timed out. Outcome/billing may be unknown; no automatic retry.", "model_timeout")
        if isinstance(exc, APIConnectionError):
            return ModelUnavailable("Model connection failed. Outcome/billing may be unknown; no automatic retry.", "model_connection_error")
        status = getattr(exc, "status_code", None)
        code, message = {
            401: ("model_authentication_failed", "Model authentication failed (401); check the private key."),
            403: ("model_permission_denied", "Model access denied (403); check model/project permissions."),
            429: ("model_rate_limited", "Model rate limit reached (429). Inspect provider quota before an explicitly authorized retry."),
            400: ("model_bad_request", "Provider rejected the request (400); check model/parameter compatibility."),
            404: ("model_not_found", "Configured model or endpoint was not found (404)."),
        }.get(status, ("model_service_error" if status and status >= 500 else "model_invalid_response",
                       "Provider request failed; response details withheld. No automatic retry."))
        return ModelUnavailable(message, code)

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        with self._lock:
            return self._complete(system, user, json_mode)

    def _complete(self, system, user, json_mode):
        if self._closed or self._halted:
            raise ModelUnavailable("Client session is closed/stopped; review the previous outcome before authorizing another session.", "live_session_stopped")
        if not isinstance(system, str) or not isinstance(user, str) or type(json_mode) is not bool:
            raise ModelUnavailable("Messages must be strings and json_mode a boolean.", "invalid_model_input")
        started = perf_counter()
        prompt = json.dumps([system, user, json_mode], ensure_ascii=False, separators=(",", ":"))
        if self.mode == "mock":
            answer = (
                '{"mode":"mock","message":"Simulated response; no model was called."}'
                if json_mode else "Mock response: migration plumbing is ready. No model was called."
            )
            # Mock mode never consumes tokens or incurs model charges.
            tokens_in = tokens_out = 0
        else:
            self._reserve(system, user, sha256(prompt.encode("utf-8")).hexdigest())
            options = {"response_format": {"type": "json_object"}} if json_mode else {}
            try:
                if self._client is None:
                    self._http_client = self._http_client or DefaultHttpxClient(follow_redirects=False, trust_env=False)
                    self._client = OpenAI(api_key=self._api_key, base_url=self.base_url,
                                          timeout=self.limits.timeout_seconds, max_retries=0, http_client=self._http_client)
                raw = self._client.chat.completions.with_raw_response.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    max_completion_tokens=self.limits.max_output_tokens, n=1, stream=False,
                    reasoning_effort="minimal", **options,
                )
                response = raw.parse()
                # The SDK can coerce strings/bools into integers. Check original
                # wire usage before accounting, rather than trusting coercion.
                usage = raw.http_response.json().get("usage")
                if not isinstance(usage, dict):
                    raise ModelUnavailable("Model token usage is missing; billing cannot be confirmed.", "model_usage_invalid")
                counts = tuple(usage.get(name) for name in ("prompt_tokens", "completion_tokens", "total_tokens"))
                if any(type(count) is not int or count < 0 for count in counts) or counts[2] != sum(counts[:2]):
                    raise ModelUnavailable("The model returned invalid token usage; billing cannot be confirmed.", "model_usage_invalid")
                tokens_in, tokens_out = counts[:2]
                self._record(prompt, tokens_in, tokens_out, started)
                self.attempts[-1] = replace(self.attempts[-1], usage_known=True)
                if tokens_in > self.limits.max_input_tokens or tokens_out > self.limits.max_output_tokens:
                    raise ModelUnavailable("Provider usage exceeded the reserved envelope. Stop and inspect billing.", "provider_budget_exceeded")
                if not isinstance(response.choices, list) or len(response.choices) != 1:
                    raise ModelUnavailable("Expected one model choice.", "model_invalid_response")
                choice = response.choices[0]
                answer = choice.message.content
                if choice.finish_reason != "stop":
                    raise ModelUnavailable("Model response was incomplete, refused or requested tools; candidate rejected.", "model_incomplete_response")
                if not isinstance(answer, str) or not answer.strip() or getattr(choice.message, "refusal", None) or getattr(choice.message, "tool_calls", None):
                    raise ModelUnavailable("The model returned no usable plain text.", "model_empty_response")
                if self._api_key in answer:
                    raise ModelUnavailable("Sensitive response withheld; do not export model content.", "model_sensitive_response")
                if json_mode:
                    parsed = json.loads(answer, parse_constant=_invalid_json_constant, object_pairs_hook=_unique_json_keys)
                    if not isinstance(parsed, dict):
                        raise ValueError
                self.attempts[-1] = replace(self.attempts[-1], outcome="ok")
                return answer
            except (APIError, ValueError, TypeError, AttributeError, ModelUnavailable) as exc:
                self._halted = True
                error = exc if isinstance(exc, ModelUnavailable) else self._api_failure(exc) if isinstance(exc, APIError) else ModelUnavailable(
                    "The model returned invalid JSON/response/usage. Details withheld; reserved budget retained.", "model_invalid_response")
                self.attempts[-1] = replace(self.attempts[-1], outcome=error.code)
                raise error from None
        self._record(prompt, tokens_in, tokens_out, started)
        return answer

    def _record(self, prompt, tokens_in, tokens_out, started):
        cost = float((self._price_in * tokens_in + self._price_out * tokens_out) / 1_000_000)
        self.calls.append(CallUsage(
            prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
            seconds=perf_counter() - started, mode=self.mode,
        ))
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd = sum(call.cost_usd for call in self.calls)

    def budget_snapshot(self):
        return {"attempts": len(self.attempts), "reserved_tokens": self._reserved_tokens,
                "reserved_cost_usd": float(self._reserved_cost), "reported_cost_usd": self.cost_usd,
                "usage_complete": all(item.usage_known for item in self.attempts), "stopped": self._halted}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._client is not None:
                self._client.close()
            if self._http_client is not None:
                self._http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _invalid_json_constant(_):
    raise ValueError("Non-finite JSON value.")


def _unique_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result
