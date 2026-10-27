"""Append-only, hash-chained evidence with optional durable storage."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from functools import wraps
import threading


def _synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


def entry_hash(entry: dict) -> str:
    payload = {key: value for key, value in entry.items() if key != "entry_hash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256((payload["prev_hash"] + canonical).encode("utf-8")).hexdigest()


class Evidence:
    def __init__(self):
        self._lock = threading.RLock()
        self._entries: list[dict] = []
        self.path: Path | None = None

    @_synchronized
    def bind(self, path: Path) -> None:
        with path.open("x", encoding="utf-8") as stream:
            for entry in self._entries:
                stream.write(json.dumps(entry, sort_keys=True, ensure_ascii=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.path = path

    @_synchronized
    def append(self, event_type: str, detail: str, module: str | None = None) -> None:
        entry = {
            "seq": len(self._entries) + 1,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "type": event_type, "module": module, "detail": detail,
            "prev_hash": self._entries[-1]["entry_hash"] if self._entries else "0" * 64,
        }
        entry["entry_hash"] = entry_hash(entry)
        if self.path:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, sort_keys=True, ensure_ascii=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        self._entries.append(entry)

    @_synchronized
    def since(self, seq: int) -> list[dict]:
        return deepcopy([entry for entry in self._entries if entry["seq"] > seq])

    @_synchronized
    def verify(self) -> bool:
        if self.path:
            try:
                persisted = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
                if persisted != self._entries:
                    return False
            except (ValueError, OSError):
                return False
        previous = "0" * 64
        for seq, entry in enumerate(self._entries, 1):
            if (entry["seq"] != seq or entry["prev_hash"] != previous
                    or entry["entry_hash"] != entry_hash(entry)):
                return False
            previous = entry["entry_hash"]
        return True
