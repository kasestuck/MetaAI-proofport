"""Small synchronous OpenAI-compatible client, with an offline mock mode."""

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values
from openai import APIError, OpenAI


class ModelUnavailable(RuntimeError):
    """A safe, actionable error without credentials or provider response bodies."""


@dataclass(frozen=True)
class CallUsage:
    prompt_hash: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    seconds: float
    mode: str


class LLMClient:
    def __init__(self, env_file: str | Path | None = None):
        env_file = env_file or Path(__file__).resolve().parents[2] / ".env"
        self._settings = {**dotenv_values(env_file), **os.environ}
        self.mode = self._settings.get("LLM_MODE", "mock").lower()
        if self.mode not in {"live", "mock"}:
            raise ModelUnavailable("LLM_MODE must be live or mock for this milestone.")
        self.model = self._settings.get("MODEL_NAME", "")
        self.base_url = self._settings.get("MODEL_BASE_URL") or "https://api.meta.ai/v1"
        self.calls: list[CallUsage] = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        try:
            self._price_in = Decimal(self._settings.get("PRICE_IN_PER_MTOK", "1.25"))
            self._price_out = Decimal(self._settings.get("PRICE_OUT_PER_MTOK", "4.25"))
            if any(not p.is_finite() or p < 0 for p in (self._price_in, self._price_out)):
                raise ValueError
        except (ValueError, ArithmeticError) as exc:
            raise ModelUnavailable("Token prices must be finite, non-negative numbers.") from exc
        self._client = None
        if self.mode == "live":
            key = self._settings.get("MODEL_API_KEY", "")
            if not key or not self.model:
                raise ModelUnavailable("Set MODEL_API_KEY and MODEL_NAME in .env, or use LLM_MODE=mock.")
            self._client = OpenAI(
                api_key=key, base_url=self.base_url, timeout=30.0, max_retries=2,
            )

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
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
            options = {"response_format": {"type": "json_object"}} if json_mode else {}
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    **options,
                )
            except APIError:
                raise ModelUnavailable(
                    "Model request failed after bounded retries. Check model settings and connectivity."
                ) from None
            if not response.choices or not response.choices[0].message.content:
                raise ModelUnavailable("The model returned no text.")
            answer = response.choices[0].message.content
            if response.usage is None:
                raise ModelUnavailable("The model returned no token usage; cost cannot be accounted for.")
            tokens_in = response.usage.prompt_tokens
            tokens_out = response.usage.completion_tokens
        cost = float((self._price_in * tokens_in + self._price_out * tokens_out) / 1_000_000)
        self.calls.append(CallUsage(
            prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
            tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost,
            seconds=perf_counter() - started, mode=self.mode,
        ))
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd = sum(call.cost_usd for call in self.calls)
        return answer

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
