"""Cost guard lưu chi phí LLM theo ngày trong Redis."""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def check_budget() -> None:
    """Kiểm tra tổng chi phí trong Redis trước khi gọi LLM; vượt ngưỡng trả 402."""
    try:
        current = float(r.get(_budget_key()) or 0.0)
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cost guard backend unavailable",
        ) from exc

    if current >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Tính chi phí request và cộng dồn vào Redis."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    key = _budget_key()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 48 * 3600)
        pipe.execute()
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cost guard backend unavailable",
        ) from exc
    return round(cost, 8)
