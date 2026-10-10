"""Cria um usuário com login (fase 3) ou troca a senha de um existente. Não há cadastro público pela tela.

A senha é pedida no terminal (sem eco) ou lida de CI_USER_PASSWORD, nunca de um argumento.

    python scripts/create_user.py --email pcp@exemplo.com --name "Ana PCP"             # SQLite local
    python scripts/create_user.py --email pcp@exemplo.com --name "Ana PCP" --postgres  # DATABASE_URL
    python scripts/create_user.py --email pcp@exemplo.com --reset-password --postgres
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from caderno_inteligente.auth import MIN_PASSWORD_LENGTH, UserStore  # noqa: E402
from scripts.import_workbook import DEFAULT_SQLITE, build_database  # noqa: E402


def read_password() -> str:
    password = os.getenv("CI_USER_PASSWORD")
    if password:
        return password
    first = getpass.getpass(f"Senha (mínimo {MIN_PASSWORD_LENGTH} caracteres): ")
    if first != getpass.getpass("Repita a senha: "):
        raise SystemExit("As senhas não conferem.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--reset-password", action="store_true", help="troca a senha de um usuário existente")
    parser.add_argument("--postgres", action="store_true", help="grava no PostgreSQL da DATABASE_URL")
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE, help="arquivo SQLite local (sem --postgres)")
    args = parser.parse_args(argv)

    users = UserStore(build_database(args.postgres, args.sqlite))
    try:
        if args.reset_password:
            users.set_password(args.email, read_password())
            print(f"Senha atualizada para {args.email.strip().lower()}.")
        else:
            users.create_user(args.email, args.name, read_password())
            print(f"Usuário {args.email.strip().lower()} criado.")
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
