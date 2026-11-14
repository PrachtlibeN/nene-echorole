import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.errors import ErrorEnvelope


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    SCENARIO_NOT_FOUND = "SCENARIO_NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    EVALUATION_NOT_FOUND = "EVALUATION_NOT_FOUND"
    SESSION_INVALID_STATE = "SESSION_INVALID_STATE"
    SESSION_NOT_ACTIVE = "SESSION_NOT_ACTIVE"
    SESSION_NOT_ENDED = "SESSION_NOT_ENDED"
    TURN_IN_PROGRESS = "TURN_IN_PROGRESS"
    EVALUATION_IN_PROGRESS = "EVALUATION_IN_PROGRESS"
    SESSION_TOO_SHORT = "SESSION_TOO_SHORT"
    AUDIO_TOO_LARGE = "AUDIO_TOO_LARGE"
    AUDIO_UNSUPPORTED_FORMAT = "AUDIO_UNSUPPORTED_FORMAT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUDIO_TOO_LONG = "AUDIO_TOO_LONG"
    AUDIO_EMPTY_OR_SILENT = "AUDIO_EMPTY_OR_SILENT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    LLM_BAD_OUTPUT = "LLM_BAD_OUTPUT"
    EVALUATION_PARSE_FAILED = "EVALUATION_PARSE_FAILED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
    STT_NOT_READY = "STT_NOT_READY"
    STT_UNAVAILABLE = "STT_UNAVAILABLE"
    LLM_TIMEOUT = "LLM_TIMEOUT"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        http_status: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details


API_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorEnvelope}
    for status in (400, 404, 409, 413, 415, 422, 500, 501, 502, 503, 504)
}


def _error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "code": code.value,
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            request,
            exc.http_status,
            exc.code,
            exc.message,
            exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "loc": list(error["loc"]),
                "msg": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _error_response(
            request,
            422,
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed.",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        code = ErrorCode.BAD_REQUEST if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
        return _error_response(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).error(
            "Unhandled request error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return _error_response(
            request,
            500,
            ErrorCode.INTERNAL_ERROR,
            "An unexpected error occurred.",
        )
