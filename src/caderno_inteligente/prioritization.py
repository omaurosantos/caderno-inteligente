from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

from caderno_inteligente.impact import priority_reason, rank_key, urgency_tier, value_at_risk


CONTEXT_COLUMNS = [
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
]


def load_weights(path: str | Path = "config/prioritization_weights.json") -> dict[str, int]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _confidence(issue_codes: set[str]) -> tuple[str, str]:
    if "LOW_SELLOUT_VISIBILITY" in issue_codes:
        return "baixa", "Sell-out não observado para o SKU; a visibilidade de canal é parcial."
    return "média", "Há sell-out observado, mas a cobertura de parceiros é parcial."


def _context_value(value):
    if isinstance(value, list):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return None if pd.isna(value) else value


SIGNALS_DISCLAIMER = "Ordenação de atenção baseada em regras configuradas; não é solução ótima nem decisão automática de produção."
IMPACT_DISCLAIMER = ("Ordena por faixa de urgência e valor em risco; a pontuação de sinais é exibida, mas não decide a ordem "
                     "(só desempata); não é solução ótima nem decisão automática de produção.")
IMPACT_COLUMNS = ["urgency_tier", "urgency_label", "urgency_reason", "urgency_nature", "value_at_risk", "abc_registry", "abc_measured", "priority_reason"]


def _impact_fields(sku: str, codes: set[str], abc_registry: str | None, impact: dict) -> dict:
    """Etapa 16.3: faixa, valor em risco e ABC medida do SKU. Com alocação calculada, SKU sem pedido aberto (fora dela)
    entra com descoberto observado zero, em vez de cair no fallback dos pedidos afetados."""
    plan = impact["plans"][sku]
    allocation = impact.get("allocation")
    allocation_sku = None
    if allocation is not None:
        allocation_sku = allocation["skus"].get(sku) or {"sku": sku, "orders": [], "uncovered_units_at_promise": 0.0}
    settings = impact["settings"]
    tier = urgency_tier(plan, allocation_sku, codes, settings)
    var = value_at_risk(plan, allocation_sku, (impact.get("prices") or {}).get(sku), tier["tier"], settings["estimated_weight"])
    measured = (impact.get("abc") or {}).get(sku)
    return {
        "urgency_tier": tier["tier"], "urgency_label": tier["label"], "urgency_reason": tier["reason"], "urgency_nature": tier["nature"],
        "value_at_risk": var, "abc_registry": abc_registry, "abc_measured": None if measured is None else measured["abc_measured"],
        "priority_reason": priority_reason(tier, var, allocation_sku),
    }


def prioritize(issues: pd.DataFrame, weights: dict[str, int], indicators: pd.DataFrame, impact: dict | None = None) -> pd.DataFrame:
    """Ordena atenção; não otimiza nem decide produção.

    Sem `impact`: pela pontuação de sinais (comportamento anterior à Etapa 16). Com `impact` = {"plans", "allocation",
    "prices", "abc", "settings"}: faixa de urgência ↑, valor em risco ponderado ↓, pontuação de sinais ↓, SKU (D2).
    """
    if issues.empty:
        extra = IMPACT_COLUMNS if impact is not None else []
        return pd.DataFrame(columns=["priority", "sku", "product", "family", "attention_score", "confidence", "confidence_reason", *CONTEXT_COLUMNS, "reasons", "evidence", "disclaimer", *extra])
    unknown = sorted(set(issues["code"]) - set(weights))
    if unknown:
        raise ValueError(f"Regras sem peso configurado: {', '.join(unknown)}")
    context_by_sku = indicators.set_index("SKU")
    ranked_rows = []
    for sku, group in issues.groupby("sku", sort=False):
        codes = set(group["code"])
        score = int(sum(weights[code] for code in group["code"]))
        confidence, confidence_reason = _confidence(codes)
        context = context_by_sku.loc[sku]
        row = {
            "sku": sku,
            "product": group["product"].iloc[0],
            "family": group["family"].iloc[0],
            "attention_score": score,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            **{column: _context_value(context[column]) for column in CONTEXT_COLUMNS},
            "reasons": group[["code", "description", "severity"]].to_dict("records"),
            "evidence": group[["code", "values_used", "data_origin"]].to_dict("records"),
            "disclaimer": SIGNALS_DISCLAIMER if impact is None else IMPACT_DISCLAIMER,
        }
        if impact is not None:
            registry = context["abc_curve"] if "abc_curve" in context.index else None
            row.update(_impact_fields(sku, codes, None if registry is None or pd.isna(registry) else str(registry).strip().upper(), impact))
        ranked_rows.append(row)
    if impact is None:
        result = pd.DataFrame(ranked_rows).sort_values(["attention_score", "sku"], ascending=[False, True]).reset_index(drop=True)
    else:
        weight = impact["settings"]["estimated_weight"]
        result = pd.DataFrame(sorted(ranked_rows, key=lambda item: rank_key(item, weight))).reset_index(drop=True)
    result.insert(0, "priority", result.index + 1)
    return result
