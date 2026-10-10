"""Importa a planilha XLSM para o banco (fase 3). Rodado uma vez; a planilha nunca é alterada.

Lê com a mesma ingestão da API, bloqueia se a validação de schemas.py encontrar erros e grava uma tabela por aba.

    python scripts/import_workbook.py                     # SQLite local (runtime/dataset.db)
    python scripts/import_workbook.py --postgres          # usa DATABASE_URL do ambiente (nunca impressa)
    python scripts/import_workbook.py --postgres --replace  # substitui uma importação anterior

Antes, no PostgreSQL, rode supabase/migrations/004_dataset_and_auth.sql. Depois, configure DATA_SOURCE=banco na API.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from caderno_inteligente.dataset_store import Database, DatasetStore, DatasetStoreError  # noqa: E402
from caderno_inteligente.ingestion import IngestionError, load_workbook  # noqa: E402
from caderno_inteligente.transformations import normalise_dataset  # noqa: E402
from caderno_inteligente.validation import validate_dataset  # noqa: E402

DEFAULT_SOURCE = ROOT / "data/source/Base de Dados - Caderno Inteligente.xlsm"
DEFAULT_SQLITE = ROOT / "runtime/dataset.db"


def build_database(postgres: bool, sqlite_path: Path) -> Database:
    if postgres:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL não definida no ambiente.")
        return Database(database_url=url)
    return Database(sqlite_path=sqlite_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="planilha XLSM de origem")
    parser.add_argument("--postgres", action="store_true", help="grava no PostgreSQL da DATABASE_URL")
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE, help="arquivo SQLite local (sem --postgres)")
    parser.add_argument("--replace", action="store_true", help="substitui dados já importados (perde o cadastro feito pela tela)")
    args = parser.parse_args(argv)

    try:
        dataset = load_workbook(args.source)
    except IngestionError as error:
        print(f"Planilha não lida: {error}", file=sys.stderr)
        return 1
    errors = validate_dataset(normalise_dataset(dataset))["errors"]
    if errors:
        print("A planilha tem erros de validação; nada foi gravado:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    store = DatasetStore(build_database(args.postgres, args.sqlite))
    try:
        version = store.import_dataset(dataset, replace=args.replace)
    except DatasetStoreError as error:
        print(str(error), file=sys.stderr)
        return 1
    rows = sum(len(frame) for frame in dataset.values())
    print(f"Importadas {len(dataset)} abas ({rows} linhas) para {store.db.kind}. Versão dos dados: {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
