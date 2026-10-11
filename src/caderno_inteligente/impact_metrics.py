"""Impacto mensurável (P8, parte 2): valor em risco endereçado e comparação modelo × Forecast_Comercial (S&OP)."""
import math
from typing import Any, Iterable

import pandas as pd

SOP_NOTE = "O erro do S&OP não é mensurável: a base só traz meses futuros. A divergência é pauta de revisão, não prova de erro de nenhum dos dois lados."


def _month(value: Any) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return str(pd.Timestamp(value).to_period("M"))


def addressed_value(feedback_records: Iterable[dict[str, Any]], ranking_records: Iterable[dict[str, Any]],
                    missing_reason: str | None = None) -> dict[str, Any]:
    """Soma `value_at_risk.observed` dos SKUs com decisão registrada. SKU sem valor observado não soma: conta à parte.

    `missing_reason` (ex.: persistência indisponível) ou nenhuma decisão registrada → `observed_total` None com o motivo, nunca R$ 0."""
    decided = [] if missing_reason else sorted({record["sku"] for record in feedback_records if record.get("sku")})
    if not decided:
        reason = missing_reason or "Nenhuma decisão registrada: não há valor endereçado a medir."
        return {"observed_total": None, "missing_reason": reason, "sku_count": 0, "decided_skus": [],
                "skus_without_value": [], "nature": "observado", "note": f"Valor endereçado não disponível. {reason}"}
    by_sku = {row["sku"]: row for row in ranking_records}
    total, counted, without_value = 0.0, [], []
    for sku in decided:
        observed = (by_sku.get(sku, {}).get("value_at_risk") or {}).get("observed")
        if observed is None or not math.isfinite(observed):
            without_value.append(sku)
            continue
        total += float(observed)
        counted.append(sku)
    note = (f"Soma do valor observado em risco (pedidos sem cobertura na data prometida × preço vigente) de {len(counted)} SKU(s) com decisão registrada. "
            "Mede o valor sob decisão, não o valor recuperado.")
    if without_value:
        note += f" {len(without_value)} SKU(s) decidido(s) sem valor observado calculado ficaram fora da soma: {', '.join(without_value)}."
    # Nenhum SKU decidido com valor calculado: a soma não existe (não é R$ 0).
    reason = None if counted else "Nenhum SKU decidido tem valor observado em risco calculado."
    return {"observed_total": round(total, 2) if counted else None, "missing_reason": reason, "sku_count": len(counted), "decided_skus": decided,
            "skus_without_value": without_value, "nature": "observado", "note": note}


def sop_divergence(forecasts: pd.DataFrame, forecast_comercial: pd.DataFrame | None, threshold: float = 0.2) -> dict[str, Any]:
    """Meses em comum entre a previsão do modelo e o Forecast_Comercial; `ratio = modelo / S&OP − 1`, destaca |ratio| > limiar."""
    result: dict[str, Any] = {"months": [], "threshold": threshold, "count": 0, "items": [], "compared_pairs": 0,
                              "note": SOP_NOTE, "nature": "calculado", "requires_human_review": True}
    if forecast_comercial is None or forecast_comercial.empty or forecasts is None or forecasts.empty:
        result["note"] += " Forecast_Comercial ou previsão do modelo indisponível; nada comparado."
        return result
    sop = {}
    for row in forecast_comercial.to_dict("records"):
        month, units = _month(row.get("Mês")), row.get("Previsão unidades")
        if month and units is not None and not pd.isna(units):
            sop[(row["SKU"], month)] = float(units)
    items, months, pairs = [], set(), 0
    for row in forecasts.to_dict("records"):
        if row.get("status") != "ok":
            continue
        for month, value in zip(row.get("forecast_months") or [], row.get("forecast_values") or []):
            key = (row["sku"], _month(month))
            if sop.get(key, 0) <= 0:
                continue  # sem S&OP ou S&OP zero: razão indefinida, não vira divergência nem zero
            pairs += 1
            months.add(key[1])
            ratio = float(value) / sop[key] - 1
            if abs(ratio) > threshold:
                items.append({"sku": key[0], "month": key[1], "model": round(float(value), 1), "sop": sop[key], "ratio": round(ratio, 4)})
    items.sort(key=lambda item: (-abs(item["ratio"]), item["sku"], item["month"]))
    result.update(months=sorted(months), count=len(items), items=items, compared_pairs=pairs)
    return result
