"""Excepciones específicas de la API + handlers globales.

Cada excepción tiene un `code` corto (kebab/snake) que el frontend puede
parsear para decidir UX (toast vs banner vs redirect). El shape JSON es
siempre `{error, code, details}` para no romper contratos.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        # Permitir override por instancia (los call-sites pasan status_code=409,
        # etc.). Sin esto, APIError("...", status_code=409) lanzaba TypeError.
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class ProductNotFoundError(APIError):
    status_code = 404
    code = "product_not_found"


class PhotoNotFoundError(APIError):
    status_code = 404
    code = "photo_not_found"


class UserNotFoundError(APIError):
    status_code = 404
    code = "user_not_found"


class VoiceNotFoundError(APIError):
    status_code = 404
    code = "voice_not_found"


class ProductAlreadyAssignedError(APIError):
    status_code = 409
    code = "product_already_assigned"


class GenerationNotFoundError(APIError):
    status_code = 404
    code = "generation_not_found"


class VideoFileNotFoundError(APIError):
    status_code = 404
    code = "video_file_not_found"


class JobNotFoundError(APIError):
    status_code = 404
    code = "job_not_found"


class JobNotCancellableError(APIError):
    status_code = 409
    code = "job_not_cancellable"


class InvalidEnqueueRequestError(APIError):
    status_code = 422
    code = "invalid_enqueue_request"


class QuotaExceededError(APIError):
    status_code = 429
    code = "quota_exceeded"


class PresetNotFoundError(APIError):
    status_code = 404
    code = "preset_not_found"


class PronosticosVersionNotFoundError(APIError):
    status_code = 404
    code = "pronosticos_version_not_found"


class InvalidTempPathError(APIError):
    status_code = 422
    code = "invalid_temp_path"


class ValidationError(APIError):
    status_code = 422
    code = "validation_error"


class DriveError(APIError):
    status_code = 500
    code = "drive_error"


class GeminiError(APIError):
    status_code = 502
    code = "gemini_error"


class UnauthorizedError(APIError):
    status_code = 401
    code = "unauthorized"


def _json_payload(error: str, code: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": error, "code": code, "details": details or {}}


def register_exception_handlers(app: FastAPI) -> None:
    """Registra handlers globales que devuelven JSON con shape consistente."""

    @app.exception_handler(APIError)
    async def _api_error_handler(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_json_payload(exc.message, exc.code, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # `exc.errors()` puede contener objetos no JSON-serializables (p.ej.
        # `ValueError` en `ctx`). `jsonable_encoder` los convierte a strings
        # de forma segura.
        return JSONResponse(
            status_code=422,
            content=_json_payload(
                "Datos de entrada inválidos.",
                "validation_error",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            500: "internal_error",
        }
        code = code_map.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_json_payload(str(exc.detail), code),
        )
