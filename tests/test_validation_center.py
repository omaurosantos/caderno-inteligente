import copy
from pathlib import Path

import pandas as pd

from caderno_inteligente.action_labels import DEFAULT_SETTINGS as CHALLENGE_DEFAULTS
from caderno_inteligente.validation_center import (
    _check,
    _commercial_label,
    evaluate_forecasts,
    evaluate_frozen_cases,
    load_validation_config,
    process_comparison,
    safe_behavior_checks,
    summarize_analysis_time,
)

CONFIG = Path(__file__).resolve().parents[1] / "config/validation_center.json"


def _sales(values, sku="SKU-1"):
    return pd.DataFrame({"Mês": pd.date_range("2025-01-01", periods=len(values), freq="MS"), "SKU": sku, "Quantidade faturada": values})


def _forecast(sku="SKU-1", model="moving_average_3", status="ok"):
    return pd.DataFrame([{"sku": sku, "model": model, "status": status, "reference_month": "2026-08-01"}])


def test_baseline_is_explicit_and_does_not_change_selection():
    sales = _sales([100.0] * 12 + [100, 100, 100, 100, 100, 100])
    result = evaluate_forecasts(sales, _forecast())
    roles = {row["model"]: row["role"] for row in result["models"]}
    assert roles["naive_last"] == "baseline"
    assert result["items"][0]["selected_model"] == "moving_average_3"
    # Tie with the baseline is reported as not beating it, never hidden as a win.
    assert result["items"][0]["outcome"] == "nao_superou"
    assert result["did_not_beat_baseline_skus"] == 1


def test_zero_demand_holdout_is_not_comparable_and_excluded_from_weighted_wape():
    sales = _sales([50.0] * 9 + [0.0, 0.0, 0.0])
    result = evaluate_forecasts(sales, _forecast())
    assert result["items"][0]["selected_wape"] is None
    assert result["items"][0]["outcome"] == "nao_comparavel"
    assert result["zero_demand_holdout_skus"] == 1
    selected = next(row for row in result["models"] if row["model"] == "selected")
    assert selected["weighted_wape"] is None and selected["median_wape"] is None


def test_insufficient_forecasts_are_counted_not_scored():
    result = evaluate_forecasts(_sales([10.0] * 4), _forecast(status="insufficient_data", model=None))
    assert result["eligible_skus"] == 0
    assert result["insufficient_skus"] == 1
    assert result["insufficient_sku_list"] == ["SKU-1"]


def test_analysis_time_does_not_claim_gain_with_small_sample():
    rows = [("A", "aceita", "", "", "nao_utilizado", 30, "2026-10-01"), ("B", "aceita", "", "", "nao_utilizado", None, "2026-10-01")]
    result = summarize_analysis_time(rows, minimum_sample=20)
    assert result["records_with_minutes"] == 1
    assert result["total_minutes"] == 30
    assert result["comparison_allowed"] is False
    assert "Nenhum ganho" in result["note"]
    sufficient = summarize_analysis_time([rows[0]] * 20, minimum_sample=20)
    assert sufficient["comparison_allowed"] is True


def test_absent_minutes_are_null_not_zero():
    result = summarize_analysis_time([], minimum_sample=20)
    assert result["total_minutes"] is None and result["average_minutes_per_decision"] is None


def test_process_comparison_separates_informed_recalculated_and_target():
    config = load_validation_config(CONFIG)
    evaluation = {"models": [{"model": "selected", "weighted_wape": 0.07}]}
    rows = {row["id"]: row for row in process_comparison(config, evaluation, summarize_analysis_time([], 20))}
    assert rows["analysis_time"]["informed"] == {"value": 22, "unit": "horas/semana", "nature": "informado", "source": rows["analysis_time"]["informed"]["source"]}
    assert rows["analysis_time"]["target"]["value"] == 8 and rows["analysis_time"]["target"]["nature"] == "meta"
    assert rows["forecast_error"]["recalculated"]["value"] == 0.07
    assert rows["forecast_error"]["recalculated"]["comparable"] is False
    for key in ("on_time_orders", "plan_adherence"):
        assert rows[key]["recalculated"]["value"] is None
        assert rows[key]["recalculated"]["nature"] == "recalculado"


def test_check_operators():
    assert _check("signals", {"includes": ["A"], "excludes": ["B"]}, ["A"])["passed"]
    assert not _check("signals", {"includes": ["A"], "excludes": ["B"]}, ["A", "B"])["passed"]
    assert _check("q", {"is_null": True}, None)["passed"]
    assert not _check("q", {"equals": 0}, None)["passed"]
    assert not _check("q", {"positive": True}, None)["passed"]
    assert _check("p", {"max": 5}, 1)["passed"] and not _check("p", {"max": 5}, None)["passed"]
    assert _check("c", {"not": "alta"}, "média")["passed"]
    assert not _check("m", {"empty": True}, None)["passed"]


