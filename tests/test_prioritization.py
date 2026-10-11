from pathlib import Path
from caderno_inteligente.indicators import build_sku_indicators
from caderno_inteligente.ingestion import load_workbook
from caderno_inteligente.prioritization import load_weights, prioritize
from caderno_inteligente.rules import evaluate_rules, load_rule_thresholds
from caderno_inteligente.transformations import normalise_dataset

SOURCE = Path("data/source/Base de Dados - Caderno Inteligente.xlsm")

def _ranking():
    data = normalise_dataset(load_workbook(SOURCE))
    indicators = build_sku_indicators(data)
    issues = evaluate_rules(indicators, load_rule_thresholds())
    return prioritize(issues, load_weights(), indicators)

def test_ranking_is_transparent_and_complete():
    ranking = _ranking()
    assert ranking["priority"].tolist() == list(range(1, len(ranking) + 1))
    assert ranking["attention_score"].is_monotonic_decreasing
    assert ranking["reasons"].map(bool).all()
    assert ranking["evidence"].map(bool).all()
    assert ranking["disclaimer"].str.contains("não é solução ótima").all()

def test_confidence_is_reduced_when_sellout_is_missing():
    ranking = _ranking()
    low_confidence = ranking.loc[ranking.confidence == "baixa"]
    assert len(low_confidence) == 20
    assert low_confidence.confidence_reason.str.contains("Sell-out não observado").all()

def test_score_equals_sum_of_configured_rule_weights():
    ranking = _ranking()
    weights = load_weights()
    first = ranking.iloc[0]
    assert first.attention_score == sum(weights[item["code"]] for item in first.reasons)

def test_ranking_exposes_operational_context_without_changing_sku_granularity():
    ranking = _ranking()
    expected_columns = {
        "critical_date",
        "critical_date_reason",
        "operational_gap_quantity",
        "projected_stock_quantity",
        "first_promised_date",
        "first_production_completion",
        "sell_in_quantity",
        "sell_out_quantity",
        "sell_in_minus_sell_out_quantity",
        "forecast_quantity",
        "analysis_scope",
        "missing_data",
    }
    assert expected_columns.issubset(ranking.columns)
    assert ranking["sku"].is_unique
    assert ranking["analysis_scope"].eq("SKU global").all()
    assert ranking["operational_gap_quantity"].ge(0).all()


# ---------------------------------------------------------------- Etapa 16.3: faixa de urgência e valor em risco

import random

import pandas as pd

from caderno_inteligente.impact import load_impact_settings
from caderno_inteligente.prioritization import CONTEXT_COLUMNS, IMPACT_COLUMNS

SETTINGS = load_impact_settings()
CALC = {"demand_to_cover": 0.0, "carteira_in_window": 0.0, "current_stock": 0.0, "open_production_quantity": 0.0}
WEIGHTS = {"A": 10, "B": 3}


def _synthetic(skus):
    """skus: {sku: (códigos, ABC do cadastro)}."""
    issues = pd.DataFrame([{"sku": sku, "product": f"P {sku}", "family": "F", "code": code, "description": code, "severity": "alta",
                            "values_used": {}, "data_origin": []} for sku, (codes, _) in skus.items() for code in codes])
    indicators = pd.DataFrame([{"SKU": sku, "abc_curve": abc, **{column: None for column in CONTEXT_COLUMNS}} for sku, (_, abc) in skus.items()])
    return issues, indicators


def _plan(sku, **overrides):
    plan = {"sku": sku, "reference_date": "2026-09-01", "discontinued": False, "early_shortfall": False, "antecipation": False, "reductions": False,
            "affected_orders": [], "planned_orders": [], "op_adjustments": [], "signals": [], "calculation": dict(CALC)}
    plan.update(overrides)
    return plan


def _alloc(sku, *uncovered):
    orders = [{"order": f"PV-{sku}-{i}", "client": f"KA-0{i + 1}", "rank": i + 1, "quantity": units, "uncovered_at_promise": units}
              for i, units in enumerate(uncovered)]
    return {"sku": sku, "orders": orders, "uncovered_units_at_promise": float(sum(uncovered))}


def _assert_value_order_within_tier(rows):
    for first, second in zip(rows, rows[1:]):
        if first["urgency_tier"] == second["urgency_tier"]:
            a, b = first["value_at_risk"]["weighted"], second["value_at_risk"]["weighted"]
            assert b is None or (a is not None and a >= b), (first["sku"], second["sku"])


def test_without_impact_order_is_the_signal_score():
    issues, indicators = _synthetic({"S1": (["B"], "A"), "S2": (["A", "B"], "B"), "S3": (["A"], "C"), "S0": (["B"], "C")})
    ranking = prioritize(issues, WEIGHTS, indicators)
    assert ranking["sku"].tolist() == ["S2", "S3", "S0", "S1"]
    assert not set(IMPACT_COLUMNS) & set(ranking.columns)
    assert ranking["disclaimer"].str.contains("regras configuradas").all()


