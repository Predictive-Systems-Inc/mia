"""ULID helpers. IDs are monotonic within this process so ordering by id follows insert order."""

import threading
import time

from ulid import ULID

_lock = threading.Lock()
_last: bytes = b""


def new_id() -> str:
    """Return a new ULID string, strictly greater than any id returned before in this process."""
    global _last
    with _lock:
        candidate = ULID.from_timestamp(time.time()).bytes
        if _last and candidate <= _last:
            candidate = (int.from_bytes(_last, "big") + 1).to_bytes(16, "big")
        _last = candidate
        return str(ULID.from_bytes(candidate))
