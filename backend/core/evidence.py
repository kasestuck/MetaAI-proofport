"""In-memory, hash-chained evidence for the skeleton."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json


def entry_hash(entry: dict) -> str:
    payload = {key: value for key, value in entry.items() if key != "entry_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256((payload["prev_hash"] + canonical).encode("utf-8")).hexdigest()


class Evidence:
    def __init__(self):
        self._entries: list[dict] = []

    def append(self, event_type: str, detail: str, module: str | None = None) -> None:
        entry = {
            "seq": len(self._entries) + 1,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "type": event_type, "module": module, "detail": detail,
            "prev_hash": self._entries[-1]["entry_hash"] if self._entries else "0" * 64,
        }
        entry["entry_hash"] = entry_hash(entry)
        self._entries.append(entry)

    def since(self, seq: int) -> list[dict]:
        return deepcopy([entry for entry in self._entries if entry["seq"] > seq])

    def verify(self) -> bool:
        previous = "0" * 64
        for seq, entry in enumerate(self._entries, 1):
            if (entry["seq"] != seq or entry["prev_hash"] != previous
                    or entry["entry_hash"] != entry_hash(entry)):
                return False
            previous = entry["entry_hash"]
        return True
