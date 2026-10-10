"""Fase 3: login e cadastro de SKU (criar, editar, excluir de forma lógica e reativar).

O cadastro só grava com DATA_SOURCE=banco, com login e com WRITE_ENABLED. Cada alteração passa pelas mesmas
validações de schemas.py (validate_dataset na prévia da base inteira) e incrementa a versão dos dados.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.security import clean_text
from caderno_inteligente.auth import MIN_SECRET_LENGTH, InvalidToken, UserStore, issue_token, read_token
from caderno_inteligente.dataset_store import (
    DatasetStore,
    SkuConflict,
    SkuNotFound,
    apply_sku_rows,
    normalise_sku,
    sku_rows,
)
from caderno_inteligente.transformations import normalise_dataset
from caderno_inteligente.validation import validate_dataset

logger = logging.getLogger("caderno_inteligente.api")

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_MAX_FAILURES = 5
UNAUTHORIZED = "Sessão inválida ou expirada. Entre novamente."
SPREADSHEET_MODE = "O cadastro de SKU exige a base no banco (DATA_SOURCE=banco). Esta publicação lê a planilha."
_dev_secret = secrets.token_urlsafe(48)


def auth_secret(production: bool) -> str | None:
    """AUTH_SECRET (32+ caracteres). Sem ele, desenvolvimento usa um segredo aleatório por processo; produção desliga o login."""
    value = (os.getenv("AUTH_SECRET") or "").strip()
    if len(value) >= MIN_SECRET_LENGTH:
        return value
    if value:
        logger.warning("auth_secret_too_short min_length=%s login_disabled=%s", MIN_SECRET_LENGTH, production)
    return None if production else _dev_secret


OPEN_USER = {"email": "sem-login", "name": ""}


def auth_required() -> bool:
    """AUTH_REQUIRED=true exige login no cadastro de SKU. Padrão false por enquanto: o cadastro fica liberado
    e as alterações são registradas como 'sem-login'. O login continua implementado para ser religado depois."""
    return (os.getenv("AUTH_REQUIRED") or "").strip().lower() in ("1", "true", "yes", "on", "sim")


def token_hours() -> int:
    try:
        return max(1, min(24, int(os.getenv("AUTH_TOKEN_HOURS", "8"))))
    except ValueError:
        return 8


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(_Strict):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class SkuFields(_Strict):
    produto: str = Field(min_length=1, max_length=120)
    familia: str = Field(min_length=1, max_length=60)
    curva_abc: Literal["A", "B", "C"]
    lead_time_dias: int = Field(ge=0, le=365)
    lote_minimo: int = Field(ge=0, le=1_000_000)
    estoque_atual: int = Field(ge=0, le=10_000_000)
    estoque_seguranca_dias: int = Field(ge=0, le=365)
    venda_media_dia: float = Field(ge=0, le=1_000_000)

    @field_validator("produto", "familia")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = clean_text(value)
        if not value or "\n" in value or "\t" in value:
            raise ValueError("Texto obrigatório, em uma linha")
        return value


class SkuCreate(SkuFields):
    sku: str = Field(min_length=1, max_length=32)

    @field_validator("sku")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().upper()
        if not SKU_PATTERN.match(value):
            raise ValueError("Use letras, números, ponto, hífen ou sublinhado (até 32 caracteres)")
        return value


def _error_key(error: dict) -> tuple:
    return (error.get("code"), error.get("sheet") or error.get("child_sheet"), error.get("column") or error.get("child_column"))


def create_registry_router(*, production: Callable[[], bool], data_source: Callable[[], str], store: Callable[[], DatasetStore],
                           users: Callable[[], UserStore], write_access, on_change: Callable[[], None]) -> APIRouter:
    router = APIRouter(prefix="/api")
    failures: dict[str, deque] = defaultdict(deque)

    def secret() -> str:
        value = auth_secret(production())
        if value is None:
            raise HTTPException(503, "Login não configurado nesta publicação (AUTH_SECRET ausente ou curto).")
        return value

    def current_user(request: Request) -> dict[str, str]:
        if not auth_required():
            return OPEN_USER
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(401, "Entre com seu usuário para cadastrar SKUs.", headers={"WWW-Authenticate": "Bearer"})
        try:
            claims = read_token(secret(), token.strip())
        except InvalidToken as error:
            raise HTTPException(401, UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"}) from error
        user = users().active_user(claims["sub"])
        if user is None:
            raise HTTPException(401, UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"})
        return user

    def database_mode() -> None:
        if data_source() != "banco":
            raise HTTPException(409, SPREADSHEET_MODE)

    editor = [write_access, Depends(database_mode)]

    def throttle(email: str) -> None:
        now = time.monotonic()
        recent = failures[email]
        while recent and now - recent[0] > LOGIN_WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= LOGIN_MAX_FAILURES:
            raise HTTPException(429, "Muitas tentativas de login. Aguarde alguns minutos.")

    @router.post("/auth/login")
    def login(item: Login):
        key = item.email.strip().lower()
        signing_secret = secret()
        throttle(key)
        user = users().authenticate(item.email, item.password)
        if user is None:
            failures[key].append(time.monotonic())
            logger.warning("login_failed")
            raise HTTPException(401, "E-mail ou senha incorretos.")
        failures.pop(key, None)
        token, expires = issue_token(signing_secret, user["email"], user["name"], token_hours() * 3600)
        logger.info("login_ok")
        return {"token": token, "expires_at": expires, "user": user}

    @router.get("/auth/me")
    def me(user: dict = Depends(current_user)):
        return {"user": user}

    @router.get("/skus/cadastro")
    def registry(user: dict = Depends(current_user)):
        if data_source() != "banco":
            return {"data_source": data_source(), "editable": False, "families": [], "items": []}
        items = store().list_skus()
        families = sorted({item["familia"] for item in items if item["familia"] and item["ativo"]})
        return {"data_source": "banco", "editable": True, "families": families, "items": items}

    def validated_rows(sku: str, fields: SkuFields, current: dict | None) -> dict:
        dataset = store().load_dataset()
        families = set(dataset["Produtos"]["Família"].dropna())
        if fields.familia not in families:
            raise HTTPException(422, f"Família desconhecida: {fields.familia}. Use uma família da base (capacidade e prazos dependem dela).")
        rows = sku_rows(sku, fields.model_dump(), current)
        baseline = {_error_key(error) for error in validate_dataset(normalise_dataset(dataset))["errors"]}
        preview = validate_dataset(normalise_dataset(apply_sku_rows(dataset, sku, rows)))
        new_errors = [error for error in preview["errors"] if _error_key(error) not in baseline]
        if new_errors:
            found = "; ".join(f"{error['code']} em {error.get('sheet') or error.get('child_sheet')}" for error in new_errors)
            raise HTTPException(422, f"O SKU deixaria a base inválida: {found}.")
        return rows

    def saved(version: int, sku: str, action: str) -> dict:
        on_change()
        logger.info("sku_registry action=%s sku=%s version=%s", action, sku, version)
        return {"sku": sku, "version": version}

    @router.post("/skus", status_code=201, dependencies=editor)
    def create(item: SkuCreate, user: dict = Depends(current_user)):
        if store().sku_state(item.sku) is not None:
            raise HTTPException(409, f"SKU {item.sku} já existe no cadastro (ativo ou inativo).")
        rows = validated_rows(item.sku, item, None)
        try:
            version = store().save_sku(item.sku, rows, user["email"], create=True)
        except SkuConflict as error:
            raise HTTPException(409, str(error)) from error
        return saved(version, item.sku, "criado")

    def existing(sku: str) -> tuple[str, bool, dict]:
        code = normalise_sku(sku) or ""
        state = store().sku_state(code)
        if state is None:
            raise HTTPException(404, f"SKU {code} não encontrado no cadastro.")
        return code, *state

    @router.put("/skus/{sku}", dependencies=editor)
    def update(sku: str, item: SkuFields, user: dict = Depends(current_user)):
        code, _, current = existing(sku)
        rows = validated_rows(code, item, current)
        try:
            version = store().save_sku(code, rows, user["email"], create=False)
        except SkuNotFound as error:
            raise HTTPException(404, str(error)) from error
        return saved(version, code, "editado")

    def toggle(sku: str, active: bool, user: dict) -> dict:
        code, *_ = existing(sku)
        try:
            version = store().set_active(code, active, user["email"])
        except SkuNotFound as error:
            raise HTTPException(404, str(error)) from error
        except SkuConflict as error:
            raise HTTPException(409, str(error)) from error
        return saved(version, code, "reativado" if active else "excluido")

    @router.post("/skus/{sku}/excluir", dependencies=editor)
    def delete(sku: str, user: dict = Depends(current_user)):
        """Exclusão lógica: o SKU sai dos cálculos; casos, decisões e execuções que o citam ficam como estão."""
        return toggle(sku, False, user)

    @router.post("/skus/{sku}/reativar", dependencies=editor)
    def reactivate(sku: str, user: dict = Depends(current_user)):
        return toggle(sku, True, user)

    return router
