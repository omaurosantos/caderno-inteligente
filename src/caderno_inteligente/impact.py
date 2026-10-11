"""Etapa 16.3 (núcleo): faixa de urgência, valor em risco e curva ABC medida para a fila de prioridades.

Camada aditiva e somente leitura. Consome o plano de suprimento (`supply_plan.build_sku_plan`) e o bloco do SKU da alocação
(`allocation.build_allocation`); não altera nenhum dos dois. Dado ausente vira `None` com motivo, nunca zero.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_PATH = Path("config/prioritization_impact.json")
DEFAULT_SETTINGS: dict[str, Any] = {
    "estimated_weight": 0.5,
    "tier_rules": {"production_window_weeks": 4},
    "abc_thresholds": {"A": 0.8, "B": 0.95},
    "abc_window_months": 12,
}
TIER_LABELS = {
    1: "Pedido confirmado sem cobertura",
    2: "Ação de produção nas próximas {weeks} semanas",
    3: "Rever OP ou excesso",
    4: "Produzir no horizonte ou monitorar",
}
VALUE_NATURE = {"observed": "observado", "estimated": "estimado", "excess": "calculado"}
SALES_VALUE = "Valor faturado (R$)"
REGISTRY_ABC = "Curva ABC"


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Configuração de impacto: {name} precisa ser um número finito")
    return float(value)


def _validate_settings(values: dict[str, Any]) -> dict[str, Any]:
    weight = _number(values["estimated_weight"], "estimated_weight")
    if not 0 <= weight <= 1:
        raise ValueError("Configuração de impacto: estimated_weight precisa estar entre 0 e 1")
    rules = values["tier_rules"]
    if not isinstance(rules, dict) or set(rules) != {"production_window_weeks"}:
        raise ValueError("Configuração de impacto: tier_rules aceita apenas production_window_weeks")
    weeks = _number(rules["production_window_weeks"], "tier_rules.production_window_weeks")
    if weeks < 1 or weeks != int(weeks):
        raise ValueError("Configuração de impacto: production_window_weeks precisa ser um inteiro positivo")
    thresholds = values["abc_thresholds"]
    if not isinstance(thresholds, dict) or set(thresholds) != {"A", "B"}:
        raise ValueError("Configuração de impacto: abc_thresholds precisa ter A e B")
    cut_a, cut_b = _number(thresholds["A"], "abc_thresholds.A"), _number(thresholds["B"], "abc_thresholds.B")
    if not 0 < cut_a < cut_b <= 1:
        raise ValueError("Configuração de impacto: abc_thresholds exige 0 < A < B <= 1")
    months = _number(values["abc_window_months"], "abc_window_months")
    if months < 1 or months != int(months):
        raise ValueError("Configuração de impacto: abc_window_months precisa ser um inteiro positivo")
    return {"estimated_weight": weight, "tier_rules": {"production_window_weeks": int(weeks)},
            "abc_thresholds": {"A": cut_a, "B": cut_b}, "abc_window_months": int(months)}


def load_impact_settings(path: str | Path | None = None) -> dict[str, Any]:
    values = {key: (dict(value) if isinstance(value, dict) else value) for key, value in DEFAULT_SETTINGS.items()}
    source = DEFAULT_PATH if path is None else Path(path)
    if source.exists() or path is not None:
        overrides = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(values):
            raise ValueError("Configuração de impacto contém campos desconhecidos")
        values.update(overrides)
    return _validate_settings(values)


# ------------------------------------------------------------------------------------------ ABC medida


def measured_abc(sales: pd.DataFrame, settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Curva ABC pelo faturamento dos últimos `abc_window_months` meses (a janela termina no último mês com venda).

    A classe usa a participação acumulada *antes* do SKU: o líder é sempre A, mesmo se sozinho passar do corte.
    """
    if sales is None or sales.empty or SALES_VALUE not in sales:
        return {}
    months = pd.to_datetime(sales["Mês"]).dt.to_period("M")
    window = sales.loc[months >= months.max() - (settings["abc_window_months"] - 1)]
    revenue = pd.to_numeric(window[SALES_VALUE], errors="coerce").groupby(window["SKU"].astype(str)).sum().sort_values(ascending=False, kind="stable")
    total = float(revenue.sum())
    if total <= 0:
        return {}
    cut_a, cut_b = settings["abc_thresholds"]["A"], settings["abc_thresholds"]["B"]
    result, cumulative = {}, 0.0
    for sku, value in revenue.items():
        before = cumulative
        cumulative += float(value) / total
        result[str(sku)] = {"abc_measured": "A" if before < cut_a else "B" if before < cut_b else "C",
                            "revenue_12m": round(float(value), 2), "cumulative_share": round(cumulative, 4)}
    return result