def _empty_context():
    return {
        "indicators": pd.DataFrame(columns=["SKU"]), "issues": pd.DataFrame(columns=["sku", "code"]),
        "ranking": pd.DataFrame(columns=["sku", "priority"]), "forecasts": pd.DataFrame(columns=["sku"]),
        "partner_items": [], "thresholds": {"excess_coverage_days": 90, "capacity_occupation_threshold": 0.9},
    }


def test_synthetic_cases_run_through_existing_rules_and_recommendation():
    config = load_validation_config(CONFIG)
    synthetic = {**config, "cases": [case for case in config["cases"] if case["origin"] == "synthetic"]}
    result = evaluate_frozen_cases(synthetic, **_empty_context(), source_sha256=config["frozen_source_sha256"])
    # 2 casos operacionais sintéticos + 11 casos dos rótulos de ação do desafio (VC-09 a VC-19) + VC-34 (alocação, liberado na 16.2)
    assert result["total"] == 14 and result["passed"] == 14 and result["pending"] == 0
    first = result["items"][0]
    assert {"RUP_LEAD_TIME", "RUP_SAFETY_STOCK", "ORDER_WITHOUT_PRODUCTION"} <= set(first["obtained"]["signals"])
    assert first["obtained"]["suggested_quantity"] == 500.0


def test_synthetic_allocation_case_puts_the_partner_with_stock_buildup_last():
    config = load_validation_config(CONFIG)
    only = {**config, "cases": [case for case in config["cases"] if case["id"] == "VC-34"]}
    item = evaluate_frozen_cases(only, **_empty_context(), source_sha256=config["frozen_source_sha256"])["items"][0]
    assert item["result"] == "passou" and item["obtained"]["ranked_clients"] == ["KA-T2", "KA-T1"]
    assert item["obtained"]["orders_with_reason"] == 2 and item["obtained"]["requires_human_review"] is True
    without_coverage = copy.deepcopy(only)
    without_coverage["cases"][0]["input"].pop("partner_coverage_days")   # sem cobertura o sinal do parceiro não vira ponto
    tie = evaluate_frozen_cases(without_coverage, **_empty_context(), source_sha256=config["frozen_source_sha256"])["items"][0]
    assert tie["obtained"]["ranked_clients"] == ["KA-T1", "KA-T2"] and tie["result"] == "falhou"   # empate total: vale o pedido


def _plan(sku="SKU-A", **extra):
    base = {"sku": sku, "reference_date": "2026-09-14", "discontinued": False, "affected_orders": [], "planned_orders": [], "op_adjustments": [],
            "early_shortfall": False, "first_shortfall_date": None, "decision_window_end": "2026-10-12", "capacity": {"status": "ok"},
            "open_orders": [], "supply_events": []}
    return {**base, **extra}


def test_base_allocation_case_reads_the_pipeline_allocation_or_rebuilds_it_from_the_plan():
    plan = _plan(open_orders=[{"order": "P1", "client": "KA-01", "quantity": 100.0, "promised_date": "2026-09-20"},
                              {"order": "P2", "client": "KA-02", "quantity": 100.0, "promised_date": "2026-09-21"}],
                 supply_events=[{"date": "2026-09-14", "quantity": 50.0, "source": "estoque", "ref": None}])
    plan.pop("affected_orders")   # sem pedidos afetados no plano, a alocação usa o FIFO por data prometida
    case = {"id": "VC-X", "title": "t", "kind": "allocation", "origin": "base", "sku": "SKU-A", "limitation": "l",
            "expected": {"contested": True, "ranked_clients": {"includes": ["KA-01", "KA-02"]}, "orders_with_reason": {"positive": True}, "requires_human_review": True}}
    config = {**load_validation_config(CONFIG), "cases": [case]}
    rebuilt = evaluate_frozen_cases(config, **_empty_context(), source_sha256="x", plans={"SKU-A": plan})["items"][0]
    assert rebuilt["result"] == "passou" and rebuilt["obtained"]["allocation_source"].startswith("recalculada")
    given = {"requires_human_review": True, "skus": {"SKU-A": {"contested": True, "orders": [{"client": "KA-02", "reason": "r"}, {"client": "KA-01", "reason": "r"}],
                                                               "first_client": "KA-02", "last_client": "KA-01", "decision_text": "d"}}}
    piped = evaluate_frozen_cases(config, **_empty_context(), source_sha256="x", plans={"SKU-A": plan}, allocation=given)["items"][0]
    assert piped["obtained"]["allocation_source"] == "pipeline" and piped["obtained"]["ranked_clients"] == ["KA-02", "KA-01"]
    assert evaluate_frozen_cases(config, **_empty_context(), source_sha256="x")["items"][0]["result"] == "nao_encontrado"


