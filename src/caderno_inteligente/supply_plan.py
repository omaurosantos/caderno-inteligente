"""Plano de suprimento da Etapa 15.3: projeção datada de estoque, ordens planejadas, ajustes de OP e a ação do SKU.

A projeção é diária (para não esconder atrasos de poucos dias) e resumida por semana. A partir da data de planejamento:

- demanda do dia = pedidos da carteira na data prometida (vencidos entram no primeiro dia) + o que a previsão do mês
  tem além da carteira daquele mês, rateado pelos dias restantes do mês (a mesma regra anti-dupla-contagem de antes);
- reposição = OPs abertas na `Conclusão prevista` (as já vencidas entram no primeiro dia);
- estoque projetado = estoque atual + reposições − demanda, podendo ficar negativo (falta).

A ação sai da projeção, não de uma conta de "próximo mês": falta que nenhuma reposição alcança vira atraso inevitável
(ou antecipação de OP, se uma OP ainda não iniciada puder chegar a tempo); necessidade futura vira ordem planejada com
data de liberação (data de necessidade − lead time); OP acima do necessário ou de produto em descontinuação vira ajuste.
SKU em descontinuação não recebe ordem nova e é planejado só para a carteira confirmada. Nada aqui libera ordem: é
sugestão para revisão humana. Capacidade entra na Etapa 15.4.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "supply_plan.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "reference_date": "2026-09-14",
    "decision_window_weeks": 4,
    "target_cover_weeks": 4,
    "excess_coverage_days": 90,
    "days_per_month": 30.4,
}
CLOSED_ORDER_STATUSES = {"cancelado", "concluído", "concluido", "entregue", "faturado", "encerrada", "concluída", "concluida"}
NOT_STARTED_OP_STATUSES = {"planejada", "liberada"}  # podem começar já; "Em produção" não pode ser antecipada

ACTION_LABELS = {
    "investigar_dados": "Investigar dados",
    "atraso_inevitavel": "Falta inevitável: renegociar prazos e garantir a OP",
    "antecipar_op": "Antecipar OP",
    "produzir_validar_capacidade": "Produzir após validar capacidade",
    "produzir": "Produzir",
    "rever_op": "Rever OP",
    "monitorar_excesso": "Monitorar excesso",
    "sem_acao_necessaria": "Sem ação necessária",
}


def load_supply_settings(path: str | Path | None = None) -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    source = DEFAULT_PATH if path is None else Path(path)
    if source.exists() or path is not None:
        overrides = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(values):
            raise ValueError("Configuração do plano de suprimento contém campos desconhecidos")
        values.update(overrides)
    return _validate_settings(values)


def _validate_settings(values: dict[str, Any]) -> dict[str, Any]:
    def number(key: str) -> float:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Parâmetro do plano de suprimento inválido: {key}")
        return float(value)

    try:
        reference = date.fromisoformat(str(values["reference_date"]))
    except ValueError as error:
        raise ValueError("reference_date deve ser uma data AAAA-MM-DD") from error
    if reference.weekday() != 0:
        raise ValueError("reference_date deve ser uma segunda-feira, como as semanas de Capacidade_Semanal")
    values["reference_date"] = reference.isoformat()
    for key in ("decision_window_weeks", "target_cover_weeks", "excess_coverage_days"):
        if number(key) != int(number(key)) or number(key) < 1:
            raise ValueError(f"Parâmetro precisa ser inteiro ≥ 1: {key}")
        values[key] = int(values[key])
    if not 28 <= number("days_per_month") <= 31:
        raise ValueError("days_per_month deve estar entre 28 e 31")
    values["days_per_month"] = float(values["days_per_month"])
    return values


# ------------------------------------------------------------------------------------------ insumos


def _day(value: Any) -> date | None:
    if value is None or (not isinstance(value, (date, pd.Timestamp)) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _br(value: date | None) -> str:
    """Data curta para textos de motivo (dd/mm); os campos estruturados continuam em ISO."""
    return "—" if value is None else f"{value.day:02d}/{value.month:02d}"


def _open(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "Status" not in frame:
        return frame
    return frame[~frame["Status"].astype(str).str.strip().str.casefold().isin(CLOSED_ORDER_STATUSES)]


def _ceil_lot(quantity: float, lot: float) -> float:
    if quantity <= 0:
        return 0.0
    return float(math.ceil(quantity / lot) * lot) if lot > 0 else float(math.ceil(quantity))


def _floor_lot(quantity: float, lot: float) -> float:
    if quantity <= 0:
        return 0.0
    return float(math.floor(quantity / lot) * lot) if lot > 0 else float(math.floor(quantity))


def daily_demand(forecast: dict[str, Any] | None, orders: list[dict[str, Any]], reference: date, end: date,
                 include_forecast: bool = True) -> tuple[dict[date, float], dict[date, float]]:
    """Carteira e demanda além da carteira por dia, de `reference` a `end` (inclusive)."""
    carteira: dict[date, float] = {}
    by_month: dict[pd.Period, float] = {}
    for order in orders:
        promised = order["promised_date"]
        if promised is None or promised > end:
            continue
        day = max(promised, reference)
        carteira[day] = carteira.get(day, 0.0) + order["quantity"]
        month = pd.Period(promised, freq="M")
        by_month[month] = by_month.get(month, 0.0) + order["quantity"]
    extra: dict[date, float] = {}
    if include_forecast and forecast and forecast.get("status") == "ok":
        for month_text, value in zip(forecast.get("forecast_months") or [], forecast.get("forecast_values") or []):
            month = pd.Period(str(month_text)[:7], freq="M")
            first, last = max(month.start_time.date(), reference), min(month.end_time.date(), end)
            if first > last:
                continue
            remaining_days = (last - first).days + 1
            share = float(value) * remaining_days / month.days_in_month  # parte do mês que ainda não passou
            remainder = max(0.0, share - by_month.get(month, 0.0))
            for offset in range(remaining_days):
                day = first + timedelta(days=offset)
                extra[day] = extra.get(day, 0.0) + remainder / remaining_days
    return carteira, extra


def project(stock: float, days: list[date], demand: dict[date, float], receipts: dict[date, float]) -> list[float]:
    """Estoque projetado no fim de cada dia: entradas do dia antes da demanda do dia; pode ficar negativo."""
    level, result = float(stock), []
    for day in days:
        level += receipts.get(day, 0.0) - demand.get(day, 0.0)
        result.append(level)
    return result


# ------------------------------------------------------------------------------------------ peças do plano


def affected_orders(stock: float, orders: list[dict[str, Any]], receipts: dict[date, float], reference: date, end: date) -> list[dict[str, Any]]:
    """Pedidos que não são atendidos na data prometida, dando à carteira prioridade sobre a demanda prevista."""
    timeline = sorted(receipts.items())
    result, needed = [], 0.0
    for order in sorted(orders, key=lambda item: (item["promised_date"] or end, item["order"])):
        needed += order["quantity"]
        promised = order["promised_date"]
        if promised is None:
            continue
        supply, covered_on = float(stock), reference if stock >= needed else None
        for day, quantity in timeline:
            if covered_on is not None:
                break
            supply += quantity
            if supply >= needed:
                covered_on = max(day, reference)
        if covered_on is None or covered_on > promised:
            result.append({
                "order": order["order"], "client": order["client"], "quantity": order["quantity"], "promised_date": _iso(promised),
                "expected_date": _iso(covered_on), "delay_days": None if covered_on is None else (covered_on - promised).days,
                "overdue_at_reference": promised < reference,
            })
    return result


def _op_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for _, row in frame.iterrows():
        start, finish = _day(row.get("Início previsto")), _day(row.get("Conclusão prevista"))
        records.append({"order": str(row["Ordem"]), "quantity": float(row["Quantidade"]), "start": start, "finish": finish,
                        "status": str(row.get("Status") or "")})
    return sorted(records, key=lambda item: (item["finish"] or date.max, item["order"]))


def _receipts(ops: list[dict[str, Any]], reference: date, quantities: dict[str, float] | None = None) -> dict[date, float]:
    receipts: dict[date, float] = {}
    for op in ops:
        if op["finish"] is None:
            continue
        day = max(op["finish"], reference)
        receipts[day] = receipts.get(day, 0.0) + (op["quantity"] if quantities is None else quantities.get(op["order"], op["quantity"]))
    return receipts


def _earliest_finish(op: dict[str, Any], reference: date) -> date | None:
    """Conclusão mais cedo possível: OP não iniciada pode começar hoje e leva a mesma duração; em produção, não antecipa."""
    if op["finish"] is None:
        return None
    if op["status"].strip().casefold() in NOT_STARTED_OP_STATUSES and op["start"] is not None:
        return reference + (op["finish"] - op["start"])
    return op["finish"]


def _excess_adjustments(stock, days, demand, ops, reference, lot, safety, horizon_end, excess_days) -> list[dict[str, Any]]:
    """Reduz OPs que deixam o estoque acima de `excess_days` de demanda futura + segurança logo após a chegada."""
    quantities = {op["order"]: op["quantity"] for op in ops}
    adjustments = []
    for op in ops:
        if op["finish"] is None:
            continue
        arrival = max(op["finish"], reference)
        levels = dict(zip(days, project(stock, days, demand, _receipts(ops, reference, quantities))))
        if arrival not in levels:
            continue
        window_end = min(arrival + timedelta(days=excess_days), horizon_end)
        keep = sum(demand.get(arrival + timedelta(days=offset), 0.0) for offset in range(1, (window_end - arrival).days + 1)) + safety
        reduce_by = min(_floor_lot(levels[arrival] - keep, lot), quantities[op["order"]])
        if reduce_by <= 0:
            continue
        new_quantity = quantities[op["order"]] - reduce_by
        quantities[op["order"]] = new_quantity
        daily = keep / max(1, (window_end - arrival).days) if window_end > arrival else 0
        adjustments.append({
            "order": op["order"], "quantity": op["quantity"], "finish": _iso(op["finish"]), "status": op["status"],
            "adjustment": "cancelar" if new_quantity <= 0 else "reduzir", "suggested_quantity": new_quantity,
            "reason": f"Depois da chegada em {_br(arrival)}, o estoque projetado ({levels[arrival]:.0f} un.) passa de {excess_days} dias de demanda "
                      f"mais o estoque de segurança ({keep:.0f} un.); reduzir {reduce_by:.0f} un. não cria falta nesse período.",
            "projected_after_arrival": round(levels[arrival], 1), "kept_for_window": round(keep, 1), "daily_demand": round(daily, 2),
            "cause": "excesso_projetado",
        })
    return adjustments


def _discontinued_adjustments(stock, ops, orders, lot) -> list[dict[str, Any]]:
    """Produto em descontinuação: manter só o necessário para a carteira confirmada que o estoque não cobre."""
    need = max(0.0, sum(order["quantity"] for order in orders) - stock)
    adjustments = []
    for op in ops:
        keep = min(op["quantity"], _ceil_lot(need, lot))
        need = max(0.0, need - keep)
        if keep >= op["quantity"]:
            continue
        adjustments.append({
            "order": op["order"], "quantity": op["quantity"], "finish": _iso(op["finish"]), "status": op["status"],
            "adjustment": "cancelar" if keep <= 0 else "reduzir", "suggested_quantity": keep,
            "reason": "Produto em descontinuação: a OP só se justifica para a carteira confirmada que o estoque não cobre"
                      + ("; o estoque já cobre a carteira." if keep <= 0 else f" ({keep:.0f} un., arredondado ao lote)."),
            "cause": "produto_em_descontinuacao",
        })
    return adjustments


def plan_orders(stock, days, demand, receipts, safety, earliest, lead_time, lot, cover_days, horizon_end) -> list[dict[str, Any]]:
    """Ordens planejadas (quantidade por período): na primeira data ≥ chegada mais cedo com estoque abaixo da segurança.

    A quantidade cobre a segurança, a falta do dia e a demanda das `cover_days` seguintes, descontadas as OPs que já chegam
    nessa janela. Se essas OPs bastam, não há ordem nova: o intervalo até elas chegarem é tratado como antecipação ou atraso.
    """
    planned: dict[date, float] = {}
    orders = []
    search_from = earliest
    for _ in range(80):
        merged = {day: receipts.get(day, 0.0) + planned.get(day, 0.0) for day in set(receipts) | set(planned)}
        levels = dict(zip(days, project(stock, days, demand, merged)))
        due = next((day for day in days if day >= search_from and levels[day] < safety), None)
        if due is None:
            break
        window = [due + timedelta(days=offset) for offset in range(1, cover_days + 1) if due + timedelta(days=offset) <= horizon_end]
        cover = sum(demand.get(day, 0.0) for day in window)
        incoming = sum(receipts.get(day, 0.0) for day in window)
        raw = safety - levels[due] + cover - incoming
        if raw <= 0:
            # Uma OP já programada chega dentro da janela e resolve: segue a busca depois da última chegada dela.
            arrivals = [day for day in window if receipts.get(day, 0.0) > 0]
            search_from = (max(arrivals) if arrivals else due) + timedelta(days=1)
            continue
        quantity = _ceil_lot(raw, lot)
        planned[due] = planned.get(due, 0.0) + quantity
        orders.append({"due_date": _iso(due), "release_date": _iso(due - timedelta(days=lead_time)), "quantity": quantity,
                       "raw_quantity": round(raw, 1), "projected_before": round(levels[due], 1), "safety_stock": round(safety, 1),
                       "cover_demand": round(cover, 1), "incoming_op_in_cover": round(incoming, 1)})
    return orders


def _weekly(days, carteira, extra, op_receipts, planned_receipts, base_levels, planned_levels, safety) -> list[dict[str, Any]]:
    weeks: dict[date, dict[str, Any]] = {}
    for day, base, with_plan in zip(days, base_levels, planned_levels):
        start = day - timedelta(days=day.weekday())
        week = weeks.setdefault(start, {"week_start": _iso(start), "carteira": 0.0, "forecast_demand": 0.0, "op_receipts": 0.0,
                                        "planned_receipts": 0.0, "min_projected": base, "min_projected_with_plan": with_plan})
        week["carteira"] += carteira.get(day, 0.0)
        week["forecast_demand"] += extra.get(day, 0.0)
        week["op_receipts"] += op_receipts.get(day, 0.0)
        week["planned_receipts"] += planned_receipts.get(day, 0.0)
        week["min_projected"] = min(week["min_projected"], base)
        week["min_projected_with_plan"] = min(week["min_projected_with_plan"], with_plan)
        week["projected_end"], week["projected_end_with_plan"] = base, with_plan
    rows = []
    for week in weeks.values():
        rows.append({**{key: round(value, 1) if isinstance(value, float) else value for key, value in week.items()},
                     "below_safety": week["projected_end_with_plan"] < safety, "shortfall": week["min_projected"] < 0,
                     "shortfall_with_plan": week["min_projected_with_plan"] < 0})
    return rows


# ------------------------------------------------------------------------------------------ plano por SKU


def build_sku_plan(indicator: dict[str, Any], forecast: dict[str, Any] | None, orders: list[dict[str, Any]], ops_frame: pd.DataFrame,
                   settings: dict[str, Any]) -> dict[str, Any]:
    reference = date.fromisoformat(settings["reference_date"])
    months = (forecast or {}).get("forecast_months") or []
    horizon_end = pd.Period(str(months[-1])[:7], freq="M").end_time.date() if months else reference + timedelta(days=90)
    days = [reference + timedelta(days=offset) for offset in range((horizon_end - reference).days + 1)]
    stock = float(indicator.get("current_stock") or 0.0)
    lot = float(indicator.get("minimum_lot") or 0.0)
    lead_time = int(indicator.get("lead_time_days") or 0)
    daily = indicator.get("reference_daily_demand") or indicator.get("average_sales_per_day") or 0.0
    daily = 0.0 if pd.isna(daily) else float(daily)
    safety = daily * float(indicator.get("safety_stock_days") or 0.0)
    discontinued = str(indicator.get("Status") or "").strip().casefold().startswith("descontinu")
    earliest = reference + timedelta(days=lead_time)

    carteira, extra = daily_demand(forecast, orders, reference, horizon_end, include_forecast=not discontinued)
    demand = {day: carteira.get(day, 0.0) + extra.get(day, 0.0) for day in set(carteira) | set(extra)}
    ops = _op_records(ops_frame)
    op_receipts = _receipts(ops, reference)
    base_levels = project(stock, days, demand, op_receipts)
    level_by_day = dict(zip(days, base_levels))
    first_shortfall = next((day for day in days if level_by_day[day] < 0), None)
    late_orders = affected_orders(stock, orders, op_receipts, reference, horizon_end)

    # Falta que nenhuma ordem nova alcança: antes da chegada mais cedo de uma reposição nova.
    early_shortfall = first_shortfall is not None and first_shortfall < earliest
    early_late_orders = [order for order in late_orders if date.fromisoformat(order["promised_date"]) < earliest]
    need_days = ([first_shortfall] if first_shortfall else []) + [max(date.fromisoformat(order["promised_date"]), reference) for order in late_orders]
    need_day = min(need_days) if need_days else None
    adjustments: list[dict[str, Any]] = []
    if need_day is not None:
        # Uma OP já programada para depois da falta, ainda não iniciada, pode ser antecipada para chegar a tempo.
        candidates = [op for op in ops if op["finish"] is not None and op["finish"] > need_day]
        for op in candidates:
            earliest_finish = _earliest_finish(op, reference)
            if earliest_finish is not None and earliest_finish <= need_day:
                adjustments.append({
                    "order": op["order"], "quantity": op["quantity"], "finish": _iso(op["finish"]), "status": op["status"],
                    "adjustment": "antecipar", "suggested_quantity": op["quantity"], "suggested_finish": _iso(need_day),
                    "reason": f"A falta começa em {_br(need_day)}; a OP ainda não começou e, iniciada em {_br(reference)}, pode concluir até {_br(earliest_finish)}.",
                    "cause": "falta_antes_da_op",
                })
                break

    if discontinued:
        adjustments += _discontinued_adjustments(stock, ops, orders, lot)
        planned = []
    else:
        adjustments += _excess_adjustments(stock, days, demand, ops, reference, lot, safety, horizon_end, settings["excess_coverage_days"])
        planned = plan_orders(stock, days, demand, op_receipts, safety, earliest, lead_time, lot, settings["target_cover_weeks"] * 7, horizon_end)

    window_end = reference + timedelta(days=settings["decision_window_weeks"] * 7)
    for order in planned:
        order["urgent"] = date.fromisoformat(order["release_date"]) <= window_end
        order["late"] = early_shortfall and order["due_date"] == _iso(earliest)
    planned_receipts: dict[date, float] = {}
    for order in planned:
        day = date.fromisoformat(order["due_date"])
        planned_receipts[day] = planned_receipts.get(day, 0.0) + order["quantity"]
    merged = {day: op_receipts.get(day, 0.0) + planned_receipts.get(day, 0.0) for day in set(op_receipts) | set(planned_receipts)}
    planned_levels = project(stock, days, demand, merged)
    reported_orders = affected_orders(stock, orders, merged, reference, horizon_end)

    # Etapa 16.2 (contrato C1): as mesmas séries de oferta e a carteira aberta, para a alocação entre pedidos. Nada é recalculado.
    supply_events = [{"date": _iso(reference), "quantity": stock, "source": "estoque", "ref": None}] if stock > 0 else []
    supply_events += [{"date": _iso(max(op["finish"], reference)), "quantity": op["quantity"], "source": "op", "ref": op["order"]}
                      for op in ops if op["finish"] is not None]
    supply_events += [{"date": order["due_date"], "quantity": order["quantity"], "source": "planejada", "ref": None} for order in planned]
    source_order = {"estoque": 0, "op": 1, "planejada": 2}
    supply_events.sort(key=lambda event: (event["date"], source_order[event["source"]]))
    open_orders = [{"order": order["order"], "client": order["client"], "quantity": order["quantity"], "promised_date": _iso(order["promised_date"])}
                   for order in orders]

    antecipation = any(item["adjustment"] == "antecipar" for item in adjustments)
    reductions = [item for item in adjustments if item["adjustment"] in ("reduzir", "cancelar")]
    signals = []
    if early_shortfall or early_late_orders:
        signals.append("PROJECTED_SHORTFALL")
    if discontinued and ops:
        signals.append("OP_FOR_DISCONTINUED")
    if any(item["cause"] == "excesso_projetado" for item in reductions):
        signals.append("PROJECTED_EXCESS")

    # Cascata da quantidade na janela que uma ordem decidida agora cobre: até a chegada mais cedo + cobertura-alvo.
    cover_end = min(earliest + timedelta(days=settings["target_cover_weeks"] * 7), horizon_end)
    window_days = [day for day in days if day <= cover_end]
    demand_to_cover = sum(demand.get(day, 0.0) for day in window_days)
    open_in_time = sum(quantity for day, quantity in op_receipts.items() if day <= cover_end)
    urgent_orders = [order for order in planned if order["urgent"]]
    return {
        "sku": indicator.get("SKU"),
        "reference_date": _iso(reference), "horizon_end": _iso(horizon_end), "earliest_arrival": _iso(earliest),
        "decision_window_end": _iso(window_end), "cover_end": _iso(cover_end),
        "lead_time_days": lead_time, "daily_demand": round(daily, 2), "safety_stock_quantity": round(safety, 1),
        "discontinued": discontinued, "current_stock": stock, "minimum_lot": lot,
        "first_shortfall_date": _iso(first_shortfall), "early_shortfall": bool(early_shortfall or early_late_orders),
        "affected_orders": reported_orders, "op_adjustments": adjustments, "planned_orders": planned,
        "supply_events": supply_events, "open_orders": open_orders,
        "antecipation": antecipation, "reductions": bool(reductions),
        "suggested_quantity": float(sum(order["quantity"] for order in urgent_orders)),
        "planned_quantity_horizon": float(sum(order["quantity"] for order in planned)),
        "calculation": {
            "cover_end": _iso(cover_end), "demand_to_cover": round(demand_to_cover, 1), "safety_stock_quantity": round(safety, 1),
            "current_stock": stock, "open_production_quantity": open_in_time,
            "raw_quantity": round(max(0.0, demand_to_cover + safety - stock - open_in_time), 1),
            "carteira_in_window": round(sum(carteira.get(day, 0.0) for day in window_days), 1),
        },
        "signals": signals,
        "projection": _weekly(days, carteira, extra, op_receipts, planned_receipts, base_levels, planned_levels, safety),
    }


def _orders_by_sku(backlog: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for _, row in _open(backlog).iterrows():
        result.setdefault(str(row["SKU"]), []).append({
            "order": str(row["Pedido"]), "client": str(row.get("Cliente/Canal") or ""), "quantity": float(row["Quantidade"]),
            "promised_date": _day(row.get("Data prometida")),
        })
    return result


def build_supply_plans(data: dict[str, pd.DataFrame], indicators: pd.DataFrame, forecasts: pd.DataFrame,
                       settings: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Plano por SKU. `indicators` precisa da demanda de referência (Etapa 15.2) e do status do produto."""
    settings = load_supply_settings() if settings is None else settings
    forecast_by_sku = {str(row["sku"]): row for row in forecasts.to_dict("records")}
    orders = _orders_by_sku(data["Carteira_Pedidos"])
    ops = _open(data["Ordens_Producao"])
    plans = {}
    for indicator in indicators.astype(object).where(indicators.notna(), None).to_dict("records"):
        sku = str(indicator["SKU"])
        plans[sku] = build_sku_plan(indicator, forecast_by_sku.get(sku), orders.get(sku, []), ops[ops["SKU"] == sku], settings)
    return plans


