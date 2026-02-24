from __future__ import annotations

from threading import Lock
from time import time

_used_nonces: dict[str, float] = {}
_nonce_lock = Lock()


def consume_oauth_nonce_once(namespace: str, nonce: str, *, max_age_seconds: int) -> bool:
    """
    Return True only the first time a nonce is seen within the replay window.
    Later calls with the same nonce return False until the window expires.
    """
    now = time()
    key = f"{namespace}:{nonce}"
    expiry = now + max(max_age_seconds, 1)
    with _nonce_lock:
        for seen_key, seen_expiry in list(_used_nonces.items()):
            if seen_expiry <= now:
                _used_nonces.pop(seen_key, None)
        if key in _used_nonces:
            return False
        _used_nonces[key] = expiry
        return True

