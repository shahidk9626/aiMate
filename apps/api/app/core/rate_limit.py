"""Redis fixed-window rate limiting (ADR-023, STAGE_2_DESIGN §6).

- One counter per (rule, window, subject): INCR + EXPIRE in a transaction.
- Subjects (emails, IPs) are hashed before use in keys, so Redis never holds
  personal data in readable form.
- If Redis is unreachable the request is ALLOWED and a warning is logged:
  failing closed would let a Redis outage lock every user out of login.
  Argon2 hashing still makes online password guessing expensive meanwhile.
"""

import hashlib
import math
import time
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import RateLimitedError
from app.core.logging import get_logger

logger = get_logger("app.rate_limit")


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    retry_after_seconds: int


def _subject_digest(subject: str) -> str:
    return hashlib.sha256(subject.strip().lower().encode()).hexdigest()[:32]


class RateLimiter:
    def __init__(self, redis: Redis, prefix: str = "rl") -> None:
        self.redis = redis
        self.prefix = prefix

    def key(self, rule: RateLimitRule, subject: str, window: int) -> str:
        return f"{self.prefix}:{rule.name}:{window}:{_subject_digest(subject)}"

    async def hit(self, rule: RateLimitRule, subject: str) -> RateLimitResult:
        now = time.time()
        window = int(now // rule.window_seconds)
        retry_after = math.ceil((window + 1) * rule.window_seconds - now)
        key = self.key(rule, subject, window)
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, rule.window_seconds + 1)
                count, _ = await pipe.execute()
        except (RedisError, OSError) as exc:
            logger.warning("rate_limit_unavailable", rule=rule.name, error_type=type(exc).__name__)
            return RateLimitResult(allowed=True, count=0, retry_after_seconds=0)
        return RateLimitResult(
            allowed=int(count) <= rule.limit,
            count=int(count),
            retry_after_seconds=retry_after,
        )

    async def enforce(self, rule: RateLimitRule, subject: str) -> None:
        result = await self.hit(rule, subject)
        if not result.allowed:
            logger.info("rate_limited", rule=rule.name)
            raise RateLimitedError(result.retry_after_seconds)


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter
