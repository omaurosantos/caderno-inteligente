"""Planilha no banco (fase 3): uma tabela por aba, cadastro de SKU com exclusão lógica e versão dos dados.

O banco devolve os mesmos DataFrames que `ingestion.load_workbook` lê da planilha (mesmas colunas, ordem e tipos),
então cálculos, ranking e previsão não mudam. PostgreSQL em produção (migração 004); SQLite local em `runtime/`.
"""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .ingestion import OPTIONAL_SHEETS
from .schemas import SCHEMAS

SHEET_TABLES: dict[str, str] = {
    "Produtos": "sheet_produtos",
    "Vendas_24m": "sheet_vendas_24m",
    "Estoque_Atual": "sheet_estoque_atual",
    "Carteira_Pedidos": "sheet_carteira_pedidos",
    "Ordens_Producao": "sheet_ordens_producao",
    "Capacidade_Semanal": "sheet_capacidade_semanal",
    "Sell_In": "sheet_sell_in",
    "Sell_Out": "sheet_sell_out",
    "Forecast_Comercial": "sheet_forecast_comercial",
    "Calendario_Eventos": "sheet_calendario_eventos",
    "Parceiros_Canais": "sheet_parceiros_canais",
    "Lead_Times": "sheet_lead_times",
    "Precos_Produtos": "sheet_precos_produtos",
}
assert set(SHEET_TABLES) == {*SCHEMAS, *OPTIONAL_SHEETS}

# Abas que o cadastro de SKU mantém: as que o pipeline cruza um a um com Produtos.
SKU_SHEETS = ("Produtos", "Estoque_Atual", "Lead_Times")


class DatasetStoreError(RuntimeError):
    pass


class SkuConflict(DatasetStoreError):
    pass


class SkuNotFound(DatasetStoreError):
    pass


# ----------------------------------------------------------- frame <-> rows

