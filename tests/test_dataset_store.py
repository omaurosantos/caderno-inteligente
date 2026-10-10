import re
from pathlib import Path

import pandas as pd
import pytest

from caderno_inteligente.dataset_store import (
    SHEET_TABLES,
    Database,
    DatasetStore,
    DatasetStoreError,
    SkuConflict,
    SkuNotFound,
    apply_sku_rows,
    decode_frame,
    encode_frame,
    sku_rows,
)
from caderno_inteligente.ingestion import load_workbook
from caderno_inteligente.transformations import normalise_dataset
from caderno_inteligente.validation import validate_dataset

SOURCE = Path("data/source/Base de Dados - Caderno Inteligente.xlsm")
FIELDS = {"produto": "Caderno Teste", "familia": "Clássico", "curva_abc": "B", "lead_time_dias": 12, "lote_minimo": 200,
          "estoque_atual": 300, "estoque_seguranca_dias": 7, "venda_media_dia": 10.0}


@pytest.fixture(scope="module")
def workbook():
    return load_workbook(SOURCE)


@pytest.fixture
def store(tmp_path, workbook):
    result = DatasetStore(Database(sqlite_path=tmp_path / "dataset.db"))
    result.import_dataset(workbook)
    return result


def test_database_returns_exactly_the_frames_the_workbook_gives(store, workbook):
    loaded = store.load_dataset()
    assert list(loaded) == list(workbook)
    for sheet, frame in workbook.items():
        pd.testing.assert_frame_equal(loaded[sheet], frame, check_exact=True)


def test_values_keep_their_type_inside_text_columns():
    frame = pd.DataFrame({"Mês": ["jan/25", pd.Timestamp("2025-02-01"), None], "Qtd": [1.5, float("nan"), 3.0]})
    columns, rows = encode_frame(frame)
    assert rows[1]["Mês"] == {"$datetime": "2025-02-01T00:00:00"} and rows[1]["Qtd"] is None
    pd.testing.assert_frame_equal(decode_frame(columns, rows), frame)


def test_integer_column_with_a_missing_value_becomes_numeric_instead_of_failing():
    frame = decode_frame([["Lote", "int64"]], [{"Lote": 10}, {"Lote": None}])
    assert frame["Lote"].isna().tolist() == [False, True]


def test_second_import_requires_replace_and_bumps_the_version(store, workbook):
    with pytest.raises(DatasetStoreError, match="--replace"):
        store.import_dataset(workbook)
    assert store.version() == 1
    assert store.import_dataset(workbook, replace=True) == 2


def test_empty_database_explains_how_to_import(tmp_path):
    empty = DatasetStore(Database(sqlite_path=tmp_path / "empty.db"))
    assert empty.is_empty()
    with pytest.raises(DatasetStoreError, match="import_workbook"):
        empty.load_dataset()


def test_created_sku_reaches_the_three_registry_sheets_and_keeps_the_base_valid(store):
    rows = sku_rows("CI-9001", FIELDS)
    preview = apply_sku_rows(store.load_dataset(), "CI-9001", rows)
    assert validate_dataset(normalise_dataset(preview))["errors"] == []
    assert store.save_sku("CI-9001", rows, "pcp@exemplo.com", create=True) == 2
    loaded = store.load_dataset()
    product = loaded["Produtos"].set_index("SKU").loc["CI-9001"]
    assert (product["Produto"], product["Família"], product["Estoque atual"], product["Cobertura (dias)"], product["Status"]) == ("Caderno Teste", "Clássico", 300, 30, "Ativo")
    assert loaded["Estoque_Atual"].set_index("SKU").loc["CI-9001", "Demanda média mensal"] == 300
    assert loaded["Lead_Times"].set_index("SKU").loc["CI-9001", "Lote mínimo"] == 200
    assert loaded["Produtos"]["Lead time (dias)"].dtype == "int64"
    with pytest.raises(SkuConflict):
        store.save_sku("CI-9001", rows, "pcp@exemplo.com", create=True)
    [item] = [item for item in store.list_skus() if item["sku"] == "CI-9001"]
    assert item["ativo"] and item["atualizado_por"] == "pcp@exemplo.com"


def test_editing_preserves_columns_the_form_does_not_manage(store):
    active, current = store.sku_state("CI-0001")
    assert active and current["Produtos"]["Coleção/Versão"] == "Linha Essencial"
    store.save_sku("CI-0001", sku_rows("CI-0001", {**FIELDS, "produto": "Caderno A5 Azul"}, current), "pcp@exemplo.com", create=False)
    product = store.load_dataset()["Produtos"].set_index("SKU").loc["CI-0001"]
    assert (product["Coleção/Versão"], product["Lead time (dias)"]) == ("Linha Essencial", 12)
    with pytest.raises(SkuNotFound):
        store.save_sku("NAO-EXISTE", sku_rows("NAO-EXISTE", FIELDS), "pcp@exemplo.com", create=False)


def test_logical_delete_hides_the_sku_from_every_sheet_and_reactivation_restores_it(store, workbook):
    before = store.load_dataset()
    assert store.set_active("CI-0001", False, "pcp@exemplo.com") == 2
    hidden = store.load_dataset()
    for sheet, frame in hidden.items():
        if "SKU" in frame:
            assert "CI-0001" not in set(frame["SKU"]), sheet
    assert len(hidden["Vendas_24m"]) < len(before["Vendas_24m"])
    assert validate_dataset(normalise_dataset(hidden))["errors"] == []
    with pytest.raises(SkuConflict):
        store.set_active("CI-0001", False, "pcp@exemplo.com")
    assert [item["ativo"] for item in store.list_skus() if item["sku"] == "CI-0001"] == [False]
    store.set_active("CI-0001", True, "pcp@exemplo.com")
    for sheet, frame in workbook.items():
        pd.testing.assert_frame_equal(store.load_dataset()[sheet], frame)


def test_every_change_is_logged_with_user_and_action(store):
    store.save_sku("CI-9001", sku_rows("CI-9001", FIELDS), "a@exemplo.com", create=True)
    store.set_active("CI-9001", False, "b@exemplo.com")
    with store.db.transaction() as cursor:
        log = cursor.execute("select sku, action, user_email from sku_changes order by id").fetchall()
    assert log == [{"sku": "CI-9001", "action": "criado", "user_email": "a@exemplo.com"},
                   {"sku": "CI-9001", "action": "excluido", "user_email": "b@exemplo.com"}]


def test_migration_creates_one_table_per_sheet_with_rls():
    sql = Path("supabase/migrations/004_dataset_and_auth.sql").read_text(encoding="utf-8").lower()
    for table in (*SHEET_TABLES.values(), "dataset_sheets", "dataset_version", "sku_changes", "app_users"):
        assert re.search(rf"create table if not exists public\.{table}\b", sql), table
        assert f"alter table public.{table} enable row level security" in sql, table
    assert "active boolean not null default true" in sql