def abc_registry_divergence_warning(products: pd.DataFrame, measured: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Aviso de qualidade: SKUs cuja Curva ABC do cadastro difere da medida. SKU sem venda na janela não entra."""
    items = []
    for sku, registry in zip(products["SKU"].astype(str), products[REGISTRY_ABC]):
        info = measured.get(sku)
        if info is None or pd.isna(registry):
            continue
        registry = str(registry).strip().upper()
        if registry != info["abc_measured"]:
            items.append({"sku": sku, "registry": registry, "measured": info["abc_measured"], "revenue_12m": info["revenue_12m"]})
    if not items:
        return None
    items.sort(key=lambda item: (-item["revenue_12m"], item["sku"]))
    return {"code": "ABC_REGISTRY_DIVERGENCE", "count": len(items), "items": items,
            "message": f"{len(items)} SKUs têm a Curva ABC do cadastro diferente da medida pelo faturamento dos últimos 12 meses. "
                       "A ABC do cadastro não é usada no ranking; a medida só é exibida ao lado dela."}


# ------------------------------------------------------------------------------------------ faixa de urgência


def _uncovered_orders(allocation_sku: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not allocation_sku:
        return []
    return [order for order in allocation_sku.get("orders", []) if (order.get("uncovered_at_promise") or 0) > 0]


def _urgent_planned(plan: dict[str, Any], settings: dict[str, Any]) -> bool:
    limit = date.fromisoformat(plan["reference_date"]) + timedelta(weeks=settings["tier_rules"]["production_window_weeks"])
    return any(date.fromisoformat(order["release_date"]) <= limit for order in plan.get("planned_orders", []))


def urgency_tier(plan: dict[str, Any], allocation_sku: dict[str, Any] | None, issue_codes: set[str], settings: dict[str, Any]) -> dict[str, Any]:
    """Faixa 1 a 4 pelo plano de suprimento e pela alocação. A faixa 1 é dado observado; as demais são calculadas."""
    weeks = settings["tier_rules"]["production_window_weeks"]
    labels = {tier: text.format(weeks=weeks) for tier, text in TIER_LABELS.items()}
    uncovered = _uncovered_orders(allocation_sku)
    if uncovered:
        clients = ", ".join(dict.fromkeys(order["client"] for order in uncovered))
        return {"tier": 1, "label": labels[1], "reason": f"Pedidos confirmados sem cobertura na data prometida ({clients}).", "nature": "observado"}
    if allocation_sku is None and plan.get("affected_orders"):
        return {"tier": 1, "label": labels[1], "reason": f"{len(plan['affected_orders'])} pedido(s) confirmado(s) não atendido(s) na data prometida (sem alocação).", "nature": "observado"}
    if plan.get("antecipation"):
        return {"tier": 2, "label": labels[2], "reason": "OP em andamento pode ser antecipada.", "nature": "calculado"}
    if _urgent_planned(plan, settings):
        return {"tier": 2, "label": labels[2], "reason": f"Ordem planejada precisa ser liberada nas próximas {weeks} semanas.", "nature": "calculado"}
    if plan.get("early_shortfall"):
        return {"tier": 2, "label": labels[2], "reason": "Falta projetada só na demanda prevista, sem pedido confirmado afetado.", "nature": "estimado"}
    signals = set(plan.get("signals", [])) | set(issue_codes)
    if plan.get("reductions") or signals & {"PROJECTED_EXCESS", "PARTNER_STOCK_BUILDUP"}:
        return {"tier": 3, "label": labels[3], "reason": "OP a reduzir ou cancelar, ou excesso projetado ou acúmulo no parceiro.", "nature": "calculado"}
    return {"tier": 4, "label": labels[4], "reason": "Sem pedido descoberto nem ação de produção na janela de decisão.", "nature": "calculado"}


# ------------------------------------------------------------------------------------------ valor em risco


def _estimated_units(plan: dict[str, Any], observed_units: float | None) -> float | None:
    """Maior déficit projetado (unidades abaixo de zero) entre a referência e `cover_end`, menos o que já está no observado.

    Lê a projeção base do plano (estoque + OPs abertas contra demanda prevista + carteira; sem ordens planejadas) e não
    recalcula a previsão. Pega a ruptura temporária antes da chegada de uma OP, que o saldo na data de cobertura esconde.
    Granularidade semanal: usa o mínimo das semanas que começam até `cover_end` (a última semana pode ir alguns dias além).
    """
    cover_end = plan.get("cover_end") or (plan.get("calculation") or {}).get("cover_end")
    lows = [week["min_projected"] for week in plan.get("projection") or []
            if cover_end and week["week_start"] <= cover_end and week.get("min_projected") is not None]
    if not lows:
        return None
    return max(0.0, -min(lows) - (observed_units or 0.0))


def _excess_units(plan: dict[str, Any]) -> float:
    return sum(max(0.0, item["quantity"] - item["suggested_quantity"]) for item in plan.get("op_adjustments", [])
               if item["adjustment"] in ("reduzir", "cancelar"))


def value_at_risk(plan: dict[str, Any], allocation_sku: dict[str, Any] | None, unit_price: float | None, tier: int,
                  estimated_weight: float = 0.5) -> dict[str, Any]:
    """Valor em reais separado por natureza. `weighted = observed + estimated_weight × estimated` (ausente não vira zero)."""
    result: dict[str, Any] = {"observed": None, "estimated": None, "excess": None, "weighted": None, "unit_price": None,
                              "nature": dict(VALUE_NATURE), "missing_reason": None, "observed_basis": None}
    if unit_price is None or not math.isfinite(unit_price) or unit_price <= 0:
        result["missing_reason"] = "Sem preço vigente em Precos_Produtos para o SKU."
        return result
    result["unit_price"] = float(unit_price)
    reasons = []
    if allocation_sku is not None:
        units = allocation_sku.get("uncovered_units_at_promise")
        result["observed_basis"] = "alocacao"
    else:
        units = sum(order["quantity"] for order in plan.get("affected_orders", []))
        result["observed_basis"] = "pedidos_afetados"
        reasons.append("Sem alocação: o valor observado usa a quantidade total dos pedidos afetados.")
    if units is not None:
        result["observed"] = round(float(units) * unit_price, 2)
    if plan.get("discontinued"):
        reasons.append("Produto em descontinuação: a demanda prevista não entra no valor em risco.")
    else:
        estimated = _estimated_units(plan, units)
        if estimated is None:
            reasons.append("Plano sem projeção de estoque até a data de cobertura; valor estimado indisponível.")
        else:
            result["estimated"] = round(estimated * unit_price, 2)
    if tier == 3:
        if any(item["adjustment"] in ("reduzir", "cancelar") for item in plan.get("op_adjustments", [])):
            result["excess"] = round(_excess_units(plan) * unit_price, 2)
        else:
            reasons.append("Faixa 3 sem OP a reduzir ou cancelar (excesso projetado ou acúmulo no parceiro): excesso em reais não calculado.")
    parts = [(result["observed"], 1.0), (result["estimated"], estimated_weight)]
    present = [value * weight for value, weight in parts if value is not None]
    result["weighted"] = round(sum(present), 2) if present else None
    result["missing_reason"] = " ".join(reasons) or None
    return result


def rank_key(row: dict[str, Any], estimated_weight: float) -> tuple:
    """Faixa ↑, valor ponderado ↓ (ausente por último na faixa), pontuação de sinais ↓, SKU.

    `estimated_weight` recompõe o valor a partir de `value_at_risk` (observado e estimado), de modo que a ordem
    acompanha o peso informado; sem componentes, cai no `weighted` já calculado. Na faixa 3 o valor da faixa é o
    excesso (`value_at_risk.excess`), que ordena antes dos sinais.
    """
    risk = row.get("value_at_risk") or {}
    if row["urgency_tier"] == 3:
        excess = risk.get("excess")
        return (3, -excess if excess is not None else math.inf, -row.get("attention_score", 0), row["sku"])
    parts = [risk.get("observed"), None if risk.get("estimated") is None else risk["estimated"] * estimated_weight]
    present = [value for value in parts if value is not None]
    weighted = sum(present) if present else risk.get("weighted")
    return (row["urgency_tier"], -weighted if weighted is not None else math.inf, -row.get("attention_score", 0), row["sku"])


# ------------------------------------------------------------------------------------------ motivo


def _brl(value: float) -> str:
    def number(amount: float, digits: int) -> str:
        return f"{amount:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if value >= 1_000_000:
        return f"R$ {number(value / 1_000_000, 1)} mi"
    if value >= 1_000:
        return f"R$ {number(value / 1_000, 1)} mil"
    return f"R$ {number(value, 0)}"


def priority_reason(tier_info: dict[str, Any], var: dict[str, Any], allocation_sku: dict[str, Any] | None) -> str:
    """Começa pela faixa e pelo valor, ex.: 'Pedido confirmado sem cobertura · R$ 63,9 mil em risco (KA-05, KA-02)'."""
    tier = tier_info["tier"]
    key, suffix = {1: ("observed", "em risco"), 2: ("estimated", "estimados em risco"), 3: ("excess", "em OP ou estoque excedente")}.get(tier, ("estimated", "estimados em risco"))
    value = var.get(key)
    if value is None:
        text = f"{tier_info['label']} · valor não calculado"
        return f"{text} ({var['missing_reason']})" if var.get("missing_reason") else text
    text = f"{tier_info['label']} · {_brl(value)} {suffix}"
    if tier == 1:
        orders = sorted(_uncovered_orders(allocation_sku), key=lambda order: order.get("rank", 0))
        clients = list(dict.fromkeys(order["client"] for order in orders))
        if clients:
            text += f" ({', '.join(clients)})"
    return text
