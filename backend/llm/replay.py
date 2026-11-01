"""Strict ordered prompt-bound recordings, never a fixture fallback or network path."""

import json
from pathlib import Path
import re

from backend.core.projects import linked


class ReplayResponses:
    def __init__(self, path):
        from backend.llm.client import ModelUnavailable, _unique_json_keys, _invalid_json_constant
        path = Path(path).absolute()
        try:
            if any(linked(p) for p in (path, *path.parents)) or path.stat().st_size > 2_000_000: raise ValueError
            data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_keys, parse_constant=_invalid_json_constant)
            if set(data) != {"mode", "responses"} or data["mode"] != "explicit_model_response_replay_not_live": raise ValueError
            records = data["responses"]
            if not isinstance(records, list) or not 1 <= len(records) <= 10: raise ValueError
            for record in records:
                if not isinstance(record, dict) or set(record) != {"prompt_hash", "response"}: raise ValueError
                if not isinstance(record["prompt_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", record["prompt_hash"]): raise ValueError
                if not isinstance(record["response"], str) or not 1 <= len(record["response"].encode()) <= 262144: raise ValueError
        except (OSError, ValueError, TypeError, KeyError):
            raise ModelUnavailable("Invalid/missing bounded response replay. No fixture/network fallback.", "model_replay_unavailable") from None
        self.records, self.position = records, 0

    def next(self, fingerprint):
        from backend.llm.client import ModelUnavailable
        if self.position >= len(self.records) or self.records[self.position]["prompt_hash"] != fingerprint:
            raise ModelUnavailable("Replay miss/order mismatch. No response substituted.", "model_replay_miss")
        response = self.records[self.position]["response"]
        self.position += 1
        return response
