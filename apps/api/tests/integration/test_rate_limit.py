"""Rate limiter against the real Redis (db 15, isolated key prefix per run)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.rate_limit import RateLimiter, RateLimitRule
from app.core.redis import create_redis_client

RULE = RateLimitRule(name="login_ip_email", limit=3, window_seconds=60)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis(integration_settings: Settings) -> AsyncIterator[Redis]:
    client = create_redis_client(integration_settings)
    try:
        await client.ping()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Redis not reachable: {type(exc).__name__}")
    yield client
    await client.aclose()


@pytest.fixture
async def limiter(redis: Redis) -> AsyncIterator[RateLimiter]:
    prefix = f"rl-test-{uuid.uuid4().hex[:8]}"
    yield RateLimiter(redis, prefix=prefix)
    keys = [key async for key in redis.scan_iter(f"{prefix}:*")]
    if keys:
        await redis.delete(*keys)


@pytest.mark.anyio
async def test_allows_up_to_the_limit_then_blocks(limiter: RateLimiter) -> None:
    results = [await limiter.hit(RULE, "alice@example.com") for _ in range(4)]

    assert [r.allowed for r in results] == [True, True, True, False]
    assert [r.count for r in results] == [1, 2, 3, 4]
    assert 1 <= results[-1].retry_after_seconds <= 60


@pytest.mark.anyio
async def test_subjects_are_counted_separately_and_case_insensitively(
    limiter: RateLimiter,
) -> None:
    for _ in range(3):
        await limiter.hit(RULE, "alice@example.com")

    assert not (await limiter.hit(RULE, "ALICE@example.com ")).allowed
    assert (await limiter.hit(RULE, "bob@example.com")).allowed


@pytest.mark.anyio
async def test_enforce_raises_rate_limited_with_retry_after(limiter: RateLimiter) -> None:
    for _ in range(3):
        await limiter.enforce(RULE, "carol@example.com")

    with pytest.raises(RateLimitedError) as exc_info:
        await limiter.enforce(RULE, "carol@example.com")
    assert int(exc_info.value.headers["Retry-After"]) >= 1


@pytest.mark.anyio
async def test_keys_contain_no_personal_data_and_expire(limiter: RateLimiter, redis: Redis) -> None:
    await limiter.hit(RULE, "dave@example.com")

    keys = [key async for key in redis.scan_iter(f"{limiter.prefix}:*")]
    assert len(keys) == 1
    key = keys[0].decode()
    assert "dave" not in key and "example.com" not in key
    assert 0 < await redis.ttl(key) <= RULE.window_seconds + 1


@pytest.mark.anyio
async def test_redis_outage_fails_open() -> None:
    broken = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.5)
    limiter = RateLimiter(broken)

    result = await limiter.hit(RULE, "eve@example.com")

    assert result.allowed
    await broken.aclose()
