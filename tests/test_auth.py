import base64
import json

import pytest

from caderno_inteligente.auth import InvalidToken, UserStore, hash_password, issue_token, read_token, verify_password
from caderno_inteligente.dataset_store import Database

SECRET = "s" * 40


def test_password_hash_is_salted_and_verifiable():
    first, second = hash_password("senha-forte-123"), hash_password("senha-forte-123")
    assert first != second and first.startswith("scrypt$")
    assert verify_password("senha-forte-123", first)
    assert not verify_password("senha-errada-123", first)
    assert not verify_password("senha-forte-123", "texto-qualquer")


def test_short_password_is_rejected():
    with pytest.raises(ValueError, match="pelo menos"):
        hash_password("curta")


def test_token_roundtrip_and_expiry():
    token, expires = issue_token(SECRET, "pcp@exemplo.com", "PCP", 3600, now=1_000)
    assert expires == 4_600
    assert read_token(SECRET, token, now=2_000)["sub"] == "pcp@exemplo.com"
    with pytest.raises(InvalidToken, match="expirada"):
        read_token(SECRET, token, now=4_600)


def _b64(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


def test_tampered_foreign_or_unsigned_tokens_are_rejected():
    token, _ = issue_token(SECRET, "pcp@exemplo.com", "PCP", 3600)
    header, claims, signature = token.split(".")
    forged_claims = _b64({"sub": "admin@exemplo.com", "name": "", "iat": 0, "exp": 9_999_999_999})
    for candidate in (
        f"{header}.{forged_claims}.{signature}",
        f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{claims}.",
        token[:-2] + "xx",
        "nao-e-token",
    ):
        with pytest.raises(InvalidToken):
            read_token(SECRET, candidate)
    with pytest.raises(InvalidToken):
        read_token("outro-segredo-" + "x" * 30, token)


def test_user_store_authenticates_only_active_users_with_the_right_password(tmp_path):
    users = UserStore(Database(sqlite_path=tmp_path / "dataset.db"))
    users.create_user(" PCP@Exemplo.com ", "Ana", "senha-forte-123")
    with pytest.raises(ValueError, match="já existe"):
        users.create_user("pcp@exemplo.com", "Ana", "senha-forte-123")
    assert users.authenticate("pcp@exemplo.com", "senha-forte-123") == {"email": "pcp@exemplo.com", "name": "Ana"}
    assert users.authenticate("pcp@exemplo.com", "senha-errada-123") is None
    assert users.authenticate("ninguem@exemplo.com", "senha-forte-123") is None
    users.set_password("pcp@exemplo.com", "outra-senha-456")
    assert users.authenticate("pcp@exemplo.com", "outra-senha-456") is not None
    with users.db.transaction() as cursor:
        cursor.execute("update app_users set active = 0")
    assert users.authenticate("pcp@exemplo.com", "outra-senha-456") is None
    assert users.active_user("pcp@exemplo.com") is None