# ------------------------------------------------------------------------------------------ decisão


def decide(plan: dict[str, Any], issue_codes: set[str]) -> tuple[str, list[str]]:
    """Ação principal pela precedência do plano da Etapa 15 e as ações secundárias que também valem."""
    urgent = any(order["urgent"] for order in plan["planned_orders"])
    candidates = []
    if plan["antecipation"]:
        candidates.append("antecipar_op")
    if plan["early_shortfall"]:
        candidates.append("atraso_inevitavel")
    if urgent:
        candidates.append("produzir")
    if plan["reductions"]:
        candidates.append("rever_op")
    if plan["planned_orders"] and not urgent:
        candidates.append("produzir")
    if "EXCESS_COVERAGE" in issue_codes and not plan["reductions"]:
        candidates.append("monitorar_excesso")
    if not candidates:
        return "sem_acao_necessaria", []
    unique = list(dict.fromkeys(candidates))
    return unique[0], unique[1:]


def attach_partner_buildup(plans: dict[str, dict[str, Any]], partner_items: list[dict[str, Any]]) -> None:
    """Etapa 15.5: leva ao SKU os pares parceiro–SKU com estoque acumulando (sem distribuir o estoque do CD).

    O SKU ganha o sinal PARTNER_STOCK_BUILDUP e, se tem OP reduzida por excesso, a evidência do parceiro entra no motivo.
    """
    by_sku: dict[str, list[dict[str, Any]]] = {}
    for item in partner_items:
        if any(signal["code"] == "PARTNER_STOCK_BUILDUP" for signal in item.get("signals", [])):
            by_sku.setdefault(str(item["sku"]), []).append({
                "partner": item["partner"], "sell_through": None if item.get("sell_through_window") is None else round(item["sell_through_window"], 2),
                "stock_start": item.get("stock_start"), "stock_end": item.get("estimated_stock"),
                "coverage_days": None if item.get("coverage_days") is None else round(item["coverage_days"], 1),
            })
    for sku, plan in plans.items():
        pairs = by_sku.get(sku, [])
        plan["partner_buildup"] = pairs
        if not pairs:
            continue
        plan["signals"].append("PARTNER_STOCK_BUILDUP")
        note = "; ".join(f"{pair['partner']} vendeu {pair['sell_through']:.0%} do que recebeu e o estoque foi de {pair['stock_start']:g} para {pair['stock_end']:g} un."
                         for pair in pairs if pair["sell_through"] is not None and pair["stock_start"] is not None and pair["stock_end"] is not None)
        for adjustment in plan["op_adjustments"]:
            if adjustment["adjustment"] in ("reduzir", "cancelar") and note:
                adjustment["reason"] += f" Estoque acumulando no parceiro: {note}"
