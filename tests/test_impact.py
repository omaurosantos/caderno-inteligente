from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from caderno_inteligente import impact
from caderno_inteligente.impact import (
    abc_registry_divergence_warning, load_impact_settings, measured_abc, priority_reason, rank_key, urgency_tier, value_at_risk,
)

SETTINGS = load_impact_settings()
WORKBOOK = Path("data/source/Base de Dados - Caderno Inteligente.xlsm")


def make_projection(*lows, start="2026-08-31"):
    """Semanas consecutivas a partir de `start` com o mínimo projetado (projeção base) informado."""
    first = date.fromisoformat(start)
    return [{"week_start": (first + timedelta(weeks=index)).isoformat(), "min_projected": low} for index, low in enumerate(lows)]


def make_plan(**overrides):
    plan = {
        "sku": "CI-0001", "reference_date": "2026-09-01", "discontinued": False, "early_shortfall": False, "antecipation": False,
        "reductions": False, "affected_orders": [], "planned_orders": [], "op_adjustments": [], "signals": [],
        "calculation": {"demand_to_cover": 500.0, "carteira_in_window": 200.0, "current_stock": 100.0, "open_production_quantity": 50.0},
        "cover_end": "2026-09-30", "projection": make_projection(-60, -300),
    }
    plan.update(overrides)
    return plan


def make_allocation(*orders, uncovered_units=None):
    rows = [{"order": f"PV-{index}", "client": client, "rank": index + 1, "quantity": quantity, "uncovered_at_promise": uncovered}
            for index, (client, quantity, uncovered) in enumerate(orders)]
    total = sum(order["uncovered_at_promise"] for order in rows) if uncovered_units is None else uncovered_units
    return {"sku": "CI-0001", "orders": rows, "uncovered_units_at_promise": total}


