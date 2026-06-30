"""Error Handler - Xu ly loi tap trung."""
import traceback
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from src.utils.logger import setup_logger

logger = setup_logger("api.error")


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured error responses."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled error: {exc}\n{traceback.format_exc()}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc) if self._is_debug() else "Da xay ra loi.",
                },
            )

    def _is_debug(self) -> bool:
        import os
        return os.getenv("ENVIRONMENT", "production") == "development"
