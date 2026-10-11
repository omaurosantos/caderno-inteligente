import math

import pytest

from fastapi.testclient import TestClient

from backend.main import app


def test_forecast_summary_contract_covers_all_skus():
    client = TestClient(app)
    response = client.get("/api/forecasts")

    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) == client.get("/api/overview").json()["total_skus"]
    assert len({item["sku"] for item in items}) == len(items)

    for item in items:
        assert {
            "sku",
            "product",
            "family",
            "priority",
            "attention_score",
            "confidence",
            "confidence_reason",
            "forecast",
            "operational_recommendation",
        }.issubset(item)
        forecast = item["forecast"]
        recommendation = item["operational_recommendation"]
        assert recommendation["requires_human_review"] is True
        assert {
            "action",
            "action_label",
            "suggested_quantity",
            "minimum_lot",
            "capacity_status",
            "confidence",
            "confidence_reason",
        }.issubset(recommendation)
        if forecast["status"] == "ok":
            # Motor v2 (Etapa 15.1): 6 meses; os campos de 3 meses continuam somando só os 3 primeiros.
            assert len(forecast["forecast_months"]) == len(forecast["forecast_values"]) == 6
            assert forecast["forecast_total_3m"] == pytest.approx(sum(forecast["forecast_values"][:3]), abs=0.11)
        else:
            assert forecast["forecast_next_month"] is None
            assert forecast["forecast_total_3m"] is None

        quantity = recommendation["suggested_quantity"]
        minimum_lot = recommendation["minimum_lot"]
        if quantity is not None:
            assert quantity >= 0
            if quantity > 0 and minimum_lot > 0:
                assert math.isclose(quantity % minimum_lot, 0, abs_tol=1e-9)


def test_forecast_summary_preserves_official_ranking_and_score():
    client = TestClient(app)
    priorities = client.get("/api/priorities").json()
    summaries = client.get("/api/forecasts").json()
    ranked_summaries = [item for item in summaries if item["priority"] is not None]

    assert [item["sku"] for item in ranked_summaries] == [item["sku"] for item in priorities]
    assert [item["priority"] for item in ranked_summaries] == [item["priority"] for item in priorities]
    assert [item["attention_score"] for item in ranked_summaries] == [item["attention_score"] for item in priorities]
    assert all(item["priority"] is None for item in summaries[len(priorities):])


def test_forecast_items_carry_urgency_and_value_from_the_ranking():
    items = TestClient(app).get("/api/forecasts").json()
    for item in items:
        assert {"urgency_tier", "urgency_label", "value_at_risk", "abc_registry", "abc_measured", "priority_reason"} <= set(item)
        if item["priority"] is None:
            assert item["urgency_tier"] is None and item["value_at_risk"] is None
        else:
            assert item["urgency_tier"] in (1, 2, 3, 4)
            assert item["value_at_risk"]["nature"] == {"observed": "observado", "estimated": "estimado", "excess": "calculado"}
            assert item["abc_measured"] in ("A", "B", "C", None)
