"""Week 4 validation evidence. Read-only: never changes weights, thresholds, models or the ranking."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import pandas as pd

from caderno_inteligente.action_labels import (
    DEFAULT_SETTINGS as CHALLENGE_DEFAULTS, build_lever_context, label_channel_row, label_commercial_row, label_operational, label_partner,
)
from caderno_inteligente.allocation import DIRECT_CHANNEL_TYPE, build_allocation, load_allocation_settings
from caderno_inteligente.forecast_candidates import CANDIDATE_LABELS
from caderno_inteligente.forecast_engine_config import load_engine_config
from caderno_inteligente.forecasting import MODEL_LABELS, _MODELS, _monthly_series, _wape
from caderno_inteligente.official_forecast import build_official_forecasts, chain_windows, evaluation_origins, ratio, run_model, window_errors
from caderno_inteligente.recommendations import build_operational_recommendation
from caderno_inteligente.rules import evaluate_rules

HOLDOUT_MONTHS = 3
BASELINE_MODEL = "naive_last"
BASELINE_LABEL = "Ingênuo do último mês (baseline)"


def load_validation_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe(value: Any) -> Any:
    """Return JSON-safe values; absent stays null, never zero."""
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return None if pd.isna(value) else value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT:
        return None
    return value


def _naive_last(history: pd.Series, targets: pd.PeriodIndex) -> list[float] | None:
    if history.empty:
        return None
    return [max(0.0, float(history.iloc[-1]))] * len(targets)


# ---------------------------------------------------------------- forecast

def _aggregate(rows: list[dict], key: str) -> dict[str, Any]:
    evaluated = [row for row in rows if row["errors"].get(key) is not None]
    defined = [row["wapes"][key] for row in evaluated if row["wapes"].get(key) is not None]
    actual = sum(row["holdout_actual_total"] for row in evaluated if row["holdout_actual_total"] > 0)
    errors = sum(row["errors"][key] for row in evaluated if row["holdout_actual_total"] > 0)
    return {
        "evaluated_skus": len(evaluated),
        "wape_defined_skus": len(defined),
        "median_wape": None if not defined else round(float(median(defined)), 4),
        "weighted_wape": None if actual <= 0 else round(errors / actual, 4),
    }


def evaluate_forecasts(sales: pd.DataFrame, forecasts: pd.DataFrame, engine_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Recompute the error of every candidate and an explicit baseline, without changing the selection.

    Motor v1: holdout dos últimos 3 meses. Motor v2 (Etapa 15.1): as origens rolantes do protocolo, com o erro separado
    em meses normais e de pico, as mesmas que dão o `backtest_wape` e a confiança da previsão oficial.
    """
    engines = {row.get("engine") for row in forecasts.to_dict("records") if row.get("status") == "ok"}
    if engines == {"v2"}:
        return _evaluate_forecasts_rolling(sales, forecasts, load_engine_config() if engine_config is None else engine_config)
    by_sku = {str(row["sku"]): row for row in forecasts.to_dict("records")}
    models = {**_MODELS, BASELINE_MODEL: _naive_last}
    rows: list[dict] = []
    insufficient: list[str] = []
    for sku, forecast in sorted(by_sku.items()):
        if forecast.get("status") != "ok":
            insufficient.append(sku)
            continue
        series = _monthly_series(sales, sku)
        train, actual = series.iloc[:-HOLDOUT_MONTHS], series.iloc[-HOLDOUT_MONTHS:]
        wapes: dict[str, float | None] = {}
        errors: dict[str, float | None] = {}
        for model, function in models.items():
            predictions = function(train, actual.index)
            if predictions is None:
                wapes[model] = errors[model] = None
                continue
            errors[model] = float(sum(abs(float(a) - p) for a, p in zip(actual, predictions)))
            error = _wape(actual, predictions)
            wapes[model] = None if error is None else round(float(error), 4)
        selected = str(forecast["model"])
        selected_wape, baseline_wape = wapes.get(selected), wapes.get(BASELINE_MODEL)
        if selected_wape is None or baseline_wape is None:
            outcome = "nao_comparavel"
        elif selected_wape < baseline_wape:
            outcome = "superou"
        else:
            outcome = "nao_superou"
        rows.append({
            "sku": sku,
            "selected_model": selected,
            "selected_model_label": MODEL_LABELS.get(selected, selected),
            "selected_wape": selected_wape,
            "baseline_wape": baseline_wape,
            "candidate_wapes": {model: wapes[model] for model in _MODELS},
            "outcome": outcome,
            "holdout_actual_total": round(float(actual.sum()), 1),
            "wapes": wapes,
            "errors": {**errors, "selected": errors.get(selected)},
        })
    for row in rows:
        row["wapes"]["selected"] = row["selected_wape"]

    winners: dict[str, int] = {}
    for row in rows:
        winners[row["selected_model"]] = winners.get(row["selected_model"], 0) + 1
    model_rows = [
        {"model": model, "label": MODEL_LABELS[model], "role": "candidato", "selected_skus": winners.get(model, 0), **_aggregate(rows, model)}
        for model in _MODELS
    ]
    model_rows.append({"model": "selected", "label": "Modelo selecionado por SKU", "role": "selecionado", "selected_skus": len(rows), **_aggregate(rows, "selected")})
    model_rows.append({"model": BASELINE_MODEL, "label": BASELINE_LABEL, "role": "baseline", "selected_skus": 0, **_aggregate(rows, BASELINE_MODEL)})
    outcomes = {key: sum(row["outcome"] == key for row in rows) for key in ("superou", "nao_superou", "nao_comparavel")}
    return {
        "holdout_months": HOLDOUT_MONTHS,
        "total_skus": len(by_sku),
        "eligible_skus": len(rows),
        "insufficient_skus": len(insufficient),
        "insufficient_sku_list": insufficient,
        "zero_demand_holdout_skus": sum(row["holdout_actual_total"] <= 0 for row in rows),
        "baseline": {"model": BASELINE_MODEL, "label": BASELINE_LABEL, "description": "Repete o último mês observado antes do holdout. Serve apenas como referência; não participa da seleção."},
        "models": model_rows,
        "beat_baseline_skus": outcomes["superou"],
        "did_not_beat_baseline_skus": outcomes["nao_superou"],
        "not_comparable_skus": outcomes["nao_comparavel"],
        "items": [{key: value for key, value in row.items() if key not in ("wapes", "errors")} for row in rows],
        "limitations": [
            "O mesmo holdout escolhe o modelo e mede o erro; o WAPE do modelo selecionado tende a ser otimista.",
            "WAPE é calculado sobre faturamento mensal por SKU e não é diretamente comparável ao MAPE informado pela empresa.",
            "Com três meses de holdout por SKU, a amostra temporal é pequena; os resultados não garantem precisão futura.",
        ],
    }


