"""Rate Limiter - Gioi han so request."""
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from src.constants import DEFAULT_REQUESTS_PER_MINUTE, RATE_LIMIT_WINDOW_S


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter.

    For production, use Redis-backed rate limiting.
    """

    def __init__(self, app, requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries
        self.requests[client_ip] = [
            t for t in self.requests[client_ip] if now - t < RATE_LIMIT_WINDOW_S
        ]

        if len(self.requests[client_ip]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Qua nhieu request. Vui long thu lai sau.",
            )

        self.requests[client_ip].append(now)
        return await call_next(request)
