"""Shared, bounded failed-code budget for HTTP and caption WebSocket access."""

from __future__ import annotations

import math
import secrets
import time

JOIN_CODE_RATE_LIMIT = 10
JOIN_CODE_RATE_WINDOW_SECONDS = 60
MAX_CLIENTS = 10000
_join_code_attempts: dict[str, tuple[int, float]] = {}


class JoinCodeThrottled(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Join-code attempt budget exhausted")


def verify_join_code(client_ip: str, submitted: str | None, expected: str | None) -> bool:
    """Check the budget before comparing any submitted guess, including cookies.

    Calls contain no awaits, so checking and recording are atomic in the portal's
    single event loop. Expired entries are removed and new clients fail closed
    when the bounded table is full. Account authentication bypasses this budget.
    """
    if not submitted:
        return False
    now = time.monotonic()
    for ip, (_, start) in list(_join_code_attempts.items()):
        if now - start >= JOIN_CODE_RATE_WINDOW_SECONDS:
            del _join_code_attempts[ip]
    count, start = _join_code_attempts.get(client_ip, (0, now))
    if count >= JOIN_CODE_RATE_LIMIT:
        raise JoinCodeThrottled(max(1, math.ceil(JOIN_CODE_RATE_WINDOW_SECONDS - (now - start))))
    if client_ip not in _join_code_attempts and len(_join_code_attempts) >= MAX_CLIENTS:
        raise JoinCodeThrottled(JOIN_CODE_RATE_WINDOW_SECONDS)
    if expected and secrets.compare_digest(submitted.encode(), expected.encode()):
        _join_code_attempts.pop(client_ip, None)
        return True
    _join_code_attempts[client_ip] = (count + 1, start)
    return False
