"""Cross-cutting API pieces: Problem Details errors, case-access tokens, admin auth, token-bucket rate limits."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Iterator

from appeal_core.db import session_factory
from appeal_core.settings import get_settings
from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session


class Problem(HTTPException):
    """RFC 9457 Problem Details."""

    def __init__(self, status: int, title: str, detail: str = "", type_: str = "about:blank", **extra):
        super().__init__(status_code=status, detail=detail)
        self.title = title
        self.type_ = type_
        self.extra = extra


def get_db() -> Iterator[Session]:
    s = session_factory()()
    try:
        yield s
    finally:
        s.close()


def case_token(case_id: str) -> str:
    return hmac.new(get_settings().case_token_secret.encode(), case_id.encode(), hashlib.sha256).hexdigest()


def require_case_access(case_id: str, request: Request, authorization: str | None = Header(default=None)) -> str:
    tok = None
    if authorization and authorization.lower().startswith("bearer "):
        tok = authorization.split(" ", 1)[1].strip()
    tok = tok or request.query_params.get("token")
    if not tok or not hmac.compare_digest(tok, case_token(case_id)):
        raise Problem(404, "Case not found", "No case with this ID is available to you.")
    return case_id


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or not hmac.compare_digest(x_admin_token, get_settings().admin_token):
        raise Problem(401, "Admin token required")


class TokenBucket:
    """Token bucket per key. Counters live in Redis when available, else in process memory."""

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.rate = refill_per_sec
        self.mem: dict[str, tuple[float, float]] = {}
        self._redis = None
        try:
            import redis

            r = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5)
            r.ping()
            self._redis = r
        except Exception:
            self._redis = None

    _LUA = """
    local k = KEYS[1]; local cap = tonumber(ARGV[1]); local rate = tonumber(ARGV[2]); local now = tonumber(ARGV[3])
    local v = redis.call('HMGET', k, 't', 'ts'); local t = tonumber(v[1]) or cap; local ts = tonumber(v[2]) or now
    t = math.min(cap, t + (now - ts) * rate)
    local ok = 0
    if t >= 1 then t = t - 1; ok = 1 end
    redis.call('HSET', k, 't', t, 'ts', now); redis.call('EXPIRE', k, 3600)
    return ok
    """

    def allow(self, key: str) -> bool:
        now = time.time()
        if self._redis is not None:
            try:
                return bool(self._redis.eval(self._LUA, 1, f"rl:{key}", self.capacity, self.rate, now))
            except Exception:
                pass
        t, ts = self.mem.get(key, (float(self.capacity), now))
        t = min(self.capacity, t + (now - ts) * self.rate)
        ok = t >= 1
        self.mem[key] = (t - 1 if ok else t, now)
        return ok