def test_outranks_higher_value_active_compares_active_skus_of_the_same_tier():
    from caderno_inteligente.validation_center import _operational_output, _outranks_higher_value_active
    ranking = pd.DataFrame([
        {"sku": "OLD", "priority": 1, "urgency_tier": 1, "value_at_risk": {"observed": 100.0, "estimated": None}},
        {"sku": "ACT", "priority": 2, "urgency_tier": 1, "value_at_risk": {"observed": 900.0, "estimated": 50.0}},
        {"sku": "LOW", "priority": 3, "urgency_tier": 2, "value_at_risk": {"observed": 5000.0, "estimated": None}},
    ])
    plans = {"OLD": _plan("OLD", discontinued=True), "ACT": _plan("ACT"), "LOW": _plan("LOW")}
    rows = ranking.to_dict("records")
    assert _outranks_higher_value_active(rows[0], ranking, plans) is True          # ACT, ativo e de valor maior, está atrás na mesma faixa
    assert _outranks_higher_value_active(rows[0], ranking, {**plans, "ACT": _plan("ACT", discontinued=True)}) is False
    assert _outranks_higher_value_active(rows[1], ranking, plans) is False         # LOW é de outra faixa
    assert _outranks_higher_value_active(None, ranking, plans) is None
    indicator = {"minimum_lot": 100, "average_sales_per_day": 10, "safety_stock_days": 10, "current_stock": 5000, "production_order_quantity": 0,
                 "backlog_order_quantity": 0, "has_sell_out": True}
    legacy = _operational_output(indicator, {"status": "ok", "forecast_next_month": 10, "forecast_confidence": "alta"}, [], None)
    assert legacy["urgency_tier"] is None and legacy["lever"] is None and legacy["outranks_higher_value_active"] is None


def test_direct_channel_row_uses_the_api_channel_label_and_falls_back_to_the_commercial_branch():
    row = {"partner": "E-commerce", "sku": "CI-0009", "row_kind": "direct", "action": "canal_direto", "data_quality": "sufficient", "signals": []}
    channel = {"sku": "CI-0009", "suggestion": {"code": "investigar_queda", "label": "Investigar queda", "reason": "Queda."}, "signals": ["DECLINING"]}
    assert _commercial_label(row, CHALLENGE_DEFAULTS, {"E-commerce": [channel]})["code"] == "investigar"
    assert _commercial_label(row, CHALLENGE_DEFAULTS, {"E-commerce": []})["code"] == "monitorar"
    assert _commercial_label(row, CHALLENGE_DEFAULTS, None)["code"] == "monitorar"


def test_failed_and_missing_cases_are_reported_not_hidden():
    config = load_validation_config(CONFIG)
    broken = copy.deepcopy(config)
    synthetic = next(case for case in broken["cases"] if case["id"] == "VC-01")
    synthetic["expected"]["action"] = "sem_acao_necessaria"
    base_case = next(case for case in broken["cases"] if case["id"] == "VC-02")
    broken["cases"] = [synthetic, base_case]
    result = evaluate_frozen_cases(broken, **_empty_context(), source_sha256="outro-hash")
    assert [item["result"] for item in result["items"]] == ["falhou", "nao_encontrado"]
    assert result["failed"] == 1 and result["not_found"] == 1
    assert result["source_matches_frozen"] is False and result["source_note"]
    failed_check = next(check for check in result["items"][0]["checks"] if check["field"] == "action")
    assert failed_check == {"field": "action", "expected": "sem_acao_necessaria", "obtained": "produzir", "passed": False}


def test_safe_behavior_guard_rails_pass_and_detect_violation():
    forecasts = pd.DataFrame([{"sku": "X", "status": "ok", "forecast_next_month": 1.0}])
    checks = {item["id"]: item for item in safe_behavior_checks(forecasts, [{"requires_human_review": True}], [])}
    assert all(item["status"] == "aprovado" for item in checks.values())
    violated = {item["id"]: item for item in safe_behavior_checks(forecasts, [{"requires_human_review": False}], [{"estimated_stock": None, "coverage_days": 10}])}
    assert violated["human_review"]["status"] == "reprovado"
    assert violated["no_false_precision"]["status"] == "reprovado"