def test_impact_orders_by_tier_then_value_then_score():
    issues, indicators = _synthetic({"HIGH_SCORE": (["A", "B"], "A"), "BIG": (["B"], "B"), "SMALL": (["B"], "C"),
                                     "T2": (["A", "B"], "A"), "NOORDER": (["B"], " a ")})
    plans = {sku: _plan(sku) for sku in ("HIGH_SCORE", "BIG", "SMALL", "NOORDER")}
    plans["T2"] = _plan("T2", antecipation=True)
    allocation = {"skus": {"HIGH_SCORE": _alloc("HIGH_SCORE", 5), "BIG": _alloc("BIG", 50, 10), "SMALL": _alloc("SMALL", 1), "T2": _alloc("T2", 0)}}
    impact = {"plans": plans, "allocation": allocation, "prices": {sku: 10.0 for sku in plans}, "abc": {"BIG": {"abc_measured": "A"}}, "settings": SETTINGS}
    ranking = prioritize(issues, WEIGHTS, indicators, impact=impact)
    assert ranking["sku"].tolist() == ["BIG", "HIGH_SCORE", "SMALL", "T2", "NOORDER"]
    assert ranking["priority"].tolist() == [1, 2, 3, 4, 5]
    rows = ranking.set_index("sku")
    assert rows.loc["BIG", "value_at_risk"]["observed"] == 600.0 and rows.loc["BIG", "urgency_label"] == "Pedido confirmado sem cobertura"
    assert rows.loc["BIG", "priority_reason"] == "Pedido confirmado sem cobertura · R$ 600 em risco (KA-01, KA-02)"
    assert rows.loc["BIG", "abc_measured"] == "A" and rows.loc["SMALL", "abc_measured"] is None  # sem venda na janela: ausente, não "C"
    assert rows.loc["NOORDER", "abc_registry"] == "A"
    # sem entrada na alocação (sem pedido aberto): descoberto observado zero, com a alocação como base
    assert rows.loc["NOORDER", "value_at_risk"]["observed"] == 0.0 and rows.loc["NOORDER", "value_at_risk"]["observed_basis"] == "alocacao"
    assert rows.loc["T2", "urgency_tier"] == 2 and rows.loc["NOORDER", "urgency_tier"] == 4
    assert rows.loc["BIG", "urgency_nature"] == "observado" and rows.loc["T2", "urgency_reason"]
    assert all(isinstance(value["nature"], dict) for value in ranking["value_at_risk"])
    assert ranking["disclaimer"].str.contains("não decide a ordem").all()


def test_discontinued_never_ahead_of_active_with_larger_observed_value():
    # CI-0047 descontinuado, com mais sinais e demanda prevista: só o observado conta para ele
    issues, indicators = _synthetic({"CI-0047": (["A", "B"], "C"), "ACTIVE": (["B"], "A")})
    plans = {"CI-0047": _plan("CI-0047", discontinued=True, calculation={**CALC, "demand_to_cover": 900.0}), "ACTIVE": _plan("ACTIVE")}
    allocation = {"skus": {"CI-0047": _alloc("CI-0047", 10), "ACTIVE": _alloc("ACTIVE", 11)}}
    impact = {"plans": plans, "allocation": allocation, "prices": {"CI-0047": 10.0, "ACTIVE": 10.0}, "abc": {}, "settings": SETTINGS}
    ranking = prioritize(issues, WEIGHTS, indicators, impact=impact)
    assert ranking["sku"].tolist() == ["ACTIVE", "CI-0047"]
    discontinued = ranking.iloc[1]["value_at_risk"]
    assert discontinued["estimated"] is None and "descontinuação" in discontinued["missing_reason"]


def test_property_order_never_contradicts_weighted_value_within_tier():
    rng = random.Random(16)
    for _ in range(20):
        skus = {f"CI-{i:04d}": (rng.sample(["A", "B"], rng.randint(1, 2)), "A") for i in range(15)}
        issues, indicators = _synthetic(skus)
        plans, allocation, prices = {}, {"skus": {}}, {}
        for sku in skus:
            plans[sku] = _plan(sku, antecipation=rng.random() < 0.3, discontinued=rng.random() < 0.2,
                               calculation={**CALC, "demand_to_cover": float(rng.randint(0, 300))})
            if rng.random() < 0.8:
                allocation["skus"][sku] = _alloc(sku, *(float(rng.choice([0, rng.randint(1, 100)])) for _ in range(rng.randint(1, 3))))
            prices[sku] = rng.choice([None, float(rng.randint(1, 50))])
        impact = {"plans": plans, "allocation": allocation, "prices": prices, "abc": {}, "settings": SETTINGS}
        ranking = prioritize(issues, WEIGHTS, indicators, impact=impact)
        assert ranking["urgency_tier"].is_monotonic_increasing
        _assert_value_order_within_tier(ranking.to_dict("records"))


def test_real_base_queue_has_tier_value_and_measured_abc():
    import backend.main as main
    _, _, indicators, issues, ranking, _ = main.pipeline()
    rows = ranking.to_dict("records")
    assert rows and all(row["urgency_tier"] in (1, 2, 3, 4) and isinstance(row["value_at_risk"], dict) and "abc_measured" in row for row in rows)
    assert all(row["value_at_risk"]["nature"] == {"observed": "observado", "estimated": "estimado", "excess": "calculado"} for row in rows)
    assert ranking["urgency_tier"].is_monotonic_increasing
    _assert_value_order_within_tier(rows)
    # CI-0047 (descontinuado) nunca à frente de SKU ativo da mesma faixa com valor observado maior
    discontinued = next(row for row in rows if row["sku"] == "CI-0047")
    for row in rows:
        if row["urgency_tier"] == discontinued["urgency_tier"] and (row["value_at_risk"]["observed"] or 0) > (discontinued["value_at_risk"]["observed"] or 0):
            assert row["priority"] < discontinued["priority"], row["sku"]
    # faixa 1 lidera; os dois maiores valores ponderados da base vêm primeiro
    assert rows[0]["urgency_tier"] == 1 and {row["sku"] for row in rows[:2]} == {"CI-0004", "CI-0041"}
    # sem impact, a ordem continua sendo a da pontuação de sinais
    legacy = prioritize(issues, main.load_weights(), indicators)
    assert list(zip(legacy["attention_score"], legacy["sku"])) == sorted(zip(legacy["attention_score"], legacy["sku"]), key=lambda pair: (-pair[0], pair[1]))
