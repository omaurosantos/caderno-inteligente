"""Projeção do estoque no parceiro por par parceiro–SKU (só backend; aguarda validação do grupo antes de ir à tela).

Usa a identidade observada em 100% dos meses da base: estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t).

- sell-out previsto = média dos últimos `window_months` meses (a janela de menor erro medida: 6 meses);
- dois cenários de sell-in: `with_replenishment` (média dos mesmos meses) e `without_replenishment` (zero), que mostra
  quando o estoque acaba se a empresa parar de enviar e não depende de prever sell-in;
- o erro de sell-out e de sell-in (WAPE e viés) é medido em origens rolantes com a mesma média e sai em toda resposta.

Só pares com sell-out observado entram; par com mês faltante na janela fica `insufficient_data` (ausente nunca vira zero).
Nada aqui altera ranking, recomendação comercial ou plano oficial.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "partner_projection.json"
REQUIRED = ("window_months", "horizon_months", "days_per_month", "target_coverage_days", "evaluation")
LIMITATIONS = (
    "Estimativa: o sell-out previsto é a média dos últimos meses e não capta sazonalidade (há só 12 meses por par).",
    "Só vale para pares parceiro–SKU com sell-out informado pelo parceiro; os demais não têm projeção.",
    "O cenário com reposição supõe que o sell-in continue na média recente; ele é uma decisão da empresa, não uma previsão.",
    "Projeção em revisão pelo grupo: não alimenta ranking, recomendação comercial nem plano de produção.",
)


def load_partner_projection_settings(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    settings = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED if key not in settings]
    if missing:
        raise ValueError(f"Configuração da projeção no parceiro sem: {', '.join(missing)}")
    for key in ("window_months", "horizon_months", "days_per_month"):
        if not isinstance(settings[key], int) or settings[key] < 1:
            raise ValueError(f"{key} deve ser inteiro positivo")
    if not isinstance(settings["target_coverage_days"], (int, float)) or settings["target_coverage_days"] <= 0:
        raise ValueError("target_coverage_days deve ser positivo")
    pd.Period(settings["evaluation"]["first_origin"], freq="M")
    pd.Period(settings["evaluation"]["last_origin"], freq="M")
    return settings


def _pairs(sell_in: pd.DataFrame, sell_out: pd.DataFrame) -> dict[tuple[str, str], pd.DataFrame]:
    """Série mensal por par com sell-out, sell-in e estoque; meses sem registro ficam NaN (nunca zero)."""
    out = sell_out[["Mês", "Cliente", "SKU", "Quantidade vendida", "Estoque estimado cliente"]].copy()
    inn = sell_in[["Mês", "Cliente", "SKU", "Quantidade enviada"]].copy()
    for frame in (out, inn):
        frame["Mês"] = pd.to_datetime(frame["Mês"]).dt.to_period("M")
        frame["Cliente"] = frame["Cliente"].astype(str)
        frame["SKU"] = frame["SKU"].astype(str)
    merged = out.merge(inn, on=["Mês", "Cliente", "SKU"], how="left")
    pairs = {}
    for (partner, sku), group in merged.groupby(["Cliente", "SKU"]):
        group = group.groupby("Mês")[["Quantidade vendida", "Quantidade enviada", "Estoque estimado cliente"]].sum(min_count=1)
        index = pd.period_range(group.index.min(), group.index.max(), freq="M")
        pairs[(partner, sku)] = group.reindex(index).astype(float)
    return pairs


def _window_mean(series: pd.Series, window: int) -> float | None:
    tail = series.tail(window)
    if len(tail) < window or tail.isna().any():
        return None
    return float(tail.mean())


def _errors(series: pd.Series, settings: dict[str, Any]) -> dict[str, float]:
    """Σ|erro|, Σ(previsto − real) e Σ real da média móvel nas origens rolantes; meses ausentes ficam fora da medida."""
    window, horizon = settings["window_months"], settings["horizon_months"]
    totals = {"abs": 0.0, "signed": 0.0, "actual": 0.0, "points": 0}
    origins = pd.period_range(settings["evaluation"]["first_origin"], settings["evaluation"]["last_origin"], freq="M")
    for origin in origins:
        predicted = _window_mean(series[series.index <= origin], window)
        if predicted is None:
            continue
        for target in pd.period_range(origin + 1, periods=horizon, freq="M"):
            actual = series.get(target)
            if actual is None or math.isnan(actual):
                continue
            totals["abs"] += abs(predicted - actual)
            totals["signed"] += predicted - actual
            totals["actual"] += actual
            totals["points"] += 1
    return totals


def _metric(totals: dict[str, float]) -> dict[str, Any]:
    if totals["actual"] <= 0:
        return {"wape": None, "bias": None, "points": int(totals["points"])}
    return {"wape": round(totals["abs"] / totals["actual"], 4), "bias": round(totals["signed"] / totals["actual"], 4), "points": int(totals["points"])}


def _scenario(stock: float, sell_in: float, sell_out: float, months: list[pd.Period], daily: float) -> dict[str, Any]:
    level, levels, stockout = stock, [], None
    for month in months:
        level += sell_in - sell_out
        levels.append(round(level, 1))
        if stockout is None and level <= 0:
            stockout = str(month)
    return {
        "monthly_sell_in": round(sell_in, 1), "projected_stock": levels, "stockout_month": stockout,
        "coverage_days_end": None if daily <= 0 else round(max(0.0, levels[-1]) / daily, 1),
    }


def _item(partner: str, sku: str, frame: pd.DataFrame, settings: dict[str, Any], totals: dict[str, dict]) -> dict[str, Any]:
    window, horizon, days = settings["window_months"], settings["horizon_months"], settings["days_per_month"]
    last = frame.index.max()
    stock = frame["Estoque estimado cliente"].get(last)
    sell_out = _window_mean(frame["Quantidade vendida"], window)
    sell_in = _window_mean(frame["Quantidade enviada"], window)
    errors = {"sell_out": _errors(frame["Quantidade vendida"], settings), "sell_in": _errors(frame["Quantidade enviada"], settings)}
    for kind, value in errors.items():
        for key in ("abs", "signed", "actual", "points"):
            totals[kind][key] += value[key]
    base = {"partner": partner, "sku": sku, "reference_month": str(last), "history_months": int(len(frame)),
            "errors": {kind: _metric(value) for kind, value in errors.items()}}
    if stock is None or math.isnan(stock) or sell_out is None or sell_in is None:
        return {**base, "status": "insufficient_data", "current_stock": None, "forecast_monthly_sell_out": None,
                "coverage_days_now": None, "replenishment_to_target": None, "months": [], "scenarios": None,
                "reason": f"São necessários {window} meses completos de sell-in, sell-out e estoque informado."}
    months = list(pd.period_range(last + 1, periods=horizon, freq="M"))
    daily = sell_out / days
    target = settings["target_coverage_days"] * daily
    return {
        **base, "status": "ok", "reason": None,
        "current_stock": round(float(stock), 1),
        "forecast_monthly_sell_out": round(sell_out, 1),
        "coverage_days_now": None if daily <= 0 else round(float(stock) / daily, 1),
        # Quanto enviar no próximo mês para terminar o mês com a cobertura-alvo, depois de vender o previsto.
        "replenishment_to_target": round(max(0.0, target - (float(stock) - sell_out)), 1),
        "months": [str(month) for month in months],
        "scenarios": {
            "with_replenishment": _scenario(float(stock), sell_in, sell_out, months, daily),
            "without_replenishment": _scenario(float(stock), 0.0, sell_out, months, daily),
        },
    }


def build_partner_stock_projection(dataset: dict[str, pd.DataFrame], settings: dict[str, Any]) -> dict[str, Any]:
    totals = {"sell_out": {"abs": 0.0, "signed": 0.0, "actual": 0.0, "points": 0}, "sell_in": {"abs": 0.0, "signed": 0.0, "actual": 0.0, "points": 0}}
    pairs = _pairs(dataset["Sell_In"], dataset["Sell_Out"])
    items = [_item(partner, sku, frame, settings, totals) for (partner, sku), frame in sorted(pairs.items())]
    window = settings["window_months"]
    return {
        "method": {
            "identity": "estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t)",
            "sell_out_forecast": f"média dos últimos {window} meses de sell-out do par",
            "scenarios": {
                "with_replenishment": f"sell-in igual à média dos últimos {window} meses",
                "without_replenishment": "sell-in zero (quando o estoque acaba se a empresa parar de enviar)",
            },
            "replenishment_to_target": f"quantidade para terminar o próximo mês com {settings['target_coverage_days']} dias de cobertura",
            "error": "WAPE = Σ|previsto − real| ÷ Σ real e viés = Σ(previsto − real) ÷ Σ real da mesma média, prevendo os "
                     f"{settings['horizon_months']} meses seguintes a cada origem de {settings['evaluation']['first_origin']} a {settings['evaluation']['last_origin']}",
            "settings": settings,
        },
        "errors": {kind: _metric(value) for kind, value in totals.items()},
        "pairs": len(items),
        "pairs_with_projection": sum(item["status"] == "ok" for item in items),
        "items": items,
        "limitations": list(LIMITATIONS),
        "nature": "estimado",
        "requires_human_review": True,
    }