def test_settings_defaults_and_strict_keys(tmp_path):
    assert load_impact_settings()["estimated_weight"] == 0.5
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"estimated_weight": 0.5, "extra": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_impact_settings(bad)
    bad.write_text(json.dumps({"estimated_weight": 2}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_impact_settings(bad)
    bad.write_text(json.dumps({"abc_thresholds": {"A": 0.9, "B": 0.8}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_impact_settings(bad)


def test_tier_rules():
    uncovered = make_allocation(("KA-05", 100, 40), ("KA-02", 50, 0))
    assert urgency_tier(make_plan(early_shortfall=True), uncovered, set(), SETTINGS)["tier"] == 1
    covered = make_allocation(("KA-05", 100, 0))
    assert urgency_tier(make_plan(), covered, set(), SETTINGS)["tier"] == 4
    assert urgency_tier(make_plan(antecipation=True), covered, set(), SETTINGS)["tier"] == 2
    assert urgency_tier(make_plan(early_shortfall=True), None, set(), SETTINGS)["tier"] == 2
    soon = [{"release_date": "2026-09-15", "quantity": 10}]
    late = [{"release_date": "2026-12-15", "quantity": 10}]
    assert urgency_tier(make_plan(planned_orders=soon), None, set(), SETTINGS)["tier"] == 2
    assert urgency_tier(make_plan(planned_orders=late), None, set(), SETTINGS)["tier"] == 4
    assert urgency_tier(make_plan(reductions=True), None, set(), SETTINGS)["tier"] == 3
    assert urgency_tier(make_plan(), None, {"PARTNER_STOCK_BUILDUP"}, SETTINGS)["tier"] == 3
    assert urgency_tier(make_plan(signals=["PROJECTED_EXCESS"]), None, set(), SETTINGS)["tier"] == 3
    # sem alocação, pedidos afetados do plano levam à faixa 1
    assert urgency_tier(make_plan(affected_orders=[{"quantity": 5}]), None, set(), SETTINGS)["tier"] == 1
    info = urgency_tier(make_plan(), covered, set(), SETTINGS)
    assert info["label"].startswith("Produzir no horizonte") and info["nature"]
    assert urgency_tier(make_plan(antecipation=True), covered, set(), SETTINGS)["label"] == "Ação de produção nas próximas 4 semanas"


def test_value_at_risk_components():
    allocation = make_allocation(("KA-05", 100, 40), ("KA-02", 50, 20))
    var = value_at_risk(make_plan(), allocation, 10.0, 1)
    assert var["observed"] == 600.0  # só o descoberto da alocação × preço
    # maior déficit da projeção base até cover_end = 300 un.; menos 60 un. já no observado → 240 un.
    assert var["estimated"] == 2400.0
    assert var["weighted"] == 600.0 + 0.5 * 2400.0
    assert var["excess"] is None
    assert var["nature"] == {"observed": "observado", "estimated": "estimado", "excess": "calculado"}
    assert value_at_risk(make_plan(), allocation, 10.0, 1, estimated_weight=1.0)["weighted"] == 3000.0


def test_value_at_risk_estimated_zero_when_projection_never_goes_below_zero():
    plan = make_plan(projection=make_projection(400, 120, 30))
    assert value_at_risk(plan, None, 10.0, 4)["estimated"] == 0.0


def test_forecast_only_temporary_shortfall_before_op_arrival_is_estimated():
    # CI-0006/0015/0023 na base: falta só na previsão, coberta pela OP antes de cover_end. O saldo final é positivo,
    # mas a projeção fica 80 un. abaixo de zero na segunda semana: o estimado é essa ruptura, não zero.
    plan = make_plan(early_shortfall=True, projection=make_projection(20, -80, 150, 90),
                     calculation={"demand_to_cover": 500.0, "carteira_in_window": 0.0, "current_stock": 100.0, "open_production_quantity": 600.0})
    var = value_at_risk(plan, make_allocation(("KA-05", 10, 0)), 10.0, 2)
    assert var["observed"] == 0.0 and var["estimated"] == 800.0 and var["weighted"] == 400.0
    assert priority_reason(urgency_tier(plan, make_allocation(("KA-05", 10, 0)), set(), SETTINGS), var, None).endswith("R$ 800 estimados em risco")


def test_estimated_ignores_weeks_after_cover_end_and_needs_projection():
    plan = make_plan(cover_end="2026-09-10", projection=make_projection(10, -50, -900))  # a semana de 14/09 fica fora
    assert value_at_risk(plan, None, 1.0, 4)["estimated"] == 50.0
    var = value_at_risk(make_plan(projection=[]), None, 1.0, 4)
    assert var["estimated"] is None and "projeção" in var["missing_reason"]


def test_discontinued_has_no_estimated():
    plan = make_plan(discontinued=True)
    var = value_at_risk(plan, make_allocation(("KA-05", 10, 10)), 10.0, 1)
    assert var["estimated"] is None and var["observed"] == 100.0
    assert var["weighted"] == 100.0 and "descontinuação" in var["missing_reason"]


def test_missing_price_is_none_not_zero():
    var = value_at_risk(make_plan(), make_allocation(("KA-05", 10, 10)), None, 1)
    assert all(var[key] is None for key in ("observed", "estimated", "excess", "weighted", "unit_price"))
    assert var["missing_reason"]
    assert value_at_risk(make_plan(), None, float("nan"), 1)["weighted"] is None


def test_excess_only_in_tier_three():
    adjustments = [{"adjustment": "reduzir", "quantity": 300, "suggested_quantity": 100}, {"adjustment": "cancelar", "quantity": 50, "suggested_quantity": 0},
                   {"adjustment": "antecipar", "quantity": 80, "suggested_quantity": 80}]
    plan = make_plan(op_adjustments=adjustments, reductions=True)
    assert value_at_risk(plan, None, 2.0, 3)["excess"] == 500.0
    assert value_at_risk(plan, None, 2.0, 2)["excess"] is None


def test_tier_three_without_reduction_has_no_excess_value_and_sorts_after_values():
    # Faixa 3 só por sinal (excesso projetado ou acúmulo no parceiro), sem OP a reduzir ou cancelar: ausente, não R$ 0.
    var = value_at_risk(make_plan(signals=["PROJECTED_EXCESS"]), None, 2.0, 3)
    assert var["excess"] is None and "não calculado" in var["missing_reason"]
    tier = urgency_tier(make_plan(signals=["PROJECTED_EXCESS"]), None, set(), SETTINGS)
    assert "R$ 0" not in priority_reason(tier, var, None) and "valor não calculado" in priority_reason(tier, var, None)
    rows = [{"sku": "SIGNAL", "urgency_tier": 3, "attention_score": 99, "value_at_risk": var},
            {"sku": "SMALL", "urgency_tier": 3, "attention_score": 1, "value_at_risk": {"excess": 10.0}}]
    assert [row["sku"] for row in sorted(rows, key=lambda row: rank_key(row, 0.5))] == ["SMALL", "SIGNAL"]


def test_no_allocation_uses_affected_orders_with_basis():
    var = value_at_risk(make_plan(affected_orders=[{"quantity": 30}, {"quantity": 20}]), None, 10.0, 1)
    assert var["observed"] == 500.0 and var["observed_basis"] == "pedidos_afetados"


def test_rank_key_property_within_tier():
    rng = random.Random(7)
    rows = []
    for index in range(60):
        observed = rng.choice([None, 0.0, rng.uniform(1, 1e5)])
        estimated = rng.choice([None, rng.uniform(1, 1e5)])
        present = [v for v in (observed, None if estimated is None else 0.5 * estimated) if v is not None]
        rows.append({"sku": f"CI-{index:04d}", "urgency_tier": rng.randint(1, 4), "attention_score": rng.randint(0, 50),
                     "value_at_risk": {"observed": observed, "estimated": estimated, "weighted": sum(present) if present else None}})
    ordered = sorted(rows, key=lambda row: rank_key(row, 0.5))
    assert [row["urgency_tier"] for row in ordered] == sorted(row["urgency_tier"] for row in rows)
    for first, second in zip(ordered, ordered[1:]):
        if first["urgency_tier"] != second["urgency_tier"] or first["urgency_tier"] == 3:  # faixa 3 ordena pelo excesso
            continue
        a, b = first["value_at_risk"]["weighted"], second["value_at_risk"]["weighted"]
        assert b is None or (a is not None and a >= b)  # nunca um valor maior depois de um menor; ausente por último


def test_rank_key_tiebreakers():
    base = {"urgency_tier": 1, "value_at_risk": {"observed": 100.0, "estimated": None, "weighted": 100.0}}
    rows = [{**base, "sku": "CI-0002", "attention_score": 5}, {**base, "sku": "CI-0001", "attention_score": 5}, {**base, "sku": "CI-0003", "attention_score": 9}]
    assert [row["sku"] for row in sorted(rows, key=lambda row: rank_key(row, 0.5))] == ["CI-0003", "CI-0001", "CI-0002"]


def test_rank_key_tier_3_orders_by_excess_before_signals():
    def row(sku, excess, weighted, score):
        return {"sku": sku, "urgency_tier": 3, "attention_score": score, "value_at_risk": {"observed": weighted, "estimated": None, "weighted": weighted, "excess": excess}}
    rows = [row("CI-0001", 100.0, 9e5, 50), row("CI-0002", 5000.0, 10.0, 1), row("CI-0003", None, 9e6, 99), row("CI-0004", 5000.0, 10.0, 7)]
    ordered = [item["sku"] for item in sorted(rows, key=lambda item: rank_key(item, 0.5))]
    assert ordered == ["CI-0004", "CI-0002", "CI-0001", "CI-0003"]   # excesso ↓, empate pelos sinais, excesso ausente por último


def test_priority_reason_format():
    allocation = make_allocation(("KA-02", 10, 5), ("KA-05", 10, 5))
    allocation["orders"][0]["rank"], allocation["orders"][1]["rank"] = 2, 1
    tier = urgency_tier(make_plan(), allocation, set(), SETTINGS)
    var = {"observed": 63900.0, "missing_reason": None}
    assert priority_reason(tier, var, allocation) == "Pedido confirmado sem cobertura · R$ 63,9 mil em risco (KA-05, KA-02)"
    assert "valor não calculado" in priority_reason(tier, {"observed": None, "missing_reason": "Sem preço"}, allocation)
    assert impact._brl(1_250_000) == "R$ 1,2 mi" and impact._brl(850) == "R$ 850"


def sales_fixture():
    rows = []
    for month in pd.period_range("2025-09", "2026-08", freq="M"):
        for sku, value in (("A1", 800.0), ("B1", 120.0), ("B2", 50.0), ("C1", 30.0)):
            rows.append({"Mês": month.to_timestamp(), "SKU": sku, "Valor faturado (R$)": value})
    rows.append({"Mês": pd.Timestamp("2024-09-01"), "SKU": "OLD", "Valor faturado (R$)": 99999.0})  # fora da janela
    return pd.DataFrame(rows)


def test_measured_abc_fixture():
    measured = measured_abc(sales_fixture(), SETTINGS)
    assert "OLD" not in measured
    assert {sku: info["abc_measured"] for sku, info in measured.items()} == {"A1": "A", "B1": "B", "B2": "B", "C1": "C"}
    assert measured["A1"]["revenue_12m"] == 9600.0
    assert measured["C1"]["cumulative_share"] == 1.0
    assert measured_abc(sales_fixture().iloc[0:0], SETTINGS) == {}


def test_leader_above_threshold_is_still_a():
    sales = pd.DataFrame({"Mês": [pd.Timestamp("2026-08-01")] * 2, "SKU": ["X", "Y"], "Valor faturado (R$)": [95.0, 5.0]})
    measured = measured_abc(sales, SETTINGS)
    assert measured["X"]["abc_measured"] == "A" and measured["Y"]["abc_measured"] == "C"


def test_divergence_warning_counts():
    measured = measured_abc(sales_fixture(), SETTINGS)
    products = pd.DataFrame({"SKU": ["A1", "B1", "B2", "C1", "NOSALE"], "Curva ABC": ["A", "A", "C", "C", "A"]})
    warning = abc_registry_divergence_warning(products, measured)
    assert warning["code"] == "ABC_REGISTRY_DIVERGENCE" and warning["count"] == 2
    assert [item["sku"] for item in warning["items"]] == ["B1", "B2"]  # ordem por faturamento; NOSALE sem medida não conta
    assert warning["items"][0] == {"sku": "B1", "registry": "A", "measured": "B", "revenue_12m": 1440.0}
    ok = pd.DataFrame({"SKU": ["A1"], "Curva ABC": ["A"]})
    assert abc_registry_divergence_warning(ok, measured) is None


@pytest.mark.skipif(not WORKBOOK.exists(), reason="planilha de origem ausente")
def test_real_base_divergence():
    from caderno_inteligente.ingestion import load_workbook
    data = load_workbook(WORKBOOK)
    measured = measured_abc(data["Vendas_24m"], load_impact_settings())
    warning = abc_registry_divergence_warning(data["Produtos"], measured)
    assert warning["count"] == 37
    assert measured["CI-0041"]["abc_measured"] == "A"
    assert measured["CI-0041"]["revenue_12m"] == pytest.approx(785_000, rel=0.01)
