"""Runtime security settings for the API: environment, demo/read-only mode, CORS, errors and log redaction.

Configured only through environment variables. Defaults keep the local development behaviour unchanged.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("caderno_inteligente.api")

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
TRUE = {"1", "true", "yes", "on", "sim"}
FALSE = {"0", "false", "no", "off", "nao", "não"}
MAX_BODY_BYTES = 16 * 1024
TEXT_LIMITS = {"sku": 32, "note": 2000, "user_name": 80, "owner": 80, "case_action": 200, "search": 100}
MAX_ANALYSIS_MINUTES = 24 * 60
WRITE_DISABLED_MESSAGE = "Registro desabilitado nesta publicação (modo somente leitura). Os dados exibidos continuam disponíveis para consulta."


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in TRUE:
        return True
    if normalized in FALSE:
        return False
    logger.warning("invalid_boolean_setting name=%s using_default=%s", name, default)
    return default


def _valid_origin(value: str) -> bool:
    parts = urlsplit(value)
    return (
        parts.scheme in ("http", "https")
        and bool(parts.hostname)
        and "*" not in value
        and not parts.path.strip("/")
        and not parts.query
        and not parts.fragment
        and not parts.username
        and not parts.password
    )


@dataclass(frozen=True)
class Settings:
    environment: str
    demo_mode: bool
    write_enabled: bool
    cors_origins: tuple[str, ...]
    rejected_origins: tuple[str, ...] = field(default=())

    @property
    def production(self) -> bool:
        return self.environment == "production"


def load_settings() -> Settings:
    environment = (os.getenv("APP_ENV") or "development").strip().lower()
    if environment not in ("development", "production"):
        logger.warning("invalid_app_env value_ignored using=production")
        environment = "production"  # Fail closed: an unknown value must not expose internal details.
    raw = os.getenv("CORS_ORIGINS")
    if raw is None:
        candidates = [] if environment == "production" else list(DEV_ORIGINS)
    else:
        candidates = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    accepted = tuple(dict.fromkeys(origin for origin in candidates if _valid_origin(origin)))
    rejected = tuple(origin for origin in candidates if not _valid_origin(origin))
    for origin in rejected:
        logger.warning("cors_origin_rejected origin=%r reason=formato_invalido_ou_curinga", origin)
    if environment == "production" and not accepted:
        logger.warning("cors_no_origins production sem CORS_ORIGINS válido: navegadores de outros domínios serão bloqueados")
    return Settings(
        environment=environment,
        demo_mode=_flag("DEMO_MODE", False),
        write_enabled=_flag("WRITE_ENABLED", True),
        cors_origins=accepted,
        rejected_origins=rejected,
    )


# ------------------------------------------------------------------ logging

_CONNECTION_STRING = re.compile(r"postgres(?:ql)?://[^\s'\"]+", re.IGNORECASE)
_PASSWORD = re.compile(r"(password\s*[=:]\s*)[^\s'\"&]+", re.IGNORECASE)


def redact(text: str) -> str:
    """Remove connection strings, passwords and the literal DATABASE_URL from any text."""
    secret = os.getenv("DATABASE_URL")
    if secret:
        text = text.replace(secret, "<DATABASE_URL redigida>")
    text = _CONNECTION_STRING.sub("<connection-string redigida>", text)
    return _PASSWORD.sub(r"\1<redigida>", text)


class RedactingFilter(logging.Filter):
    """Applied to every handler so no log line (including tracebacks) prints DATABASE_URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if record.exc_info:
            formatter = logging.Formatter()
            message = f"{message}\n{formatter.formatException(record.exc_info)}"
            record.exc_info = None
            record.exc_text = None
        record.msg = redact(message)
        record.args = ()
        return True


def install_log_redaction() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())


# ------------------------------------------------------------ write access

def write_guard(settings_provider):
    def require_write_access() -> None:
        if not settings_provider().write_enabled:
            raise HTTPException(403, WRITE_DISABLED_MESSAGE)
    return require_write_access


def clean_text(value: str) -> str:
    """Trim and reject control characters (line breaks and tabs are allowed in free text)."""
    value = value.strip()
    if any((ord(char) < 32 and char not in "\n\t\r") or ord(char) == 127 for char in value):
        raise ValueError("Texto contém caracteres de controle não permitidos")
    return value


def public_message(settings: Settings, message: str, error: Exception) -> str:
    """Development keeps the technical cause; production returns only the generic message and logs the cause."""
    if settings.production:
        logger.warning("handled_error message=%s error_type=%s detail=%s", message, type(error).__name__, redact(str(error)))
        return message
    return f"{message}: {redact(str(error))}"


# ---------------------------------------------------- errors and middleware

def install_error_handling(app: FastAPI, settings_provider) -> None:
    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
                return JSONResponse({"detail": f"Requisição maior que o limite de {MAX_BODY_BYTES // 1024} KB."}, status_code=413,
                                    headers={"X-Request-ID": request_id})
        try:
            response = await call_next(request)
        except Exception as error:  # noqa: BLE001 - last-resort handler; details go to the redacted log only.
            logger.error("api_unhandled_error request_id=%s method=%s path=%s error_type=%s", request_id, request.method,
                         request.url.path, type(error).__name__, exc_info=True)
            settings = settings_provider()
            detail = (f"Erro interno. Código de referência: {request_id}." if settings.production
                      else f"Erro interno ({type(error).__name__}): {redact(str(error))}. Código de referência: {request_id}.")
            response = JSONResponse({"detail": detail}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.method != "GET":
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        errors = error.errors()
        if settings_provider().production:
            # Do not echo submitted values or internal context back to the client.
            errors = [{"type": item.get("type"), "loc": item.get("loc"), "msg": item.get("msg")} for item in errors]
        return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)