def _model_windows(code: str, series: pd.Series, origins: list[pd.Period], config: dict[str, Any]) -> list[dict[str, Any]]:
    horizon = config["evaluation"]["horizon_months"]
    windows = []
    for origin in origins:
        train = series[series.index <= origin]
        targets = pd.period_range(origin + 1, periods=horizon, freq="M")
        predicted = _naive_last(train, targets) if code == BASELINE_MODEL else run_model(code, train, targets, config)
        if predicted is None:
            return []  # o modelo não cobre todas as origens: fica fora da comparação deste SKU
        windows.append({"months": [period.month for period in targets], "actual": [float(value) for value in series.reindex(targets).tolist()],
                        "predicted": list(predicted)})
    return windows


def _evaluate_forecasts_rolling(sales: pd.DataFrame, forecasts: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    by_sku = {str(row["sku"]): row for row in forecasts.to_dict("records")}
    chain = list(config["official"]["model_chain"])
    peaks = config["evaluation"]["peak_months"]
    keys = [*chain, "selected", BASELINE_MODEL]
    rows: list[dict] = []
    insufficient: list[str] = []
    totals = {key: {name: 0.0 for name in window_errors([])} for key in keys}
    origins_used: set[str] = set()
    for sku, forecast in sorted(by_sku.items()):
        series = _monthly_series(sales, sku)
        origins = evaluation_origins(series, config)
        if forecast.get("status") != "ok" or not origins:
            insufficient.append(sku)
            continue
        windows = {code: _model_windows(code, series, origins, config) for code in [*chain, BASELINE_MODEL]}
        windows["selected"] = chain_windows(series, config, origins)
        origins_used.update(window["origin"] for window in windows["selected"])
        wapes: dict[str, float | None] = {}
        errors: dict[str, float | None] = {}
        actual_total = 0.0
        for key in keys:
            if not windows[key]:
                wapes[key] = errors[key] = None
                continue
            measured = window_errors(windows[key], peaks)
            for name, value in measured.items():
                totals[key][name] += value
            errors[key] = measured["all_abs"]
            value = ratio(measured["all_abs"], measured["all_actual"])
            wapes[key] = None if value is None else round(value, 4)
            if key == "selected":
                actual_total = measured["all_actual"]
        selected_wape, baseline_wape = wapes.get("selected"), wapes.get(BASELINE_MODEL)
        if selected_wape is None or baseline_wape is None:
            outcome = "nao_comparavel"
        elif selected_wape < baseline_wape:
            outcome = "superou"
        else:
            outcome = "nao_superou"
        selected_model = str(forecast["model"])
        rows.append({
            "sku": sku,
            "selected_model": selected_model,
            "selected_model_label": CANDIDATE_LABELS.get(selected_model, selected_model),
            "selected_wape": selected_wape,
            "baseline_wape": baseline_wape,
            "candidate_wapes": {code: wapes[code] for code in chain},
            "outcome": outcome,
            "holdout_actual_total": round(actual_total, 1),
            "wapes": wapes,
            "errors": errors,
        })

    winners: dict[str, int] = {}
    for row in rows:
        winners[row["selected_model"]] = winners.get(row["selected_model"], 0) + 1

    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 4)

    def split(key: str) -> dict[str, float | None]:
        item = totals[key]
        return {
            "peak_weighted_wape": rounded(ratio(item["peak_abs"], item["peak_actual"])),
            "peak_weighted_bias": rounded(ratio(item["peak_signed"], item["peak_actual"])),
            "normal_weighted_wape": rounded(ratio(item["normal_abs"], item["normal_actual"])),
            "normal_weighted_bias": rounded(ratio(item["normal_signed"], item["normal_actual"])),
        }

    model_rows = [
        {"model": code, "label": CANDIDATE_LABELS[code], "role": "candidato", "selected_skus": winners.get(code, 0), **_aggregate(rows, code), **split(code)}
        for code in chain
    ]
    model_rows.append({"model": "selected", "label": "Previsão oficial (motor v2)", "role": "selecionado", "selected_skus": len(rows),
                       **_aggregate(rows, "selected"), **split("selected")})
    model_rows.append({"model": BASELINE_MODEL, "label": BASELINE_LABEL, "role": "baseline", "selected_skus": 0,
                       **_aggregate(rows, BASELINE_MODEL), **split(BASELINE_MODEL)})
    outcomes = {key: sum(row["outcome"] == key for row in rows) for key in ("superou", "nao_superou", "nao_comparavel")}
    origins = sorted(origins_used)
    span = f"{origins[0]} a {origins[-1]}" if origins else "nenhuma"
    return {
        "method": "rolante",
        "holdout_months": config["evaluation"]["horizon_months"],
        "origins": origins,
        "peak_months": peaks,
        "total_skus": len(by_sku),
        "eligible_skus": len(rows),
        "insufficient_skus": len(insufficient),
        "insufficient_sku_list": insufficient,
        "zero_demand_holdout_skus": sum(row["holdout_actual_total"] <= 0 for row in rows),
        "baseline": {"model": BASELINE_MODEL, "label": BASELINE_LABEL,
                     "description": "Repete o último mês observado antes de cada origem. Serve apenas como referência; não participa da previsão."},
        "models": model_rows,
        "beat_baseline_skus": outcomes["superou"],
        "did_not_beat_baseline_skus": outcomes["nao_superou"],
        "not_comparable_skus": outcomes["nao_comparavel"],
        "items": [{key: value for key, value in row.items() if key not in ("wapes", "errors")} for row in rows],
        "limitations": [
            f"Erro medido em {len(origins)} origens rolantes ({span}), cada uma prevendo os {config['evaluation']['horizon_months']} meses seguintes só com dados anteriores a ela.",
            "Os meses de pico testados são janeiro e fevereiro; novembro não cai em nenhuma origem porque o modelo exige 15 meses de histórico. O pico de novembro é conferido pelo caso congelado VC-28.",
            "As origens se sobrepõem e os SKUs compartilham a sazonalidade: não são observações independentes.",
            "WAPE é calculado sobre faturamento mensal por SKU e não é diretamente comparável ao MAPE informado pela empresa.",
        ],
    }