def normalise_sku(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return str(value).strip().upper() or None


def _encode_value(value: Any, datetime_column: bool) -> Any:
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, dict) and set(value) in ({"$datetime"}, {"$date"}):
        return value  # Já codificado (linha relida do banco).
    if isinstance(value, (pd.Timestamp, datetime)):
        iso = pd.Timestamp(value).isoformat()
        return iso if datetime_column else {"$datetime": iso}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) else float(value)
    if isinstance(value, str):
        return value
    raise DatasetStoreError(f"Tipo de valor não suportado no banco: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "$datetime" in value:
            return pd.Timestamp(value["$datetime"]).to_pydatetime()
        if "$date" in value:
            return date.fromisoformat(value["$date"])
    return value


def encode_frame(frame: pd.DataFrame) -> tuple[list[list[str]], list[dict[str, Any]]]:
    """Colunas na ordem original com o dtype, e uma linha por registro (valor ausente vira null)."""
    columns = [[str(name), str(dtype)] for name, dtype in frame.dtypes.items()]
    datetime_columns = {name for name, dtype in columns if dtype.startswith("datetime64")}
    rows = [{name: _encode_value(value, name in datetime_columns) for name, value in record.items()}
            for record in frame.astype(object).to_dict("records")]
    return columns, rows


def decode_frame(columns: list[list[str]], rows: list[dict[str, Any]]) -> pd.DataFrame:
    names = [name for name, _ in columns]
    frame = pd.DataFrame([[_decode_value(row.get(name)) for name in names] for row in rows], columns=names)
    for name, dtype in columns:
        if dtype.startswith("datetime64"):
            frame[name] = pd.to_datetime(frame[name]).astype(dtype)
        elif dtype != "object":
            try:
                frame[name] = frame[name].astype(dtype)
            except (TypeError, ValueError):
                # Ex.: coluna inteira com valor ausente em um SKU cadastrado depois; mantém número com NaN.
                frame[name] = pd.to_numeric(frame[name], errors="coerce")
        elif frame[name].isna().all():
            frame[name] = frame[name].astype(object)
    return frame


# ------------------------------------------------------- cadastro de SKU

SKU_FIELDS = ("produto", "familia", "curva_abc", "lead_time_dias", "lote_minimo", "estoque_atual", "estoque_seguranca_dias", "venda_media_dia")


def _coverage_days(stock: float, daily_sales: float) -> int:
    """Mesma unidade da planilha (dias inteiros); sem venda cadastrada, a cobertura fica 0 e a previsão decide."""
    return int(round(stock / daily_sales)) if daily_sales > 0 else 0


def sku_rows(sku: str, fields: dict[str, Any], current: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Linhas de Produtos, Estoque_Atual e Lead_Times para o SKU; colunas não cadastradas pelo formulário são preservadas."""
    current = current or {}
    stock, daily = fields["estoque_atual"], fields["venda_media_dia"]
    coverage = _coverage_days(stock, daily)
    product = {
        **current.get("Produtos", {}),
        "SKU": sku, "Produto": fields["produto"], "Família": fields["familia"], "Curva ABC": fields["curva_abc"],
        "Lead time (dias)": fields["lead_time_dias"], "Lote mínimo": fields["lote_minimo"],
        "Estoque segurança (dias)": fields["estoque_seguranca_dias"], "Estoque atual": stock,
        "Cobertura (dias)": coverage, "Venda média/dia": daily,
    }
    product.setdefault("Status", "Ativo")
    product.setdefault("Descrição completa", fields["produto"])
    stock_row = {
        **current.get("Estoque_Atual", {}),
        "SKU": sku, "Estoque atual": stock, "Cobertura dias": coverage, "Estoque segurança dias": fields["estoque_seguranca_dias"],
        "Demanda média mensal": int(round(daily * 30)),
    }
    lead_time = {**current.get("Lead_Times", {}), "SKU": sku, "Família": fields["familia"], "Lead time dias": fields["lead_time_dias"], "Lote mínimo": fields["lote_minimo"]}
    return {"Produtos": product, "Estoque_Atual": stock_row, "Lead_Times": lead_time}


def apply_sku_rows(dataset: dict[str, pd.DataFrame], sku: str, rows: dict[str, dict[str, Any]] | None) -> dict[str, pd.DataFrame]:
    """Prévia em memória da alteração (None remove o SKU de todas as abas), para validar antes de gravar."""
    result = dict(dataset)
    for sheet, frame in dataset.items():
        if "SKU" not in frame:
            continue
        keep = frame[frame["SKU"].map(normalise_sku) != sku]
        if rows is None:
            result[sheet] = keep.reset_index(drop=True)
        elif sheet in rows:
            addition = pd.DataFrame([{column: rows[sheet].get(column) for column in frame.columns}], columns=frame.columns)
            result[sheet] = pd.concat([keep, addition.astype(frame.dtypes.to_dict(), errors="ignore")], ignore_index=True)
    return result


def registry_item(row: dict[str, Any], active: bool, updated_at: Any, updated_by: str | None) -> dict[str, Any]:
    return {
        "sku": normalise_sku(row.get("SKU")), "produto": row.get("Produto"), "familia": row.get("Família"), "curva_abc": row.get("Curva ABC"),
        "lead_time_dias": row.get("Lead time (dias)"), "lote_minimo": row.get("Lote mínimo"),
        "estoque_atual": row.get("Estoque atual"), "estoque_seguranca_dias": row.get("Estoque segurança (dias)"),
        "venda_media_dia": row.get("Venda média/dia"), "ativo": bool(active),
        "atualizado_em": updated_at.isoformat() if isinstance(updated_at, (datetime, date)) else updated_at, "atualizado_por": updated_by,
    }


# ------------------------------------------------------------- database

_SQLITE_SCHEMA = [
    "create table if not exists dataset_sheets (name text primary key, table_name text not null, columns text not null, imported_at text not null default current_timestamp)",
    "create table if not exists dataset_version (id integer primary key check (id = 1), version integer not null default 0, updated_at text not null default current_timestamp)",
    "insert or ignore into dataset_version(id, version) values (1, 0)",
    "create table if not exists sku_changes (id integer primary key autoincrement, sku text not null, action text not null, user_email text not null, before text, after text, changed_at text not null default current_timestamp)",
    "create table if not exists app_users (id integer primary key autoincrement, email text not null unique, name text not null default '', password_hash text not null, active integer not null default 1, created_at text not null default current_timestamp)",
    *(f"create table if not exists {table} (id integer primary key autoincrement, position integer not null, sku text, data text not null"
      + (", active integer not null default 1, updated_at text, updated_by text, unique (sku))" if sheet == "Produtos" else ")")
      for sheet, table in SHEET_TABLES.items()),
]


class Database:
    """PostgreSQL (psycopg) ou SQLite com a mesma interface mínima: transação, placeholders e JSON."""

    def __init__(self, *, database_url: str | None = None, sqlite_path: Path | None = None):
        if bool(database_url) == bool(sqlite_path):
            raise ValueError("Informe DATABASE_URL ou o caminho do SQLite, não os dois")
        self._database_url = database_url
        self._sqlite_path = sqlite_path
        self.kind = "postgres" if database_url else "sqlite"
        if sqlite_path is not None:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            with self.transaction() as cursor:
                for statement in _SQLITE_SCHEMA:
                    cursor.execute(statement)

    def __repr__(self) -> str:
        return f"Database(kind={self.kind!r})"

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        if self._database_url:
            import psycopg
            from psycopg.rows import dict_row

            with psycopg.connect(self._database_url, autocommit=False, prepare_threshold=None, row_factory=dict_row) as connection:
                with connection.cursor() as cursor:
                    yield _Cursor(cursor, "%s")
            return
        connection = sqlite3.connect(self._sqlite_path)
        connection.row_factory = sqlite3.Row
        try:
            yield _Cursor(connection.cursor(), "?")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def json_in(self, value: Any) -> Any:
        if self.kind == "postgres":
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def json_out(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value


class _Cursor:
    """Queries are written with `?`; PostgreSQL receives `%s`."""

    def __init__(self, cursor, placeholder: str):
        self._cursor = cursor
        self._placeholder = placeholder

    def execute(self, query: str, params: tuple | list = ()) -> "_Cursor":
        self._cursor.execute(query.replace("?", self._placeholder) if self._placeholder != "?" else query, tuple(params))
        return self

    def executemany(self, query: str, rows: list[tuple]) -> None:
        self._cursor.executemany(query.replace("?", self._placeholder) if self._placeholder != "?" else query, rows)

    def fetchone(self) -> dict[str, Any] | None:
        row = self._cursor.fetchone()
        return None if row is None else dict(row)

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._cursor.fetchall()]


class DatasetStore:
    def __init__(self, database: Database):
        self.db = database

    # -------------------------------------------------------------- leitura

    def version(self) -> int:
        with self.db.transaction() as cursor:
            row = cursor.execute("select version from dataset_version where id = 1").fetchone()
            return int(row["version"]) if row else 0

    def is_empty(self) -> bool:
        with self.db.transaction() as cursor:
            return cursor.execute("select count(*) as total from dataset_sheets").fetchone()["total"] == 0

    def load_dataset(self) -> dict[str, pd.DataFrame]:
        """As abas como a planilha as entrega; SKUs inativos saem de todas as abas (o histórico de casos e decisões fica)."""
        with self.db.transaction() as cursor:
            sheets = cursor.execute("select name, table_name, columns from dataset_sheets").fetchall()
            if not sheets:
                raise DatasetStoreError("O banco ainda não tem a planilha importada. Rode scripts/import_workbook.py.")
            frames = {}
            for sheet in sheets:
                rows = cursor.execute(
                    f"select data from {sheet['table_name']} where sku is null or sku not in (select sku from sheet_produtos where active = ?) order by position, id",
                    (False,),
                ).fetchall()
                frames[sheet["name"]] = decode_frame(self.db.json_out(sheet["columns"]), [self.db.json_out(row["data"]) for row in rows])
        missing = sorted(set(SCHEMAS) - set(frames))
        if missing:
            raise DatasetStoreError(f"Abas obrigatórias ausentes no banco: {', '.join(missing)}")
        return {name: frames[name] for name in SHEET_TABLES if name in frames}

    def list_skus(self) -> list[dict[str, Any]]:
        with self.db.transaction() as cursor:
            rows = cursor.execute("select data, active, updated_at, updated_by from sheet_produtos order by sku").fetchall()
        return [registry_item(self.db.json_out(row["data"]), row["active"], row["updated_at"], row["updated_by"]) for row in rows]

    def sku_state(self, sku: str) -> tuple[bool, dict[str, dict[str, Any]]] | None:
        """(ativo, linha atual de cada aba do cadastro) ou None se o SKU não existe."""
        with self.db.transaction() as cursor:
            product = cursor.execute("select active from sheet_produtos where sku = ?", (sku,)).fetchone()
            if product is None:
                return None
            current = {}
            for sheet in SKU_SHEETS:
                row = cursor.execute(f"select data from {SHEET_TABLES[sheet]} where sku = ? order by position limit 1", (sku,)).fetchone()
                if row is not None:
                    current[sheet] = self.db.json_out(row["data"])
            return bool(product["active"]), current

    # -------------------------------------------------------------- escrita

    def import_dataset(self, dataset: dict[str, pd.DataFrame], *, replace: bool = False) -> int:
        unknown = sorted(set(dataset) - set(SHEET_TABLES))
        if unknown:
            raise DatasetStoreError(f"Abas sem tabela no banco: {', '.join(unknown)}")
        with self.db.transaction() as cursor:
            existing = cursor.execute("select count(*) as total from dataset_sheets").fetchone()["total"]
            if existing and not replace:
                raise DatasetStoreError("O banco já tem dados importados. Use --replace para substituir (o cadastro feito pela tela será perdido).")
            for table in SHEET_TABLES.values():
                cursor.execute(f"delete from {table}")
            cursor.execute("delete from dataset_sheets")
            for sheet, frame in dataset.items():
                columns, rows = encode_frame(frame)
                table = SHEET_TABLES[sheet]
                cursor.execute("insert into dataset_sheets(name, table_name, columns) values (?, ?, ?)", (sheet, table, self.db.json_in(columns)))
                cursor.executemany(f"insert into {table}(position, sku, data) values (?, ?, ?)",
                                   [(position, normalise_sku(row.get("SKU")), self.db.json_in(row)) for position, row in enumerate(rows)])
            return self._bump(cursor)

    def save_sku(self, sku: str, rows: dict[str, dict[str, Any]], user_email: str, *, create: bool) -> int:
        with self.db.transaction() as cursor:
            existing = cursor.execute("select data, active from sheet_produtos where sku = ?", (sku,)).fetchone()
            if create and existing is not None:
                state = "ativo" if existing["active"] else "inativo (reative em vez de cadastrar de novo)"
                raise SkuConflict(f"SKU {sku} já existe e está {state}.")
            if not create and existing is None:
                raise SkuNotFound(f"SKU {sku} não encontrado no cadastro.")
            columns = {row["name"]: [name for name, _ in self.db.json_out(row["columns"])]
                       for row in cursor.execute("select name, columns from dataset_sheets").fetchall()}
            for sheet, values in rows.items():
                table = SHEET_TABLES[sheet]
                data = {column: _encode_value(values.get(column), False) for column in columns.get(sheet, values)}
                updated = cursor.execute(f"select id from {table} where sku = ? order by position limit 1", (sku,)).fetchone()
                if updated is not None:
                    cursor.execute(f"update {table} set data = ? where id = ?", (self.db.json_in(data), updated["id"]))
                else:
                    position = cursor.execute(f"select coalesce(max(position), -1) + 1 as next from {table}").fetchone()["next"]
                    cursor.execute(f"insert into {table}(position, sku, data) values (?, ?, ?)", (position, sku, self.db.json_in(data)))
            cursor.execute("update sheet_produtos set updated_at = current_timestamp, updated_by = ? where sku = ?", (user_email, sku))
            self._log(cursor, sku, "criado" if create else "editado", user_email, None if existing is None else self.db.json_out(existing["data"]), rows["Produtos"])
            return self._bump(cursor)

    def set_active(self, sku: str, active: bool, user_email: str) -> int:
        with self.db.transaction() as cursor:
            existing = cursor.execute("select active from sheet_produtos where sku = ?", (sku,)).fetchone()
            if existing is None:
                raise SkuNotFound(f"SKU {sku} não encontrado no cadastro.")
            if bool(existing["active"]) == active:
                raise SkuConflict(f"SKU {sku} já está {'ativo' if active else 'inativo'}.")
            cursor.execute("update sheet_produtos set active = ?, updated_at = current_timestamp, updated_by = ? where sku = ?", (active, user_email, sku))
            self._log(cursor, sku, "reativado" if active else "excluido", user_email, {"ativo": not active}, {"ativo": active})
            return self._bump(cursor)

    def _log(self, cursor: _Cursor, sku: str, action: str, user_email: str, before: Any, after: Any) -> None:
        cursor.execute("insert into sku_changes(sku, action, user_email, before, after) values (?, ?, ?, ?, ?)",
                       (sku, action, user_email, None if before is None else self.db.json_in(before), None if after is None else self.db.json_in(after)))

    @staticmethod
    def _bump(cursor: _Cursor) -> int:
        cursor.execute("update dataset_version set version = version + 1, updated_at = current_timestamp where id = 1")
        return int(cursor.execute("select version from dataset_version where id = 1").fetchone()["version"])
