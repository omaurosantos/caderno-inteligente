"""Estoque projetado agregado para o Início (proposta de melhorias, fase 2).

Camada derivada e somente leitura: conta, a partir da projeção semanal do plano de suprimento (Etapa 15.3), os SKUs
que ficam com estoque negativo (falta) ou abaixo do estoque de segurança no horizonte, em duas leituras:

- `without_new_orders`: só estoque atual e OPs abertas (a projeção base, "se nada novo for liberado");
- `with_planned_orders`: somando as ordens planejadas; a falta que sobra chega antes de qualquer reposição nova.

A produção planejada repete os totais do gráfico de produção da fila (`production_plan.py`). Nenhum cálculo novo:
não muda projeção, ação, quantidade, score nem ranking. SKU sem previsão fica fora da conta e é listado, nunca
entra como "sem falta".
"""
from __future__ import annotations

from typing import Any

import pandas as pd

LIMITATIONS = [
    "Estoque projetado é estimativa: depende da previsão e das datas de conclusão das OPs.",
    "Sem novas ordens = estoque atual + OPs abertas − demanda; com o plano = somando as ordens planejadas, que exigem revisão humana.",
    "Abaixo da segurança inclui os SKUs com falta.",
    "SKUs sem previsão ficam fora da conta, não contam como sem falta.",
]


def _first_week(projection: list[dict[str, Any]], flag: str) -> str | None:
    return next((week["week_start"] for week in projection if week[flag]), None)


def _reading(plans: list[dict[str, Any]], min_key: str, shortfall_flag: str) -> dict[str, Any]:
    shortfall = [plan for plan in plans if _first_week(plan["projection"], shortfall_flag)]
    below_safety = [plan for plan in plans if any(week[min_key] < plan["safety_stock_quantity"] for week in plan["projection"])]
    weeks = [_first_week(plan["projection"], shortfall_flag) for plan in shortfall]
    return {
        "shortfall_sku_count": len(shortfall),
        "below_safety_sku_count": len(below_safety),
        "first_shortfall_week": min(weeks) if weeks else None,
    }


def _weekly(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """SKUs em falta em cada semana, nas duas leituras (gráfico do Início).

    Só entram as semanas presentes na projeção de todos os SKUs avaliados: uma semana além do horizonte de algum
    SKU contaria menos SKUs e pareceria melhora.
    """
    if not plans:
        return []
    by_sku = [{week["week_start"]: week for week in plan["projection"]} for plan in plans]
    common = sorted(set.intersection(*(set(weeks) for weeks in by_sku)))
    return [{
        "week_start": start,
        "shortfall_sku_count": sum(1 for weeks in by_sku if weeks[start]["shortfall"]),
        "shortfall_with_plan_sku_count": sum(1 for weeks in by_sku if weeks[start]["shortfall_with_plan"]),
    } for start in common]


def build_projected_stock(plans: dict[str, dict[str, Any]], indicators: pd.DataFrame, forecasts: pd.DataFrame,
                          production: dict[str, Any]) -> dict[str, Any]:
    """Agrega a projeção por SKU do plano de suprimento; `production` é o resultado de `build_production_plan`."""
    products = {str(row["SKU"]): row for row in indicators[["SKU", "Produto", "family"]].to_dict("records")}
    status = {str(row["sku"]): str(row["status"]) for row in forecasts[["sku", "status"]].to_dict("records")}
    excluded = [{"sku": sku, "reason": "sem_previsao"} for sku in plans if status.get(sku) != "ok"]
    included = [plan for sku, plan in plans.items() if status.get(sku) == "ok"]

    shortfall_skus = []
    for plan in included:
        week = _first_week(plan["projection"], "shortfall")
        if week is None:
            continue
        product = products.get(str(plan["sku"]), {})
        shortfall_skus.append({
            "sku": plan["sku"], "product": product.get("Produto"), "family": product.get("family"),
            "first_shortfall_date": plan["first_shortfall_date"], "first_shortfall_week": week,
            "shortfall_with_plan": _first_week(plan["projection"], "shortfall_with_plan") is not None,
        })
    shortfall_skus.sort(key=lambda item: (item["first_shortfall_date"] or "", item["sku"]))

    total = production["total"]
    return {
        "reference_date": min((plan["reference_date"] for plan in included), default=None),
        "horizon_end": min((plan["horizon_end"] for plan in included), default=None),
        "skus_evaluated": len(included),
        "without_new_orders": _reading(included, "min_projected", "shortfall"),
        "with_planned_orders": _reading(included, "min_projected_with_plan", "shortfall_with_plan"),
        "shortfall_skus": shortfall_skus,
        "weekly": _weekly(included),
        "planned_production": {
            "urgent_total": total["urgent_total"], "horizon_total": total["horizon_total"],
            "urgent_window_end": production["urgent_window_end"],
        },
        "excluded_skus": excluded,
        "limitations": LIMITATIONS,
        "requires_human_review": True,
    }
