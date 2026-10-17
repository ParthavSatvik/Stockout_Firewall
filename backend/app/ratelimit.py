from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


def login_limit() -> str:
    """Stricter per-IP limit on password login to slow credential stuffing (read per request)."""
    return get_settings().login_rate_limit
