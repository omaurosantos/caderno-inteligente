"""Etapa 16.2: rotas da alocação sugerida e ligação com o detalhe do SKU, a fila e o Início."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.allocation import create_allocation_router
from backend.main import app

CONTESTED = {"CI-0004", "CI-0005", "CI-0027", "CI-0041", "CI-0049"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_allocation_lists_contested_skus_with_order_and_reason(client):
    payload = client.get("/api/allocation").json()
    assert payload["requires_human_review"] is True
    assert any("não reserva estoque" in text for text in payload["limitations"])
    assert {"reference_date", "total", "items", "totals", "field_nature", "limitations"} <= set(payload)
    assert payload["total"] == len(payload["items"])
    assert all(item["has_shortfall"] or item["contested"] for item in payload["items"])
    assert set(payload["totals"]["contested_skus"]) == CONTESTED
    contested = {item["sku"]: item for item in payload["items"] if item["contested"]}
    assert set(contested) == CONTESTED
    for item in contested.values():
        assert [order["rank"] for order in item["orders"]] == list(range(1, len(item["orders"]) + 1))
        assert all(order["reason"] for order in item["orders"]) and item["decision_text"]


def test_allocation_filters_and_invalid_filters(client):
    one = client.get("/api/allocation", params={"sku": "CI-0041"}).json()
    assert [item["sku"] for item in one["items"]] == ["CI-0041"]
    by_client = client.get("/api/allocation", params={"cliente": "KA-05"}).json()
    assert by_client["items"] and all("KA-05" in item["clients"] for item in by_client["items"])
    region = client.get("/api/allocation/regions").json()["regions"][0]["region"]
    by_region = client.get("/api/allocation", params={"regiao": region}).json()
    assert by_region["items"] and all(any(order["region"] == region for order in item["orders"]) for item in by_region["items"])
    assert client.get("/api/allocation", params={"sku": "CI-9999"}).status_code == 404
    assert client.get("/api/allocation", params={"regiao": "Marte"}).status_code == 422
    assert client.get("/api/allocation", params={"cliente": "KA-99"}).status_code == 422


def test_allocation_regions_sum_to_total(client):
    payload = client.get("/api/allocation/regions").json()
    assert payload["requires_human_review"] is True and payload["limitations"]
    assert sum(row["uncovered_units"] for row in payload["regions"]) == pytest.approx(payload["totals"]["uncovered_units"])


def test_invalid_allocation_configuration_is_422():
    def broken():
        raise ValueError("chave desconhecida")
    local = FastAPI()
    local.include_router(create_allocation_router(broken))
    response = TestClient(local).get("/api/allocation/regions")
    assert response.status_code == 422 and "Alocação bloqueada" in response.json()["detail"]


def test_sku_detail_carries_allocation_and_partner_lever(client):
    data = client.get("/api/priorities/CI-0041").json()
    assert data["allocation"]["contested"] is True
    assert {"KA-02", "KA-05"} <= set(data["allocation"]["clients"])
    assert data["challenge_action"]["code"] == "priorizar_parceiro"
    assert data["challenge_action"]["lever"] == "alocar" and data["challenge_action"]["decide_by"]


def test_forecasts_labels_follow_the_lever_table(client):
    items = client.get("/api/forecasts").json()
    by_sku = {item["sku"]: item for item in items}
    for sku in CONTESTED:
        assert by_sku[sku]["challenge_action"]["code"] == "priorizar_parceiro"
    for sku in ("CI-0047", "CI-0050"):
        assert by_sku[sku]["challenge_action"]["code"] not in ("priorizar_producao", "produzir")
    for item in items:
        action = item["challenge_action"]
        if action["lever"] not in (None, "nenhuma"):
            assert action["decide_by"], item["sku"]


def test_no_label_exceeds_40_percent_of_the_queue(client):
    items = client.get("/api/forecasts").json()
    counts: dict[str, int] = {}
    for item in items:
        counts[item["challenge_action"]["code"]] = counts.get(item["challenge_action"]["code"], 0) + 1
    assert max(counts.values()) <= 0.4 * len(items), counts


def test_overview_exposes_decisions_today(client):
    block = client.get("/api/overview").json()["decisions_today"]
    assert {"window_end", "count", "items"} <= set(block)
    assert block["count"] == len(block["items"])
    assert all(item["decide_by"] <= block["window_end"] and item["lever"] != "nenhuma" for item in block["items"])
