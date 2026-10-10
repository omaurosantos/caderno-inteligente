"""Login próprio (fase 3): usuários no mesmo banco, senha com scrypt e token assinado (JWT HS256).

Só a biblioteca padrão: o token aceita apenas HS256, compara a assinatura em tempo constante e expira.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from .dataset_store import Database

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD_LENGTH = 10
MIN_SECRET_LENGTH = 32
_HEADER = {"alg": "HS256", "typ": "JWT"}


class InvalidToken(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ----------------------------------------------------------------- senhas

def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(_unb64(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, _unb64(digest))


# ----------------------------------------------------------------- tokens

def _sign(secret: str, message: bytes) -> bytes:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()


def issue_token(secret: str, email: str, name: str, ttl_seconds: int, now: float | None = None) -> tuple[str, int]:
    issued = int(time.time() if now is None else now)
    expires = issued + ttl_seconds
    claims = {"sub": email, "name": name, "iat": issued, "exp": expires}
    signing_input = f"{_b64(json.dumps(_HEADER, separators=(',', ':')).encode())}.{_b64(json.dumps(claims, separators=(',', ':')).encode())}"
    return f"{signing_input}.{_b64(_sign(secret, signing_input.encode('ascii')))}", expires


def read_token(secret: str, token: str, now: float | None = None) -> dict[str, Any]:
    try:
        header_b64, claims_b64, signature_b64 = token.split(".")
        header = json.loads(_unb64(header_b64))
        claims = json.loads(_unb64(claims_b64))
        signature = _unb64(signature_b64)
    except (ValueError, TypeError) as error:
        raise InvalidToken("Token malformado") from error
    if header != _HEADER:
        raise InvalidToken("Algoritmo de token não aceito")
    if not hmac.compare_digest(signature, _sign(secret, f"{header_b64}.{claims_b64}".encode("ascii"))):
        raise InvalidToken("Assinatura inválida")
    if not isinstance(claims, dict) or not isinstance(claims.get("sub"), str) or not isinstance(claims.get("exp"), int):
        raise InvalidToken("Token sem usuário ou validade")
    if claims["exp"] <= (time.time() if now is None else now):
        raise InvalidToken("Sessão expirada")
    return claims


# ---------------------------------------------------------------- usuários

def normalise_email(email: str) -> str:
    return email.strip().lower()


class UserStore:
    def __init__(self, database: Database):
        self.db = database

    def create_user(self, email: str, name: str, password: str) -> None:
        email = normalise_email(email)
        if "@" not in email:
            raise ValueError("E-mail inválido")
        with self.db.transaction() as cursor:
            if cursor.execute("select 1 as found from app_users where email = ?", (email,)).fetchone():
                raise ValueError(f"Usuário {email} já existe")
            cursor.execute("insert into app_users(email, name, password_hash) values (?, ?, ?)", (email, name.strip(), hash_password(password)))

    def set_password(self, email: str, password: str) -> None:
        email = normalise_email(email)
        with self.db.transaction() as cursor:
            if not cursor.execute("select 1 as found from app_users where email = ?", (email,)).fetchone():
                raise ValueError(f"Usuário {email} não existe")
            cursor.execute("update app_users set password_hash = ? where email = ?", (hash_password(password), email))

    def authenticate(self, email: str, password: str) -> dict[str, str] | None:
        with self.db.transaction() as cursor:
            row = cursor.execute("select email, name, password_hash, active from app_users where email = ?", (normalise_email(email),)).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)  # Mesmo custo para e-mail inexistente.
            return None
        if not verify_password(password, row["password_hash"]) or not row["active"]:
            return None
        return {"email": row["email"], "name": row["name"]}

    def active_user(self, email: str) -> dict[str, str] | None:
        with self.db.transaction() as cursor:
            row = cursor.execute("select email, name, active from app_users where email = ?", (normalise_email(email),)).fetchone()
        return None if row is None or not row["active"] else {"email": row["email"], "name": row["name"]}


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
