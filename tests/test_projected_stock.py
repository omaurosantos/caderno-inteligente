import pandas as pd
from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app, production_plan, supply_plans
from caderno_inteligente.production_plan import build_production_plan
from caderno_inteligente.projected_stock import build_projected_stock


def _week(start: str, base: float, with_plan: float) -> dict:
    return {"week_start": start, "min_projected": base, "min_projected_with_plan": with_plan, "shortfall": base < 0, "shortfall_with_plan": with_plan < 0}


def _plan(sku: str, weeks: list[dict], safety: float = 10.0) -> dict:
    first = next((week["week_start"] for week in weeks if week["shortfall"]), None)
    return {
        "sku": sku, "reference_date": "2026-09-14", "horizon_end": "2027-02-28", "decision_window_end": "2026-10-12",
        "lead_time_days": 14, "safety_stock_quantity": safety, "first_shortfall_date": first, "projection": weeks,
        "planned_orders": [], "suggested_quantity": 0.0, "planned_quantity_horizon": 0.0,
    }


def _build(plans: dict, statuses: dict | None = None) -> dict:
    indicators = pd.DataFrame({"SKU": list(plans), "Produto": [f"Produto {sku}" for sku in plans], "family": ["F1"] * len(plans)})
    forecasts = pd.DataFrame({"sku": list(plans), "status": [(statuses or {}).get(sku, "ok") for sku in plans]})
    return build_projected_stock(plans, indicators, forecasts, build_production_plan(plans, indicators, forecasts))


def test_counts_shortfall_and_safety_with_and_without_the_planned_orders():
    result = _build({
        # Falta sem novas ordens que o plano resolve.
        "A": _plan("A", [_week("2026-09-14", 50, 50), _week("2026-09-21", -5, 20)]),
        # Falta que sobra mesmo com o plano (chega antes de qualquer reposição nova).
        "B": _plan("B", [_week("2026-09-14", -1, -1), _week("2026-09-21", -30, 15)]),
        # Abaixo da segurança sem nunca faltar.
        "C": _plan("C", [_week("2026-09-14", 5, 5), _week("2026-09-21", 40, 40)]),
        # Folgado.
        "D": _plan("D", [_week("2026-09-14", 80, 80)]),
    })
    assert result["skus_evaluated"] == 4
    assert result["without_new_orders"] == {"shortfall_sku_count": 2, "below_safety_sku_count": 3, "first_shortfall_week": "2026-09-14"}
    assert result["with_planned_orders"] == {"shortfall_sku_count": 1, "below_safety_sku_count": 2, "first_shortfall_week": "2026-09-14"}
    assert [(item["sku"], item["first_shortfall_week"], item["shortfall_with_plan"]) for item in result["shortfall_skus"]] == [
        ("B", "2026-09-14", True), ("A", "2026-09-21", False),
    ]
    assert result["shortfall_skus"][0]["product"] == "Produto B"
    assert result["requires_human_review"] is True and result["horizon_end"] == "2027-02-28"


def test_weekly_counts_skus_in_shortfall_per_week_in_both_readings():
    result = _build({
        "A": _plan("A", [_week("2026-09-14", 50, 50), _week("2026-09-21", -5, 20), _week("2026-09-28", 30, 30)]),
        "B": _plan("B", [_week("2026-09-14", -1, -1), _week("2026-09-21", -30, 15), _week("2026-09-28", -2, 4)]),
        # Horizonte mais curto: a semana 28/09 fica fora para não parecer melhora.
        "C": _plan("C", [_week("2026-09-14", 5, 5), _week("2026-09-21", 40, 40)]),
    })
    assert result["weekly"] == [
        {"week_start": "2026-09-14", "shortfall_sku_count": 1, "shortfall_with_plan_sku_count": 1},
        {"week_start": "2026-09-21", "shortfall_sku_count": 2, "shortfall_with_plan_sku_count": 0},
    ]


def test_weekly_is_empty_without_evaluated_skus():
    result = _build({"A": _plan("A", [_week("2026-09-14", -5, -5)])}, {"A": "insufficient_data"})
    assert result["weekly"] == []


def test_sku_without_forecast_is_excluded_not_counted_as_safe():
    result = _build({
        "A": _plan("A", [_week("2026-09-14", -5, -5)]),
        "B": _plan("B", [_week("2026-09-14", 80, 80)]),
    }, {"B": "insufficient_data"})
    assert result["skus_evaluated"] == 1
    assert result["excluded_skus"] == [{"sku": "B", "reason": "sem_previsao"}]
    assert result["without_new_orders"]["shortfall_sku_count"] == 1


def test_no_forecast_at_all_returns_empty_readings_not_zero_risk_dates():
    result = _build({"A": _plan("A", [_week("2026-09-14", -5, -5)])}, {"A": "insufficient_data"})
    assert result["skus_evaluated"] == 0 and result["reference_date"] is None
    assert result["without_new_orders"] == {"shortfall_sku_count": 0, "below_safety_sku_count": 0, "first_shortfall_week": None}


def test_overview_aggregates_the_real_supply_plan_without_new_calculation():
    payload = TestClient(app).get("/api/overview").json()["projected_stock"]
    plans = supply_plans()
    assert payload["skus_evaluated"] + len(payload["excluded_skus"]) == len(plans)
    assert payload["without_new_orders"]["shortfall_sku_count"] == len(payload["shortfall_skus"])
    # Mesmas datas do plano de suprimento: a primeira falta de cada SKU vem de first_shortfall_date.
    for item in payload["shortfall_skus"]:
        assert item["first_shortfall_date"] == plans[item["sku"]]["first_shortfall_date"]
    # O plano só acrescenta entradas: com ele, nunca há mais falta nem mais SKUs abaixo da segurança.
    for key in ("shortfall_sku_count", "below_safety_sku_count"):
        assert payload["with_planned_orders"][key] <= payload["without_new_orders"][key] <= payload["skus_evaluated"]
    assert payload["with_planned_orders"]["shortfall_sku_count"] == sum(item["shortfall_with_plan"] for item in payload["shortfall_skus"])
    # Série semanal: nenhuma semana tem mais SKUs em falta que o total no horizonte; com o plano, nunca mais que sem.
    assert payload["weekly"], "a série semanal vem com a base real"
    for week in payload["weekly"]:
        assert week["shortfall_with_plan_sku_count"] <= week["shortfall_sku_count"] <= payload["without_new_orders"]["shortfall_sku_count"]
    # A primeira semana é a da data de referência (segunda-feira igual ou anterior a ela).
    assert payload["weekly"][0]["week_start"] <= payload["reference_date"]
    # Produção planejada: os mesmos totais do gráfico da fila.
    total = production_plan()["total"]
    assert payload["planned_production"]["urgent_total"] == total["urgent_total"]
    assert payload["planned_production"]["horizon_total"] == total["horizon_total"]


def test_failure_in_the_aggregation_keeps_the_rest_of_the_overview(monkeypatch):
    def broken():
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(main, "projected_stock", broken)
    response = TestClient(app).get("/api/overview")
    assert response.status_code == 200
    assert response.json()["projected_stock"] is None
    assert response.json()["rupture_sku_count"] >= 0
