"""Cartão do modelo oficial de previsão: o que prevê, com que dados, sob quais premissas e com que erro medido.

Tudo sai da configuração em uso (`config/forecast_engine.json`) e da previsão oficial já calculada; nada aqui altera a
previsão. As premissas são as regras que o código aplica, escritas para quem decide.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from .forecast_candidates import CANDIDATES, LEVEL_MONTHS, SEASONAL_LEVEL_MIN_HISTORY, describe_seasonal_level
from .official_forecast import ENGINE_LABELS, MINIMUM_HISTORY_MONTHS, V2_LIMITATION, chain_windows, ratio, window_errors

TARGET = {
    "what": "Unidades faturadas por SKU e mês",
    "source": "Vendas_24m → Quantidade faturada, somada entre todos os clientes e canais",
    "granularity": "SKU × mês",
}
CONFIDENCE_RULE = "Confiança pelo erro medido (WAPE): alta até 20%, média até 40%, baixa acima de 40% ou sem medida."
COMMON_ASSUMPTIONS = (
    "Mês sem venda dentro do histórico do SKU conta como zero; antes da primeira venda não há histórico.",
    f"SKU com menos de {MINIMUM_HISTORY_MONTHS} meses de histórico não recebe previsão (fica sem número, nunca zero).",
    "A previsão nunca é negativa.",
    "A previsão é do SKU inteiro: não é distribuída entre parceiros, canais ou regiões.",
)
LIMITATIONS = (
    V2_LIMITATION,
    "O erro mede o passado recente nas origens do protocolo; não garante o erro futuro.",
    "Os SKUs compartilham a mesma sazonalidade: os erros por SKU não são observações independentes.",
)


def _model_assumption(code: str, config: dict[str, Any]) -> str:
    if code == "seasonal_level":
        low, high = config["seasonal_level"]["ratio_bounds"]
        return (
            f"O mesmo mês do ano anterior se repete, corrigido pelo crescimento do nível (média dos {LEVEL_MONTHS} últimos meses ÷ "
            f"mesmos meses um ano antes). A razão de cada mês fica entre {low:g} e {high:g} vezes o nível de um ano antes, "
            f"para um mês atípico não dominar. Exige {SEASONAL_LEVEL_MIN_HISTORY} meses de histórico."
        )
    candidate = CANDIDATES[code]
    return f"{candidate.label}: {candidate.description} Exige {candidate.min_history} meses de histórico."


def _evaluation(sales_series: dict[str, pd.Series], config: dict[str, Any]) -> dict[str, Any]:
    windows = [window for series in sales_series.values() for window in chain_windows(series, config)]
    errors = window_errors(windows, config["evaluation"]["peak_months"])
    return {
        "origins": sorted({window["origin"] for window in windows}),
        "horizon_months": config["evaluation"]["horizon_months"],
        "peak_months": list(config["evaluation"]["peak_months"]),
        "wape": ratio(errors["all_abs"], errors["all_actual"]),
        "peak_wape": ratio(errors["peak_abs"], errors["peak_actual"]),
        "normal_wape": ratio(errors["normal_abs"], errors["normal_actual"]),
        "bias": ratio(errors["all_signed"], errors["all_actual"]),
        "evaluated_points": sum(len(window["months"]) for window in windows),
        "metric": "WAPE agrupado = Σ|previsto − real| ÷ Σ real, em todas as origens e SKUs",
    }


def build_model_card(series_map: dict[str, pd.Series], forecasts: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    """Cartão do modelo oficial; no motor v1 a avaliação rolante não se aplica e fica nula."""
    engine = config["engine"]
    records = forecasts.to_dict("records") if not forecasts.empty else []
    used = Counter(record["model"] for record in records if record.get("model"))
    chain = list(config["official"]["model_chain"]) if engine == "v2" else ["moving_average_3", "seasonal_naive_12"]
    lengths = [len(series) for series in series_map.values() if not series.empty]
    return {
        "engine": engine,
        "engine_label": ENGINE_LABELS[engine],
        "target": TARGET,
        "horizon_months": config["official"]["horizon_months"] if engine == "v2" else 3,
        "models": [
            {"model": code, "label": CANDIDATES[code].label, "description": describe_seasonal_level(tuple(config["seasonal_level"]["ratio_bounds"])) if code == "seasonal_level" else CANDIDATES[code].description,
             "min_history_months": SEASONAL_LEVEL_MIN_HISTORY if code == "seasonal_level" else CANDIDATES[code].min_history,
             "skus": used.get(code, 0)}
            for code in chain
        ],
        "data": {
            "skus": len(records),
            "skus_with_forecast": sum(record.get("status") == "ok" for record in records),
            "history_months_max": max(lengths) if lengths else None,
            "history_months_min": min(lengths) if lengths else None,
        },
        "assumptions": [_model_assumption(code, config) for code in chain] + list(COMMON_ASSUMPTIONS),
        "evaluation": _evaluation(series_map, config) if engine == "v2" else None,
        "confidence": {
            "rule": CONFIDENCE_RULE,
            "skus": {level: sum(record.get("forecast_confidence") == level for record in records) for level in ("alta", "média", "baixa")},
        },
        "limitations": list(LIMITATIONS),
        "nature": "calculado",
    }
