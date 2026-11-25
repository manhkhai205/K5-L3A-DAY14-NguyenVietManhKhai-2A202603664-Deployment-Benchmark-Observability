"""Kết nối Redis dùng chung cho rate limiter và cost guard."""
import redis

from app.config import settings

r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
)


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho GET /ready; trả False nếu lỗi."""
    try:
        return bool(r.ping())
    except (redis.RedisError, OSError, ValueError):
        return False
