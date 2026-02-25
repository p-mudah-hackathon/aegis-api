"""
Global error handling — consistent JSON error responses.
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("aegis")


class AegisError(Exception):
    """Base application error."""
    def __init__(self, code: str, message: str, status_code: int = 400, detail: dict = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class NotFoundError(AegisError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} '{identifier}' not found",
            status_code=404,
        )


class ConflictError(AegisError):
    def __init__(self, message: str):
        super().__init__(code="CONFLICT", message=message, status_code=409)


class ServiceUnavailableError(AegisError):
    def __init__(self, service: str):
        super().__init__(
            code="SERVICE_UNAVAILABLE",
            message=f"{service} is currently unavailable",
            status_code=503,
        )


def register_error_handlers(app: FastAPI):
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AegisError)
    async def aegis_error_handler(request: Request, exc: AegisError):
        logger.warning(f"[{exc.code}] {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP_ERROR",
                "message": exc.detail,
                "detail": {},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "detail": {"type": type(exc).__name__},
            },
        )
