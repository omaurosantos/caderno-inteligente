import pytest
from fastapi.testclient import TestClient

import backend.main as main

client = TestClient(main.app)


@pytest.fixture(scope="module")
def body():
    response = client.get("/api/partner-stock-projection")
    assert response.status_code == 200
    return response.json()


def test_returns_every_pair_with_errors_for_sell_in_and_sell_out(body):
    assert body["total"] == body["pairs"] == 50
    assert set(body["errors"]) == {"sell_out", "sell_in"}
    assert body["errors"]["sell_in"]["wape"] is not None and body["errors"]["sell_in"]["bias"] is not None
    item = body["items"][0]
    assert set(item["errors"]) == {"sell_out", "sell_in"}
    assert set(item["scenarios"]) == {"with_replenishment", "without_replenishment"}
    assert body["requires_human_review"] is True and body["nature"] == "estimado"


def test_filters_by_partner_and_sku_keep_aggregate_errors(body):
    item = body["items"][0]
    filtered = client.get("/api/partner-stock-projection", params={"partner": item["partner"], "sku": item["sku"]}).json()
    assert filtered["total"] == 1 and filtered["items"][0] == item
    assert filtered["errors"] == body["errors"]


def test_unknown_codes_return_404_and_malformed_input_422():
    assert client.get("/api/partner-stock-projection", params={"partner": "KA-99"}).status_code == 404
    assert client.get("/api/partner-stock-projection", params={"sku": "CI-9999"}).status_code == 404
    assert client.get("/api/partner-stock-projection", params={"partner": "<script>"}).status_code == 422
    assert client.get("/api/partner-stock-projection", params={"sku": "x" * 41}).status_code == 422


def test_projection_never_changes_official_outputs():
    before = (client.get("/api/forecasts").json(), client.get("/api/commercial-recommendations?limit=50").json())
    client.get("/api/partner-stock-projection")
    assert (client.get("/api/forecasts").json(), client.get("/api/commercial-recommendations?limit=50").json()) == before


def test_route_is_read_only():
    assert client.post("/api/partner-stock-projection").status_code == 405
