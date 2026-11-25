"""Rate limiting dùng Redis sorted set (sliding window 60 giây)."""
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    now = time.time()
    window_start = now - 60.0
    redis_key = f"ratelimit:{key}"

    try:
        r.zremrangebyscore(redis_key, "-inf", window_start)
        count = r.zcard(redis_key)
        if count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, 120)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Rate limiter backend unavailable",
        ) from exc
