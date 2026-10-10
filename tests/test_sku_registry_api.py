"""Fase 3 pela API: base no banco, login e cadastro de SKU (criar, editar, excluir de forma lógica, reativar)."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from caderno_inteligente.ingestion import load_workbook

EMAIL, PASSWORD = "pcp@exemplo.com", "senha-forte-123"
NEW_SKU = {"sku": "ci-9001", "produto": "Caderno Teste", "familia": "Clássico", "curva_abc": "B", "lead_time_dias": 12,
           "lote_minimo": 200, "estoque_atual": 300, "estoque_seguranca_dias": 7, "venda_media_dia": 10.0}
FIELDS = {key: value for key, value in NEW_SKU.items() if key != "sku"}


def _isolate(monkeypatch, tmp_path, source: str):
    for name in ("RUNS_DB", "CASES_DB", "FEEDBACK_DB", "DATASET_DB"):
        monkeypatch.setattr(main, name, tmp_path / f"{name.lower()}.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_SOURCE", source)
    monkeypatch.setenv("AUTH_SECRET", "segredo-de-teste-" + "x" * 30)
    monkeypatch.setenv("AUTH_REQUIRED", "true")  # Testes do login; o modo liberado (padrão atual) tem testes próprios.
    # Each test has its own database starting at version 1: never reuse a pipeline built from another one.
    monkeypatch.setattr(main, "_pipeline_cache", None)
    monkeypatch.setattr(main, "_version_seen", None)
    main.user_store().create_user(EMAIL, "Ana PCP", PASSWORD)
    return TestClient(main.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    client = _isolate(monkeypatch, tmp_path, "banco")
    main.dataset_store().import_dataset(load_workbook(main.SOURCE))
    return client


@pytest.fixture
def spreadsheet_client(tmp_path, monkeypatch):
    return _isolate(monkeypatch, tmp_path, "planilha")


def _auth(client) -> dict:
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _skus(client) -> set[str]:
    return {item["sku"] for item in client.get("/api/forecasts").json()}


def test_login_issues_a_token_that_identifies_the_user(client):
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": "errada-123456"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    headers = _auth(client)
    assert client.get("/api/auth/me", headers=headers).json() == {"user": {"email": EMAIL, "name": "Ana PCP"}}
    assert client.get("/api/auth/me", headers={"Authorization": headers["Authorization"][:-3] + "abc"}).status_code == 401


def test_repeated_login_failures_are_throttled(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "alvo@exemplo.com", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "alvo@exemplo.com", "password": "x"}).status_code == 429


def test_system_reports_the_data_source(client):
    body = client.get("/api/system").json()
    assert (body["data_source"], body["auth_enabled"], body["auth_required"]) == ("banco", True, True)


def test_database_source_gives_the_same_ranking_as_the_spreadsheet(client, monkeypatch):
    from_database = client.get("/api/priorities").json()
    monkeypatch.setenv("DATA_SOURCE", "planilha")
    assert client.get("/api/priorities").json() == from_database


def test_sku_registry_full_cycle(client):
    headers = _auth(client)
    assert client.post("/api/skus", json=NEW_SKU).status_code == 401
    created = client.post("/api/skus", json=NEW_SKU, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json() == {"sku": "CI-9001", "version": 2}
    assert "CI-9001" in _skus(client)
    detail = client.get("/api/priorities/CI-9001").json()
    assert detail["indicator"]["Produto"] == "Caderno Teste"

    assert client.post("/api/skus", json=NEW_SKU, headers=headers).status_code == 409
    edited = client.put("/api/skus/CI-9001", json={**FIELDS, "produto": "Caderno Teste 2"}, headers=headers)
    assert edited.status_code == 200 and edited.json()["version"] == 3
    assert client.get("/api/priorities/CI-9001").json()["indicator"]["Produto"] == "Caderno Teste 2"

    registry = client.get("/api/skus/cadastro", headers=headers).json()
    assert registry["editable"] and "Clássico" in registry["families"]
    [item] = [row for row in registry["items"] if row["sku"] == "CI-9001"]
    assert (item["produto"], item["ativo"], item["atualizado_por"]) == ("Caderno Teste 2", True, EMAIL)

    assert client.post("/api/skus/CI-9001/excluir", headers=headers).status_code == 200
    assert "CI-9001" not in _skus(client)
    assert client.get("/api/priorities/CI-9001").status_code == 404
    assert client.post("/api/cases", json={"sku": "CI-9001"}).status_code == 422
    assert client.post("/api/skus/CI-9001/excluir", headers=headers).status_code == 409
    assert client.post("/api/skus", json=NEW_SKU, headers=headers).status_code == 409

    assert client.post("/api/skus/CI-9001/reativar", headers=headers).status_code == 200
    assert "CI-9001" in _skus(client)


def test_deleting_an_existing_sku_keeps_its_decision_history(client):
    headers = _auth(client)
    assert client.post("/api/feedback", json={"sku": "CI-0014", "action": "aceita"}).status_code == 200
    assert client.post("/api/skus/CI-0014/excluir", headers=headers).status_code == 200
    assert "CI-0014" not in _skus(client)
    assert [item["sku"] for item in client.get("/api/feedback").json()] == ["CI-0014"]


@pytest.mark.parametrize("body, message", [
    ({**NEW_SKU, "estoque_atual": -1}, "greater than or equal"),
    ({**NEW_SKU, "familia": "Inexistente"}, "Família desconhecida"),
    ({**NEW_SKU, "sku": "com espaço"}, "letras, números"),
    ({**NEW_SKU, "curva_abc": "D"}, "'A', 'B' or 'C'"),
    ({**NEW_SKU, "extra": 1}, "Extra inputs"),
])
def test_invalid_sku_is_rejected_before_anything_is_saved(client, body, message):
    response = client.post("/api/skus", json=body, headers=_auth(client))
    assert response.status_code == 422
    assert message in response.text
    assert main.dataset_store().version() == 1


def test_unknown_sku_cannot_be_edited_or_deleted(client):
    headers = _auth(client)
    assert client.put("/api/skus/NAO-EXISTE", json=FIELDS, headers=headers).status_code == 404
    assert client.post("/api/skus/NAO-EXISTE/excluir", headers=headers).status_code == 404


def test_read_only_publication_blocks_registry_writes(client, monkeypatch):
    headers = _auth(client)
    monkeypatch.setattr(main, "SETTINGS", replace(main.SETTINGS, write_enabled=False))
    assert client.post("/api/skus", json=NEW_SKU, headers=headers).status_code == 403


def test_spreadsheet_mode_refuses_registry_writes(spreadsheet_client):
    headers = _auth(spreadsheet_client)
    response = spreadsheet_client.post("/api/skus", json=NEW_SKU, headers=headers)
    assert response.status_code == 409 and "DATA_SOURCE=banco" in response.json()["detail"]
    assert spreadsheet_client.get("/api/skus/cadastro", headers=headers).json()["editable"] is False


def test_production_without_auth_secret_disables_login(client, monkeypatch):
    monkeypatch.delenv("AUTH_SECRET")
    monkeypatch.setattr(main, "SETTINGS", replace(main.SETTINGS, environment="production"))
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 503
    assert client.get("/api/system").json()["auth_enabled"] is False


def test_cors_allows_the_authorization_header():
    client = TestClient(main.app)
    origin = main.SETTINGS.cors_origins[0]
    response = client.options("/api/skus/CI-0001/excluir", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                                    "Access-Control-Request-Headers": "authorization,content-type"})
    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_without_auth_required_registry_is_open_and_changes_are_logged_as_sem_login(client, monkeypatch):
    monkeypatch.delenv("AUTH_REQUIRED")
    assert client.get("/api/system").json()["auth_required"] is False
    assert client.get("/api/skus/cadastro").status_code == 200
    assert client.post("/api/skus", json=NEW_SKU).status_code == 201
    assert client.put("/api/skus/CI-9001", json=FIELDS).status_code == 200
    assert client.post("/api/skus/CI-9001/excluir").status_code == 200
    assert client.post("/api/skus/CI-9001/reativar").status_code == 200
    [item] = [row for row in client.get("/api/skus/cadastro").json()["items"] if row["sku"] == "CI-9001"]
    assert item["atualizado_por"] == "sem-login"


def test_open_registry_still_respects_read_only_and_spreadsheet_mode(client, monkeypatch):
    monkeypatch.delenv("AUTH_REQUIRED")
    monkeypatch.setattr(main, "SETTINGS", replace(main.SETTINGS, write_enabled=False))
    assert client.post("/api/skus", json=NEW_SKU).status_code == 403
    monkeypatch.setattr(main, "SETTINGS", replace(main.SETTINGS, write_enabled=True))
    monkeypatch.setenv("DATA_SOURCE", "planilha")
    assert client.post("/api/skus", json=NEW_SKU).status_code == 409