# ------------------------------------------------------------ analysis time

def summarize_analysis_time(feedback_rows: Iterable[tuple], minimum_sample: int) -> dict[str, Any]:
    """Consolidate registered minutes without claiming a gain before the sample is sufficient."""
    rows = list(feedback_rows)
    minutes = [int(row[5]) for row in rows if row[5] is not None]
    sufficient = len(minutes) >= minimum_sample
    return {
        "feedback_count": len(rows),
        "records_with_minutes": len(minutes),
        "total_minutes": sum(minutes) if minutes else None,
        "average_minutes_per_decision": None if not minutes else round(sum(minutes) / len(minutes), 1),
        "median_minutes_per_decision": None if not minutes else float(median(minutes)),
        "minimum_sample": minimum_sample,
        "sample_status": "suficiente" if sufficient else "insuficiente",
        "comparison_allowed": sufficient,
        "note": (
            "Amostra atinge o mínimo definido, mas os minutos medem decisões registradas, não a jornada semanal completa do PCP."
            if sufficient else
            f"Somente {len(minutes)} registro(s) com tempo de análise; mínimo de {minimum_sample} para comparar com a linha de base. Nenhum ganho é afirmado."
        ),
    }


def process_comparison(config: dict[str, Any], forecast_evaluation: dict[str, Any], analysis_time: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep informed, recalculated and target values in separate fields."""
    selected = next(row for row in forecast_evaluation["models"] if row["model"] == "selected")
    recalculated = {
        "analysis_time": {
            "value": None,
            "unit": "horas/semana",
            "comparable": False,
            "reason": analysis_time["note"],
        },
        "forecast_error": {
            "value": selected["weighted_wape"],
            "unit": "WAPE ponderado (origens rolantes com pico)" if forecast_evaluation.get("method") == "rolante" else "WAPE ponderado (holdout de 3 meses)",
            "comparable": False,
            "reason": "Erro do modelo estatístico do protótipo sobre faturamento. A empresa informa MAPE do forecast comercial; a base só traz forecast comercial para meses futuros, então esse erro não pode ser recalculado.",
        },
        "on_time_orders": {
            "value": None,
            "unit": "percentual",
            "comparable": False,
            "reason": "A base não traz histórico de entregas realizadas; não é possível recalcular.",
        },
        "plan_adherence": {
            "value": None,
            "unit": "percentual",
            "comparable": False,
            "reason": "A base não traz produção realizada contra planejada; não é possível recalcular.",
        },
    }
    return [{
        "id": item["id"],
        "label": item["label"],
        "informed": {"value": item["value"], "unit": item["unit"], "nature": "informado", "source": item["source"]},
        "recalculated": {**recalculated[item["id"]], "nature": "recalculado"},
        "target": None if item.get("target") is None else {"value": item["target"], "unit": item["target_unit"], "nature": "meta"},
    } for item in config["company_baseline"]]


# ------------------------------------------------------------ frozen cases

def _check(field: str, spec: Any, obtained: Any) -> dict[str, Any]:
    if isinstance(spec, dict) and ("includes" in spec or "excludes" in spec):
        values = set(obtained or [])
        missing = [code for code in spec.get("includes", []) if code not in values]
        unexpected = [code for code in spec.get("excludes", []) if code in values]
        parts = []
        if spec.get("includes"):
            parts.append("inclui " + ", ".join(spec["includes"]))
        if spec.get("excludes"):
            parts.append("não inclui " + ", ".join(spec["excludes"]))
        return {"field": field, "expected": "; ".join(parts), "obtained": sorted(values), "passed": not missing and not unexpected}
    if isinstance(spec, dict) and "includes_any" in spec:
        values = set(obtained or [])
        return {"field": field, "expected": "inclui ao menos um de " + ", ".join(spec["includes_any"]), "obtained": sorted(values),
                "passed": any(code in values for code in spec["includes_any"])}
    if isinstance(spec, dict) and "in" in spec:
        return {"field": field, "expected": "um de " + ", ".join(map(str, spec["in"])), "obtained": obtained, "passed": obtained in spec["in"]}
    if isinstance(spec, dict) and "between" in spec:
        low, high = spec["between"]
        return {"field": field, "expected": f"entre {low} e {high}", "obtained": obtained, "passed": obtained is not None and low <= obtained <= high}
    if isinstance(spec, dict) and "min" in spec:
        return {"field": field, "expected": f"≥ {spec['min']}", "obtained": obtained, "passed": obtained is not None and obtained >= spec["min"]}
    if isinstance(spec, dict) and "max" in spec:
        return {"field": field, "expected": f"≤ {spec['max']}", "obtained": obtained, "passed": obtained is not None and obtained <= spec["max"]}
    if isinstance(spec, dict) and "not" in spec:
        return {"field": field, "expected": f"diferente de {spec['not']}", "obtained": obtained, "passed": obtained is not None and obtained != spec["not"]}
    if isinstance(spec, dict) and "positive" in spec:
        return {"field": field, "expected": "> 0", "obtained": obtained, "passed": obtained is not None and obtained > 0}
    if isinstance(spec, dict) and "equals" in spec:
        return {"field": field, "expected": f"= {spec['equals']}", "obtained": obtained, "passed": obtained is not None and obtained == spec["equals"]}
    if isinstance(spec, dict) and "is_null" in spec:
        return {"field": field, "expected": "nulo (não disponível)", "obtained": obtained, "passed": obtained is None}
    if isinstance(spec, dict) and "empty" in spec:
        return {"field": field, "expected": "vazio", "obtained": obtained, "passed": obtained is not None and len(obtained) == 0}
    return {"field": field, "expected": spec, "obtained": obtained, "passed": obtained == spec}


def _indicator_frame(values: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame([values])
    for column in ("first_promised_date", "first_production_completion"):
        frame[column] = pd.to_datetime(frame[column])
    return frame


def _outranks_higher_value_active(ranked_row: dict[str, Any] | None, ranking: pd.DataFrame | None, plans: dict[str, dict[str, Any]] | None) -> bool | None:
    """Etapa 16.3: o SKU fica à frente de um SKU ativo da mesma faixa com valor observado maior? None sem faixa ou valor."""
    if ranked_row is None or ranking is None or "urgency_tier" not in ranking or ranked_row.get("urgency_tier") is None:
        return None
    observed = (ranked_row.get("value_at_risk") or {}).get("observed")
    if observed is None:
        return None
    for row in ranking.to_dict("records"):
        other = (row.get("value_at_risk") or {}).get("observed")
        active = not (plans or {}).get(row["sku"], {}).get("discontinued")
        if (row["urgency_tier"] == ranked_row["urgency_tier"] and row["priority"] > ranked_row["priority"] and active
                and other is not None and other > observed):
            return True
    return False


def _operational_output(indicator: dict[str, Any], forecast: dict[str, Any], codes: list[str], priority: int | None,
                        plan: dict[str, Any] | None = None, settings: dict[str, Any] | None = None,
                        ranked_row: dict[str, Any] | None = None, allocation_sku: dict[str, Any] | None = None,
                        ranking: pd.DataFrame | None = None, plans: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Com plano (casos da base), o rótulo usa a mesma tabela de alavancas da API: contexto do plano, da alocação e da faixa da linha do ranking."""
    recommendation = build_operational_recommendation(indicator, forecast, codes, plan)
    context = None
    if plan is not None:
        tier = None if ranked_row is None or ranked_row.get("urgency_tier") is None else {"tier": int(ranked_row["urgency_tier"])}
        context = build_lever_context(plan, allocation_sku, tier, (plan.get("capacity") or {}).get("status"), plan.get("reference_date"))
    challenge = label_operational(recommendation["action"], priority, forecast.get("status"), None, recommendation["capacity_status"], None,
                                  settings or CHALLENGE_DEFAULTS, context=context)
    risk = (ranked_row or {}).get("value_at_risk") or {}
    return {
        "signals": sorted(codes),
        "ranked": priority is not None,
        "priority": priority,
        "forecast_status": forecast.get("status"),
        "action": recommendation["action"],
        "suggested_quantity": recommendation["suggested_quantity"],
        "capacity_status": recommendation["capacity_status"],
        "confidence": recommendation["confidence"],
        "requires_human_review": recommendation["requires_human_review"],
        "coverage_days_calculated": indicator.get("coverage_days_calculated"),
        "data_quality_warnings": list(indicator.get("data_quality_warnings") or []),
        "challenge_code": challenge["code"],
        "secondary_actions": list(recommendation.get("secondary_actions") or []),
        "affected_order_ids": [item["order"] for item in recommendation.get("affected_orders") or []],
        "op_adjusted_orders": [item["order"] for item in recommendation.get("op_adjustments") or [] if item["adjustment"] in ("reduzir", "cancelar")],
        "op_anticipated_orders": [item["order"] for item in recommendation.get("op_adjustments") or [] if item["adjustment"] == "antecipar"],
        "urgency_tier": None if context is None else context["urgency_tier"],
        "value_at_risk_estimated": risk.get("estimated"),
        "outranks_higher_value_active": _outranks_higher_value_active(ranked_row, ranking, plans),
        "lever": challenge["lever"],
        "decide_by": challenge["decide_by"],
    }


def _challenge_output(case_input: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Executa o mesmo rotulador do produto sobre uma entrada congelada; nada é recalculado à parte."""
    level = case_input["level"]
    if level == "operational":
        reference = case_input.get("reference_date")
        label = label_operational(case_input["action"], case_input.get("priority"), case_input.get("forecast_status", "ok"), case_input.get("event_alerts"),
                                  case_input.get("capacity_status"), None if reference is None else date.fromisoformat(reference), settings,
                                  context=case_input.get("context"))
    elif level == "commercial":
        label = label_commercial_row(case_input["row"], settings)
    elif level == "partner":
        rows = [{**row, "challenge_action": label_commercial_row(row, settings)} for row in case_input["rows"]]
        label = label_partner(case_input["summary"], rows, case_input.get("priority_by_sku", {}), settings)
    else:
        label = label_channel_row(case_input["row"])
    if label is None:
        return {"code": None, "label": None, "source": level, "signals_used": [], "evidence_count": 0, "requires_human_review": None}
    return {"code": label["code"], "label": label["label"], "source": label["source"], "signals_used": sorted(label["signals_used"]),
            "evidence_count": len(label["evidence"]), "requires_human_review": label["requires_human_review"]}


_TOTAL_FIELD = re.compile(r"^total_units_(\d{4})_(\d{2})$")
_FAMILY_FIELD = re.compile(r"^family_units_(.+?)_(\d{4})((?:_\d{2})+)$")


def _forecast_aggregate_output(fields: Iterable[str], forecasts: pd.DataFrame, indicators: pd.DataFrame) -> dict[str, Any]:
    """Soma da previsão oficial por mês (`total_units_AAAA_MM`) ou por família e meses (`family_units_familia_AAAA_MM_MM`)."""
    family_by_sku = {} if indicators.empty or "family" not in indicators else dict(zip(indicators["SKU"], indicators["family"]))
    monthly: dict[tuple[str, str], float] = {}
    for row in forecasts.to_dict("records"):
        if row.get("status") != "ok":
            continue
        family = str(family_by_sku.get(row["sku"], "")).casefold()
        for month, value in zip(row.get("forecast_months") or [], row.get("forecast_values") or []):
            key = (family, str(month)[:7])
            monthly[key] = monthly.get(key, 0.0) + float(value)
    obtained: dict[str, Any] = {}
    for field in fields:
        if match := _TOTAL_FIELD.match(field):
            month = f"{match.group(1)}-{match.group(2)}"
            values = [value for (_, key), value in monthly.items() if key == month]
            obtained[field] = round(sum(values), 1) if values else None
        elif match := _FAMILY_FIELD.match(field):
            family, months = match.group(1).casefold(), [f"{match.group(2)}-{item}" for item in match.group(3).strip("_").split("_")]
            values = [monthly.get((family, month)) for month in months]
            obtained[field] = None if any(value is None for value in values) else round(sum(values), 1)
    return obtained


_OPERATIONAL_INPUT = (
    "current_stock", "coverage_days_calculated", "lead_time_days", "safety_stock_days", "backlog_order_quantity",
    "production_order_quantity", "first_promised_date", "first_production_completion", "capacity_occupation_average", "has_sell_out",
)
_COMMERCIAL_INPUT = (
    "sell_out_months", "missing_months", "estimated_stock", "average_monthly_sell_out", "coverage_days", "age_months", "backlog_quantity",
)


def _allocation_output(sku_entry: dict[str, Any], allocation: dict[str, Any], source: str) -> dict[str, Any]:
    orders = sku_entry["orders"]
    return {"contested": sku_entry["contested"], "ranked_clients": [row["client"] for row in orders],
            "orders_with_reason": sum(1 for row in orders if row.get("reason")), "first_client": sku_entry["first_client"],
            "last_client": sku_entry["last_client"], "decision_text": sku_entry["decision_text"],
            "requires_human_review": allocation["requires_human_review"], "allocation_source": source}


def _base_allocation(sku: str, plans: dict[str, dict[str, Any]] | None, partner_items: list[dict],
                     allocation: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """Alocação do SKU: a do pipeline quando informada; sem ela, o mesmo `build_allocation` sobre o plano e os pares parceiro–SKU.

    No recálculo o cadastro vem dos próprios pares: o canal direto é reconhecido (`row_kind`) e os demais ficam sem tipo, o que não
    muda a pontuação (só o canal direto pontua pelo tipo)."""
    if allocation is not None:
        return allocation["skus"].get(sku), allocation, "pipeline"
    plan = (plans or {}).get(sku)
    if plan is None:
        return None, None, "indisponivel"
    registry = {item["partner"]: {"Código": item["partner"], "Tipo": DIRECT_CHANNEL_TYPE if item.get("row_kind") == "direct" else None, "Região": item.get("region")}
                for item in partner_items}
    rebuilt = build_allocation({sku: plan}, pd.DataFrame(list(registry.values()), columns=["Código", "Tipo", "Região"]), partner_items, {},
                               load_allocation_settings(), plan["reference_date"])
    return rebuilt["skus"].get(sku), rebuilt, "recalculada sobre o plano e os pares parceiro–SKU"


def _synthetic_allocation(case_input: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Roda `build_allocation` (pontuação + `allocate_sku`) sobre uma entrada congelada: oferta única na referência e os pedidos."""
    sku, reference = case_input["sku"], case_input["reference_date"]
    orders = [{"order": item.get("order") or f"{sku}-{index}", "client": item["client"], "quantity": float(item["quantity"]), "promised_date": item["promised_date"]}
              for index, item in enumerate(case_input["orders"], start=1)]
    plan = {"sku": sku, "reference_date": reference, "open_orders": orders,
            "supply_events": [{"date": reference, "quantity": float(case_input["supply_units"]), "source": "estoque", "ref": None}]}
    coverage = case_input.get("partner_coverage_days") or {}
    pairs = [{"partner": client, "sku": sku, "data_quality": "sufficient" if coverage.get(client) is not None else "insufficient",
              "coverage_days": coverage.get(client), "signals": [{"code": code} for code in codes]}
             for client, codes in (case_input.get("partner_signals") or {}).items()]
    registry = pd.DataFrame([{"Código": item["client"], "Tipo": None, "Região": None} for item in orders], columns=["Código", "Tipo", "Região"])
    allocation = build_allocation({sku: plan}, registry, pairs, {}, load_allocation_settings(), reference)
    return allocation["skus"].get(sku), allocation


def _commercial_label(item: dict[str, Any], settings: dict[str, Any], channel_rows: dict[str, list[dict[str, Any]]] | None) -> dict[str, Any]:
    """Mesmo rótulo da API: canal direto usa a sugestão de canais diretos para o canal e SKU (Etapa 16.1); sem ela, o ramo canal_direto."""
    if item.get("row_kind") == "direct":
        match = next((row for row in (channel_rows or {}).get(item["partner"], []) if row["sku"] == item["sku"]), None)
        if match is not None:
            return label_channel_row(match)
    return label_commercial_row(item, settings)


def _evaluate_case(case: dict, indicators: pd.DataFrame, issues: pd.DataFrame, ranking: pd.DataFrame,
                   forecasts: pd.DataFrame, partner_items: list[dict], thresholds: dict, challenge_settings: dict[str, Any],
                   plans: dict[str, dict[str, Any]] | None = None, capacity: dict[str, Any] | None = None,
                   channel_rows: dict[str, list[dict[str, Any]]] | None = None, allocation: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {key: case.get(key) for key in ("id", "title", "kind", "origin", "origin_reason", "sku", "partner", "family", "limitation", "pending_until")}
    if case.get("pending_until"):
        # Caso gravado antes do código que o atende (protocolo da Etapa 15): fica visível, mas só é executado quando a
        # subetapa indicada remover a marca. Não conta como aprovado nem como reprovado.
        return {**result, "input": None, "expected": case["expected"], "obtained": None, "checks": [], "result": "pendente",
                "adjustment": f"Caso congelado antes da implementação; será executado a partir da Etapa {case['pending_until']}."}
    obtained: dict[str, Any] | None = None
    case_input: dict[str, Any] = {}
    if case["kind"] == "commercial":
        item = next((row for row in partner_items if row["partner"] == case["partner"] and row["sku"] == case["sku"]), None)
        if item is not None:
            case_input = {key: item.get(key) for key in _COMMERCIAL_INPUT}
            obtained = {
                "action": item["action"],
                "signals": sorted(signal["code"] for signal in item["signals"]),
                "data_quality": item["data_quality"],
                "missing_months": item["missing_months"],
                "estimated_stock": item["estimated_stock"],
                "coverage_days": item["coverage_days"],
                "requires_human_review": item["requires_human_review"],
                "challenge_code": _commercial_label(item, challenge_settings, channel_rows)["code"],
            }
    elif case["kind"] == "challenge_action":
        case_input = case["input"]
        obtained = _challenge_output(case_input, challenge_settings)
    elif case["kind"] == "allocation":
        if case["origin"] == "synthetic":
            case_input = case["input"]
            entry, result_allocation = _synthetic_allocation(case_input)
            if entry is not None:
                obtained = _allocation_output(entry, result_allocation, "sintética")
        else:
            entry, result_allocation, source = _base_allocation(case["sku"], plans, partner_items, allocation)
            if entry is not None:
                case_input = {"sku": case["sku"], "orders": [{key: row.get(key) for key in ("order", "client", "quantity", "promised_date")} for row in entry["orders"]]}
                obtained = _allocation_output(entry, result_allocation, source)
    elif case["kind"] == "capacity_family":
        family = next((item for item in (capacity or {}).get("families", []) if item["family"] == case.get("family")), None)
        if family is not None:
            case_input = {"family": family["family"], "line": family["line"], "calendar_end": family["calendar_end"], "peak_months": family["peak_months"]}
            obtained = {key: family[key] for key in ("peak_status", "peak_need_units", "available_until_calendar_end", "unscheduled_quantity", "status", "skus_short")}
    elif case["kind"] == "forecast_aggregate":
        aggregate = _forecast_aggregate_output(case["expected"], forecasts, indicators)
        if aggregate and all(value is not None for value in aggregate.values()):
            case_input, obtained = {"origem": "previsão oficial somada por mês e família"}, aggregate
    elif case["origin"] == "synthetic":
        indicator = case["input"]["indicator"]
        codes = list(evaluate_rules(_indicator_frame(indicator), thresholds)["code"])
        if "sales" in case["input"]:
            sales = pd.DataFrame(case["input"]["sales"]).assign(SKU=indicator["SKU"])
            sales["Mês"] = pd.to_datetime(sales["Mês"])
            forecast = build_official_forecasts(sales).to_dict("records")[0]
        else:
            forecast = case["input"]["forecast"]
        case_input = {**{key: indicator.get(key) for key in _OPERATIONAL_INPUT}, "forecast_status": forecast.get("status"), "forecast_next_month": forecast.get("forecast_next_month")}
        obtained = _operational_output(indicator, forecast, codes, None, None, challenge_settings)
    else:
        row = indicators[indicators.SKU == case["sku"]]
        if not row.empty:
            indicator = {key: _safe(value) for key, value in row.iloc[0].to_dict().items()}
            forecast_rows = forecasts[forecasts.sku == case["sku"]].to_dict("records")
            forecast = forecast_rows[0] if forecast_rows else {"status": "insufficient_data", "forecast_next_month": None}
            codes = list(issues.loc[issues.sku == case["sku"], "code"])
            ranked = ranking[ranking.sku == case["sku"]]
            priority = None if ranked.empty else int(ranked["priority"].iloc[0])
            case_input = {**{key: indicator.get(key) for key in _OPERATIONAL_INPUT}, "forecast_status": forecast.get("status"), "forecast_next_month": forecast.get("forecast_next_month")}
            plan = (plans or {}).get(case["sku"])
            allocation_sku = None if plan is None else _base_allocation(case["sku"], plans, partner_items, allocation)[0]
            obtained = _operational_output(indicator, forecast, codes, priority, plan, challenge_settings,
                                           None if ranked.empty else ranked.iloc[0].to_dict(), allocation_sku, ranking, plans)

    if obtained is None:
        return {**result, "input": None, "expected": case["expected"], "obtained": None, "checks": [], "result": "nao_encontrado",
                "adjustment": "Nenhum ajuste realizado. O caso não foi encontrado na base atual e precisa ser revisado."}
    checks = [_check(field, spec, obtained.get(field)) for field, spec in case["expected"].items()]
    return {
        **result,
        "input": _safe(case_input),
        "expected": case["expected"],
        "obtained": _safe(obtained),
        "checks": _safe(checks),
        "result": "passou" if all(check["passed"] for check in checks) else "falhou",
        "adjustment": "Nenhum ajuste de pesos, limiares ou modelos foi feito a partir deste caso.",
    }


def evaluate_frozen_cases(config: dict[str, Any], *, indicators: pd.DataFrame, issues: pd.DataFrame, ranking: pd.DataFrame,
                          forecasts: pd.DataFrame, partner_items: list[dict], thresholds: dict, source_sha256: str,
                          challenge_settings: dict[str, Any] | None = None, plans: dict[str, dict[str, Any]] | None = None,
                          capacity: dict[str, Any] | None = None, channel_rows: dict[str, list[dict[str, Any]]] | None = None,
                          allocation: dict[str, Any] | None = None) -> dict[str, Any]:
    """`plans` (Etapa 15.3): plano datado por SKU; os casos da base usam a mesma recomendação do produto.

    `channel_rows` (Etapa 16.1): linhas de `build_direct_channels(...)["rows"]`, para rotular o canal direto como a API.
    `allocation` (Etapa 16.2): saída de `build_allocation` do pipeline; sem ela, a alocação do SKU é recalculada pelo mesmo núcleo."""
    settings = challenge_settings or CHALLENGE_DEFAULTS
    items = [_evaluate_case(case, indicators, issues, ranking, forecasts, partner_items, thresholds, settings, plans, capacity, channel_rows, allocation)
             for case in config["cases"]]
    counts = {key: sum(item["result"] == key for item in items) for key in ("passou", "falhou", "nao_encontrado", "pendente")}
    matches = source_sha256 == config["frozen_source_sha256"]
    return {
        "frozen_at": config["frozen_at"],
        "frozen_source_sha256": config["frozen_source_sha256"],
        "source_matches_frozen": matches,
        "source_note": None if matches else "A planilha mudou desde o congelamento; os casos baseados na base precisam ser revisados antes de servir como evidência.",
        "policy": config["policy"],
        "total": len(items),
        "passed": counts["passou"],
        "failed": counts["falhou"],
        "not_found": counts["nao_encontrado"],
        "pending": counts["pendente"],
        "synthetic": sum(item["origin"] == "synthetic" for item in items),
        "items": items,
    }


# ------------------------------------------------------------ safe behavior

def _base_indicator() -> dict[str, Any]:
    return {"minimum_lot": 100, "average_sales_per_day": 10, "safety_stock_days": 10, "current_stock": 100,
            "production_order_quantity": 0, "backlog_order_quantity": 0, "has_sell_out": True}


def safe_behavior_checks(forecasts: pd.DataFrame, recommendations: list[dict], partner_items: list[dict],
                         plans: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Execute the guard rails with controlled inputs; results are reported, never hidden."""
    checks: list[dict[str, Any]] = []

    def add(check_id: str, label: str, passed: bool, evidence: str, method: str = "executado") -> None:
        checks.append({"id": check_id, "label": label, "status": "aprovado" if passed else "reprovado", "method": method, "evidence": evidence})

    ok_forecast = {"status": "ok", "forecast_next_month": 400, "forecast_confidence": "alta"}
    without_sell_out = build_operational_recommendation({**_base_indicator(), "has_sell_out": False}, ok_forecast, [])
    add("missing_sell_out", "Ausência de sell-out reduz a confiança", without_sell_out["confidence"] == "baixa",
        f"Previsão com confiança alta e sem sell-out resultou em confiança {without_sell_out['confidence']}.")

    zero_holdout = _wape(pd.Series([0.0, 0.0, 0.0]), [10.0, 10.0, 10.0])
    add("zero_holdout", "Holdout com demanda zero não gera erro artificial", zero_holdout is None,
        "WAPE retornado como não calculado quando a demanda real do holdout soma zero." if zero_holdout is None else f"WAPE retornou {zero_holdout}.")

    short = pd.DataFrame({"Mês": pd.date_range("2026-05-01", periods=4, freq="MS"), "SKU": "SAFE-01", "Quantidade faturada": [10, 12, 11, 13]})
    short_forecast = build_official_forecasts(short).to_dict("records")[0]
    short_recommendation = build_operational_recommendation(_base_indicator(), short_forecast, [])
    add("insufficient_forecast", "Forecast insuficiente não vira quantidade",
        short_forecast["status"] == "insufficient_data" and short_recommendation["suggested_quantity"] is None and short_recommendation["action"] == "investigar_dados",
        f"Status {short_forecast['status']}, ação {short_recommendation['action']}, quantidade {short_recommendation['suggested_quantity']}.")

    plain = build_operational_recommendation(_base_indicator(), ok_forecast, [])
    pressured = build_operational_recommendation(_base_indicator(), ok_forecast, ["CAPACITY_SHORTFALL"])
    add("aggregated_capacity", "Falta de capacidade exige revisão e não é tratada como garantia",
        pressured["capacity_status"] == "requires_review" and pressured["action"] == "produzir_validar_capacidade" and pressured["confidence"] != "alta",
        f"Com ordem que não cabe na linha: ação {pressured['action']}, confiança {pressured['confidence']} (sem falta: {plain['confidence']}).")

    review = [item for item in recommendations if not item.get("requires_human_review")]
    add("human_review", "Toda recomendação operacional exige revisão humana", not review,
        f"{len(recommendations)} recomendação(ões) da base verificadas; {len(review)} sem revisão obrigatória.")

    insufficient = forecasts[forecasts.status != "ok"]
    zeros = int(insufficient["forecast_next_month"].notna().sum()) if not insufficient.empty else 0
    invented = [item for item in partner_items if item["estimated_stock"] is None and item["coverage_days"] is not None]
    add("no_false_precision", "Dado ausente não é convertido em zero ou cobertura inventada", zeros == 0 and not invented,
        f"{len(insufficient)} previsão(ões) insuficiente(s) com valor: {zeros}; {len(invented)} par(es) com cobertura sem estoque estimado.")

    if plans:
        # Etapa 15.3 — I1/I2: falta projetada nunca fica "Sem ação necessária"; I3: ordem planejada respeita o lote mínimo.
        action_by_sku = {item.get("sku"): item.get("action") for item in recommendations if item.get("sku")}
        hidden = [sku for sku, plan in plans.items()
                  if any(week["shortfall"] for week in plan["projection"]) and action_by_sku.get(sku) == "sem_acao_necessaria"]
        add("no_hidden_shortfall", "Falta projetada nunca aparece como 'Sem ação necessária'", not hidden,
            f"{sum(1 for plan in plans.values() if any(week['shortfall'] for week in plan['projection']))} SKU(s) com falta projetada no horizonte; "
            f"{len(hidden)} sem ação: {', '.join(hidden) or 'nenhum'}.")
        off_lot = [f"{sku} ({order['quantity']:g})" for sku, plan in plans.items() for order in plan["planned_orders"]
                   if plan["minimum_lot"] > 0 and order["quantity"] % plan["minimum_lot"]]
        add("planned_lot", "Ordem planejada é múltiplo do lote mínimo", not off_lot,
            f"{sum(len(plan['planned_orders']) for plan in plans.values())} ordem(ns) planejada(s); fora do lote: {', '.join(off_lot) or 'nenhuma'}.")
    return checks
