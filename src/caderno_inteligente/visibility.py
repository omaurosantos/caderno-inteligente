"""Etapa 16.1: até onde a empresa vê o consumidor, e onde as fontes comerciais não fecham.

Funções puras e somente leitura sobre as abas da planilha. Canal direto: o faturamento (`Vendas_24m`) é a venda ao
consumidor. Parceiro KA: a venda ao consumidor só é vista pelo sell-out informado (`Sell_Out`). O restante do que a
empresa faturou fica "sem visibilidade". Dado ausente nunca vira zero.
"""
from __future__ import annotations

import pandas as pd

from caderno_inteligente.direct_channels import direct_channel_codes

SELLIN_BILLING_RATIO_LIMIT = 1.25
# Faturamento "quase proporcional": a participação de todo cliente em todo SKU fica a até 10% da mediana dos clientes.
BILLING_UNIFORM_SPLIT_BAND = 0.1
UNITS = "Quantidade faturada"


def _periods(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="raise").dt.to_period("M")


def _sales(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frame = data["Vendas_24m"].rename(columns={"Cliente/Canal": "partner", "SKU": "sku", "Mês": "month", UNITS: "billed"})[["partner", "sku", "month", "billed"]].copy()
    frame["month"] = _periods(frame["month"])
    frame["billed"] = pd.to_numeric(frame["billed"], errors="raise")
    return frame.dropna(subset=["billed"])


def _ratio(numerator: float, denominator: float) -> float | None:
    return None if not denominator else round(numerator / denominator, 4)


def build_visibility_journey(data: dict[str, pd.DataFrame], window_months: int = 12) -> dict:
    """Unidades faturadas nos últimos `window_months` meses por tipo de canal, separadas em venda ao consumidor observada e sem visibilidade.

    O sell-out de um KA é limitado, por par parceiro–SKU, ao que a empresa faturou para o par nos mesmos meses: a jornada
    responde "do que vendemos, quanto vimos chegar ao consumidor". O valor bruto fica em `observed_consumer_units_raw`.
    """
    sales = _sales(data)
    partners = data["Parceiros_Canais"]
    direct = set(direct_channel_codes(partners))
    types = dict(zip(partners["Código"].astype(str), partners["Tipo"].astype(str)))
    last = sales["month"].max()
    window = [] if pd.isna(last) else [last - i for i in reversed(range(window_months))]
    billed = sales[sales["month"].isin(window)].groupby(["partner", "sku"], as_index=False)["billed"].sum()
    out = data["Sell_Out"].rename(columns={"Cliente": "partner", "SKU": "sku", "Mês": "month", "Quantidade vendida": "sell_out"})[["partner", "sku", "month", "sell_out"]].copy()
    out["month"] = _periods(out["month"])
    out["sell_out"] = pd.to_numeric(out["sell_out"], errors="raise")
    out = out[out["month"].isin(window) & out["sell_out"].notna()].groupby(["partner", "sku"], as_index=False)["sell_out"].sum()
    pairs = billed.merge(out, on=["partner", "sku"], how="outer")
    pairs["billed"] = pairs["billed"].fillna(0.0)
    pairs["direct"] = pairs["partner"].isin(direct)
    pairs["raw"] = pairs["billed"].where(pairs["direct"], pairs["sell_out"].fillna(0))
    pairs["observed"] = pairs[["raw", "billed"]].min(axis=1)
    pairs["type"] = pairs["partner"].map(types).fillna("Sem cadastro")
    by_type = []
    for kind, group in pairs.groupby("type", sort=False):
        total, observed = float(group["billed"].sum()), float(group["observed"].sum())
        by_type.append({
            "type": kind, "billed_units": total, "observed_consumer_units": observed,
            "observed_consumer_units_raw": float(group["raw"].sum()), "without_visibility_units": total - observed,
            "share_observed": _ratio(observed, total), "exceeds_billing": bool((group["raw"] > group["billed"]).any()),
            "visibility_source": "faturamento_direto" if group["direct"].all() else "sell_out_parceiro",
        })
    by_type.sort(key=lambda item: -item["billed_units"])
    total = float(pairs["billed"].sum())
    observed = float(pairs["observed"].sum())
    return {
        "window_months": [str(month) for month in window], "total_units": total, "by_channel_type": by_type,
        "observed_consumer_units": observed, "without_visibility_units": total - observed, "observed_share": _ratio(observed, total),
        "nature": {
            "total_units": "observado (Vendas_24m.Quantidade faturada)",
            "observed_consumer_units": "observado: faturamento nos canais diretos; sell-out informado pelos parceiros KA, limitado ao faturado por par",
            "without_visibility_units": "calculado: faturado − venda ao consumidor observada",
        },
        "note": ("Canal direto vende ao consumidor: o faturamento é a venda observada. Nos parceiros KA só o sell-out informado é visto; "
                 "o restante do faturado fica sem visibilidade. Ausência de sell-out não é venda zero ao consumidor."),
    }


def sellin_billing_divergence_warning(data: dict[str, pd.DataFrame]) -> dict | None:
    """Sell-in × faturamento por parceiro KA, só nos pares e meses presentes nas duas fontes."""
    sales = _sales(data)
    direct = set(direct_channel_codes(data["Parceiros_Canais"]))
    sent = data["Sell_In"].rename(columns={"Cliente": "partner", "SKU": "sku", "Mês": "month", "Quantidade enviada": "sell_in"})[["partner", "sku", "month", "sell_in"]].copy()
    sent["month"] = _periods(sent["month"])
    sent["sell_in"] = pd.to_numeric(sent["sell_in"], errors="raise")
    both = sent.dropna(subset=["sell_in"]).merge(sales, on=["partner", "sku", "month"], how="inner")
    both = both[~both["partner"].isin(direct)]
    items = []
    for partner, group in both.groupby("partner"):
        sell_in, billed = float(group["sell_in"].sum()), float(group["billed"].sum())
        ratio = sell_in / billed if billed else None
        if ratio is None or ratio > SELLIN_BILLING_RATIO_LIMIT or ratio < 1 / SELLIN_BILLING_RATIO_LIMIT:
            items.append({"partner": str(partner), "sell_in_units": sell_in, "billed_units": billed, "ratio": None if ratio is None else round(ratio, 2)})
    if not items:
        return None
    items.sort(key=lambda item: -(item["ratio"] or float("inf")))
    return {
        "code": "SELLIN_BILLING_DIVERGENCE", "sheet": "Sell_In × Vendas_24m", "count": len(items), "limit": SELLIN_BILLING_RATIO_LIMIT, "items": items,
        "message": "as duas fontes não fecham; o sistema usa Sell_In e Sell_Out para o parceiro e Vendas_24m para o total do SKU",
    }


def billing_uniform_split_warning(data: dict[str, pd.DataFrame]) -> dict | None:
    """Participação de cada SKU no faturamento de cada cliente ÷ mediana dos clientes no mesmo SKU (toda a Vendas_24m).

    Se todas as razões ficam perto de 1, o faturamento por cliente é um rateio do total e não revela padrão por parceiro.
    """
    sales = _sales(data)
    table = sales.groupby(["sku", "partner"])["billed"].sum().unstack()
    if table.shape[1] < 2:
        return None
    totals = table.sum(axis=0)
    mix = table.div(totals.where(totals > 0), axis=1)
    ratios = mix.div(mix.median(axis=1).where(lambda median: median > 0), axis=0).stack().dropna()
    if ratios.empty:
        return None
    low, high = float(ratios.min()), float(ratios.max())
    if low < 1 - BILLING_UNIFORM_SPLIT_BAND or high > 1 + BILLING_UNIFORM_SPLIT_BAND:
        return None
    return {
        "code": "BILLING_UNIFORM_SPLIT", "sheet": "Vendas_24m", "min_ratio": round(low, 2), "max_ratio": round(high, 2), "count": int(len(ratios)),
        "band": BILLING_UNIFORM_SPLIT_BAND,
        "message": "o faturamento por cliente é quase proporcional entre clientes e não é usado para padrões por parceiro",
    }
