"""Etapa 15.3: projeção diária datada, ordens planejadas, ajustes de OP e ação do SKU."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.main as main
from caderno_inteligente.recommendations import build_operational_recommendation
from caderno_inteligente.rules import evaluate_rules
from caderno_inteligente.supply_plan import (
    DEFAULT_SETTINGS,
    _validate_settings,
    affected_orders,
    build_sku_plan,
    daily_demand,
    decide,
)

SETTINGS = _validate_settings(dict(DEFAULT_SETTINGS))  # planejamento em 14/09/2026, janela de 4 semanas
REFERENCE = date(2026, 9, 14)
MONTHS = ["2026-09-01", "2026-10-01", "2026-11-01"]


def _indicator(**changes):
    base = {"SKU": "X", "current_stock": 1000.0, "minimum_lot": 100.0, "lead_time_days": 14, "reference_daily_demand": 10.0,
            "safety_stock_days": 5, "Status": "Ativo", "has_sell_out": True, "backlog_order_quantity": 0, "production_order_quantity": 0}
    return {**base, **changes}


def _forecast(values=(300.0, 300.0, 300.0)):
    return {"status": "ok", "forecast_months": MONTHS[: len(values)], "forecast_values": list(values), "forecast_next_month": values[0], "forecast_confidence": "alta"}


def _order(name, quantity, promised, client="KA-01"):
    return {"order": name, "client": client, "quantity": float(quantity), "promised_date": date.fromisoformat(promised)}


def _ops(*rows):
    columns = ["Ordem", "SKU", "Quantidade", "Início previsto", "Conclusão prevista", "Status"]
    return pd.DataFrame([{"Ordem": name, "SKU": "X", "Quantidade": quantity, "Início previsto": pd.Timestamp(start),
                          "Conclusão prevista": pd.Timestamp(finish), "Status": status} for name, quantity, start, finish, status in rows], columns=columns)


def _plan(indicator=None, forecast=None, orders=(), ops=None):
    return build_sku_plan(_indicator() if indicator is None else indicator, _forecast() if forecast is None else forecast, list(orders),
                          _ops() if ops is None else ops, SETTINGS)


# ------------------------------------------------------------------------------------------ demanda e projeção


def test_daily_demand_puts_orders_on_their_date_and_spreads_only_the_forecast_beyond_the_backlog():
    orders = [_order("A", 200, "2026-09-10"), _order("B", 100, "2026-10-05")]
    carteira, extra = daily_demand(_forecast((300.0, 400.0)), orders, REFERENCE, date(2026, 10, 31))
    assert carteira[REFERENCE] == 200  # vencido entra no primeiro dia
    assert carteira[date(2026, 10, 5)] == 100
    september = sum(value for day, value in extra.items() if day.month == 9)
    october = sum(value for day, value in extra.items() if day.month == 10)
    assert september == pytest.approx(0.0)  # 17/30 de 300 = 170 < 200 da carteira de setembro: nada além da carteira
    assert october == pytest.approx(300.0)  # 400 previstos − 100 da carteira de outubro
    assert min(extra) >= REFERENCE  # nada antes da data de planejamento


def test_affected_orders_give_backlog_priority_and_report_the_delay():
    orders = [_order("A", 80, "2026-09-16"), _order("B", 50, "2026-09-20")]
    late = affected_orders(100.0, orders, {date(2026, 9, 25): 100.0}, REFERENCE, date(2026, 11, 30))
    assert [item["order"] for item in late] == ["B"]
    assert late[0]["expected_date"] == "2026-09-25" and late[0]["delay_days"] == 5


# ------------------------------------------------------------------------------------------ ações


def test_shortfall_before_any_new_supply_is_an_unavoidable_delay_with_the_affected_orders():
    plan = _plan(_indicator(current_stock=100.0), orders=[_order("PED-1", 500, "2026-09-18")])
    action, secondary = decide(plan, set())
    assert action == "atraso_inevitavel" and "produzir" in secondary
    assert "PROJECTED_SHORTFALL" in plan["signals"]
    assert [item["order"] for item in plan["affected_orders"]] == ["PED-1"]
    first = plan["planned_orders"][0]
    assert first["due_date"] == "2026-09-28" and first["release_date"] == "2026-09-14" and first["urgent"]  # chega no lead time


def test_not_started_op_that_can_still_arrive_is_anticipated():
    ops = _ops(("OP-1", 600, "2026-09-25", "2026-09-30", "Planejada"))  # 5 dias de produção: iniciada hoje, conclui 19/09
    plan = _plan(_indicator(current_stock=100.0, lead_time_days=30), orders=[_order("PED-1", 400, "2026-09-22")], ops=ops)
    assert decide(plan, set())[0] == "antecipar_op"
    anticipation = next(item for item in plan["op_adjustments"] if item["adjustment"] == "antecipar")
    assert anticipation["order"] == "OP-1" and anticipation["suggested_finish"] <= "2026-09-22"


def test_op_already_in_production_is_not_anticipated():
    ops = _ops(("OP-1", 600, "2026-09-10", "2026-09-30", "Em produção"))
    plan = _plan(_indicator(current_stock=100.0, lead_time_days=30), orders=[_order("PED-1", 400, "2026-09-22")], ops=ops)
    assert decide(plan, set())[0] == "atraso_inevitavel"
    assert not any(item["adjustment"] == "antecipar" for item in plan["op_adjustments"])


def test_discontinued_product_plans_only_the_backlog_and_cancels_unneeded_op():
    ops = _ops(("OP-9", 1600, "2026-09-16", "2026-10-07", "Liberada"))
    plan = _plan(_indicator(current_stock=118.0, Status="Descontinuando", minimum_lot=400.0), orders=[_order("PED-1", 85, "2026-09-29")], ops=ops)
    assert plan["planned_orders"] == [] and plan["first_shortfall_date"] is None  # a previsão não entra para descontinuado
    assert plan["op_adjustments"][0]["adjustment"] == "cancelar" and plan["op_adjustments"][0]["suggested_quantity"] == 0
    assert "OP_FOR_DISCONTINUED" in plan["signals"] and decide(plan, set())[0] == "rever_op"


def test_discontinued_product_keeps_the_lot_needed_for_the_backlog():
    ops = _ops(("OP-9", 400, "2026-09-16", "2026-10-12", "Planejada"))
    plan = _plan(_indicator(current_stock=67.0, Status="Descontinuando", minimum_lot=200.0), orders=[_order("PED-1", 130, "2026-10-05")], ops=ops)
    adjustment = next(item for item in plan["op_adjustments"] if item["adjustment"] in ("reduzir", "cancelar"))
    assert adjustment["adjustment"] == "reduzir" and adjustment["suggested_quantity"] == 200  # 63 un. faltantes → 1 lote


def test_op_far_above_the_need_is_reduced_without_creating_shortfall_in_the_window():
    ops = _ops(("OP-2", 2000, "2026-09-17", "2026-09-29", "Planejada"))
    plan = _plan(_indicator(current_stock=300.0, reference_daily_demand=9.0, minimum_lot=500.0), forecast=_forecast((270.0, 270.0, 270.0)), ops=ops)
    reduction = next(item for item in plan["op_adjustments"] if item["cause"] == "excesso_projetado")
    assert reduction["adjustment"] == "reduzir" and reduction["suggested_quantity"] % 500 == 0 and reduction["suggested_quantity"] < 2000
    assert reduction["projected_after_arrival"] - (2000 - reduction["suggested_quantity"]) >= reduction["kept_for_window"]
    assert "PROJECTED_EXCESS" in plan["signals"] and decide(plan, set())[0] == "rever_op"


def test_planned_order_is_not_created_when_an_op_already_arrives_in_the_cover_window():
    ops = _ops(("OP-3", 2000, "2026-09-17", "2026-09-30", "Em produção"))
    plan = _plan(_indicator(current_stock=40.0, lead_time_days=12), ops=ops)  # abaixo da segurança até a OP chegar
    assert all(order["due_date"] > "2026-09-30" for order in plan["planned_orders"])


def test_future_need_is_a_non_urgent_order_with_release_date_and_lot_rounding():
    plan = _plan(_indicator(current_stock=700.0, minimum_lot=250.0))
    assert decide(plan, set())[0] == "produzir"
    first = plan["planned_orders"][0]
    assert not first["urgent"] and first["release_date"] > SETTINGS["reference_date"] and first["quantity"] % 250 == 0
    assert plan["suggested_quantity"] == 0 and plan["planned_quantity_horizon"] > 0


def test_no_action_only_when_the_projection_stays_above_safety():
    plan = _plan(_indicator(current_stock=5000.0), forecast=_forecast((300.0, 300.0, 300.0)))
    assert decide(plan, set()) == ("sem_acao_necessaria", [])
    assert not any(week["shortfall"] or week["below_safety"] for week in plan["projection"])


def test_recommendation_uses_the_plan_and_keeps_the_contract_fields():
    plan = _plan(_indicator(current_stock=100.0), orders=[_order("PED-1", 500, "2026-09-18")])
    recommendation = build_operational_recommendation(_indicator(current_stock=100.0), _forecast(), [], plan)
    assert recommendation["action"] == "atraso_inevitavel" and recommendation["requires_human_review"] is True
    assert recommendation["suggested_quantity"] == plan["suggested_quantity"] > 0
    assert {"demand_to_cover", "safety_stock_quantity", "current_stock", "open_production_quantity", "raw_quantity"} <= set(recommendation["calculation"])
    assert recommendation["affected_orders"][0]["order"] == "PED-1" and recommendation["rationale"]
    future = build_operational_recommendation(_indicator(current_stock=700.0), _forecast(), [], _plan(_indicator(current_stock=700.0)))
    assert future["action"] == "produzir" and future["action_label"].startswith("Produzir (liberar a partir de")


def test_insufficient_forecast_still_means_investigate_even_with_a_plan():
    plan = _plan()
    recommendation = build_operational_recommendation(_indicator(), {"status": "insufficient_data", "forecast_next_month": None}, [], plan)
    assert recommendation["action"] == "investigar_dados" and recommendation["suggested_quantity"] is None


def test_rules_emit_the_plan_signals():
    plan = _plan(_indicator(current_stock=100.0), orders=[_order("PED-1", 500, "2026-09-18")])
    indicators = pd.DataFrame([{**_indicator(current_stock=100.0), "Produto": "P", "family": "F", "coverage_days_calculated": 10, "safety_stock_days": 5,
                                "capacity_occupation_average": 0.5, "capacity_available_average": 100, "has_sell_out": True, "sell_out_partner_count": 1,
                                "sell_out_visibility": "parcial", "first_promised_date": pd.NaT, "first_production_completion": pd.NaT}])
    issues = evaluate_rules(indicators, None, {"X": plan})
    shortfall = issues[issues["code"] == "PROJECTED_SHORTFALL"].iloc[0]
    assert shortfall["values_used"]["affected_orders"] == ["PED-1"]


def test_plan_exposes_the_supply_series_and_open_orders_without_recalculating():
    ops = _ops(("OP-1", 300, "2026-09-01", "2026-09-10", "Em produção"), ("OP-2", 200, "2026-09-20", "2026-09-30", "Planejada"))
    orders = [_order("PED-2", 50, "2026-09-20", client="KA-02"), _order("PED-1", 500, "2026-09-18")]
    plan = _plan(_indicator(current_stock=100.0), orders=orders, ops=ops)
    events = plan["supply_events"]
    assert [event for event in events if event["source"] != "planejada"] == [
        {"date": "2026-09-14", "quantity": 100.0, "source": "estoque", "ref": None},
        {"date": "2026-09-14", "quantity": 300.0, "source": "op", "ref": "OP-1"},  # vencida entra na referência, como em _receipts
        {"date": "2026-09-30", "quantity": 200.0, "source": "op", "ref": "OP-2"},
    ]
    planned = [event for event in events if event["source"] == "planejada"]
    assert [(event["date"], event["quantity"]) for event in planned] == [(order["due_date"], order["quantity"]) for order in plan["planned_orders"]]
    assert [event["date"] for event in events] == sorted(event["date"] for event in events)
    assert plan["open_orders"] == [
        {"order": "PED-2", "client": "KA-02", "quantity": 50.0, "promised_date": "2026-09-20"},
        {"order": "PED-1", "client": "KA-01", "quantity": 500.0, "promised_date": "2026-09-18"},
    ]
    assert all(event["source"] != "estoque" for event in _plan(_indicator(current_stock=0.0))["supply_events"])  # sem estoque, sem evento


# ------------------------------------------------------------------------------------------ base real


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def test_top_of_the_queue_never_says_no_action(client):
    top = [item for item in client.get("/api/forecasts").json() if item["priority"] is not None and item["priority"] <= 10]
    assert len(top) == 10 and all(item["operational_recommendation"]["action"] != "sem_acao_necessaria" for item in top)


def test_ci_0041_reports_the_late_orders_and_a_dated_plan(client):
    recommendation = client.get("/api/priorities/CI-0041").json()["operational_recommendation"]
    assert recommendation["action"] == "atraso_inevitavel"
    assert {item["order"] for item in recommendation["affected_orders"]} == {"PED-041-1", "PED-041-2"}
    assert recommendation["earliest_arrival"] == "2026-10-05" and recommendation["projection"][0]["week_start"] == "2026-09-14"


def test_discontinued_and_oversized_ops_are_flagged_on_the_base(client):
    adjusted = {}
    for sku in ("CI-0050", "CI-0047", "CI-0048", "CI-0009"):
        recommendation = client.get(f"/api/priorities/{sku}").json()["operational_recommendation"]
        adjusted[sku] = {item["order"]: item["adjustment"] for item in recommendation["op_adjustments"]}
    assert adjusted["CI-0050"] == {"OP-7849": "cancelar"}
    assert adjusted["CI-0047"] == {"OP-7846": "reduzir"}
    assert adjusted["CI-0048"]["OP-7847"] == "reduzir" and adjusted["CI-0009"]["OP-7808"] == "reduzir"


def test_supply_series_do_not_change_the_plan_on_the_base(client):
    """Etapa 16.2 (C1): os campos novos são aditivos; quantidade e ação seguem iguais ao snapshot "antes" da Etapa 16."""
    import json
    from pathlib import Path

    before = {item["sku"]: item for item in json.loads((Path(main.ROOT) / "docs/etapa-16/antes.json").read_text(encoding="utf-8"))["skus"]}
    plans = main._cached()[2]
    assert set(before) <= set(plans)
    for sku, item in before.items():
        plan = plans[sku]
        assert plan["suggested_quantity"] == item["suggested_quantity"], sku
        # As séries reproduzem a carteira afetada do plano: mesmas chegadas (OP + planejada), mesmos pedidos.
        receipts = {}
        for event in plan["supply_events"]:
            if event["source"] != "estoque":
                day = date.fromisoformat(event["date"])
                receipts[day] = receipts.get(day, 0.0) + event["quantity"]
        orders = [{**order, "promised_date": None if order["promised_date"] is None else date.fromisoformat(order["promised_date"])} for order in plan["open_orders"]]
        assert affected_orders(plan["current_stock"], orders, receipts, REFERENCE, date.fromisoformat(plan["horizon_end"])) == plan["affected_orders"], sku
        assert sum(event["quantity"] for event in plan["supply_events"] if event["source"] == "planejada") == plan["planned_quantity_horizon"], sku
