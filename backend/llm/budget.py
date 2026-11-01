"""Explicit, per-client reservations; not a provider billing/spending guarantee."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def decimal_amount(value, *, positive=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Amounts must be finite non-negative decimals.") from None
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError("Amounts must be finite non-negative decimals.")
    return result


@dataclass(frozen=True)
class LLMLimits:
    max_calls: int = 1
    max_input_tokens: int = 2048
    max_output_tokens: int = 256
    max_total_tokens: int = 2304
    max_cost_usd: Decimal = Decimal("0.01")
    timeout_seconds: float = 15

    def __post_init__(self):
        for name, ceiling in (("max_calls", 10), ("max_input_tokens", 65536),
                              ("max_output_tokens", 8192), ("max_total_tokens", 737280)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Invalid LLM budget integer limit.")
        if self.max_total_tokens < self.max_input_tokens + self.max_output_tokens:
            raise ValueError("Total budget must cover at least one full reservation.")
        if isinstance(self.timeout_seconds, bool) or not 0 < self.timeout_seconds <= 30:
            raise ValueError("LLM timeout must be finite and between zero and 30 seconds.")
        object.__setattr__(self, "max_cost_usd", decimal_amount(self.max_cost_usd, positive=True))


@dataclass(frozen=True)
class CallAttempt:
    prompt_hash: str
    reserved_tokens: int
    reserved_cost_usd: float
    outcome: str = "reserved"
    usage_known: bool = False
    # Safe wire diagnostics only; no raw content, headers or provider messages.
    finish_reason: str | None = None
    finish_reason_matches_sdk: bool | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    output_token_limit: int | None = None
    output_limit_reached: bool | None = None
    content_sha256: str | None = None
    content_bytes: int | None = None
    json_object_valid: bool | None = None
