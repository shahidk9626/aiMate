"""Redis client factory (async). The client connects lazily on first command."""

from redis.asyncio import Redis

from app.core.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password.get_secret_value() if settings.redis_password else None,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=5,
        health_check_interval=30,
    )
