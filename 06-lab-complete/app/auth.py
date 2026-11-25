"""API Key authentication qua header X-API-Key."""
import hmac
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Xác thực X-API-Key từ header; thiếu hoặc sai trả HTTP 401."""
    if (
        not settings.agent_api_key
        or not api_key
        or not hmac.compare_digest(api_key, settings.agent_api_key)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )
    return api_key
