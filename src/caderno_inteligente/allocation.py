"""Etapa 16.2 (núcleo): alocação sugerida do produto escasso entre os pedidos confirmados.

Oferta = as séries do plano de suprimento (`plan["supply_events"]`: estoque do CD na referência, OPs abertas na conclusão
prevista e ordens planejadas na data de chegada); nada é recalculado. Demanda = só a carteira aberta (`plan["open_orders"]`);
a previsão nunca é distribuída a clientes (decisão D1).

Cada pedido recebe uma pontuação transparente (`allocation_score`) com os componentes expostos como evidência; os pesos vêm de
`config/allocation.json`. O faturamento por cliente de `Vendas_24m` não entra: é um rateio uniforme e daria um peso falso.
Sem sell-out suficiente do par parceiro–SKU, a cobertura no parceiro não é inferida (componente `sem_sell_out`, 0 ponto).

Na ordem da pontuação, cada pedido consome primeiro as chegadas mais tardias que ainda chegam até a sua data (preserva a oferta
antecipada para os demais) e, se faltar, as primeiras chegadas depois dela. É sugestão para revisão humana: não reserva estoque
nem altera pedidos.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "allocation.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "weights": {"urgency": 3, "direct_channel": 2, "low_partner_coverage": 2, "partner_buildup_or_high_coverage": -3, "small_order": 1},
    "low_coverage_days": 30,
    "high_coverage_days": 90,
    "urgency_horizon_days": 30,
    "allow_partial": True,
}
DIRECT_CHANNEL_TYPE = "Canal direto"
UNKNOWN_REGION = "Não informada"
TOLERANCE = 1e-9

LIMITATION = "Alocação sugerida; não reserva estoque nem altera pedidos."
FIELD_NATURE = {
    "supply": {"nature": "calculado pelo plano de suprimento", "origin": "estoque do CD na referência + OPs abertas na conclusão prevista + ordens planejadas na chegada"},
    "orders": {"nature": "observado na fonte", "origin": "Carteira_Pedidos (pedidos abertos)"},
    "allocation_score": {"nature": "calculado: soma dos componentes com os pesos de config/allocation.json", "origin": "Carteira_Pedidos, Parceiros_Canais, partner_insights"},
    "urgencia": {"nature": "observado", "origin": "Carteira_Pedidos.Data prometida contra a data de referência"},
    "canal_direto": {"nature": "cadastral", "origin": "Parceiros_Canais.Tipo"},
    "cobertura_baixa_parceiro": {"nature": "estimado", "origin": "partner_insights.coverage_days, só com sell-out suficiente"},
    "estoque_acumulando_parceiro": {"nature": "estimado", "origin": "partner_insights (PARTNER_STOCK_BUILDUP ou cobertura alta), só com sell-out suficiente"},
    "sem_sell_out": {"nature": "ausente", "origin": "par parceiro–SKU sem sell-out suficiente; nunca inferido"},
    "pedido_pequeno": {"nature": "observado", "origin": "Carteira_Pedidos.Quantidade contra o maior pedido do SKU"},
    "allocated_now": {"nature": "calculado", "origin": "oferta que chega até max(data prometida, referência)"},
    "allocated_later": {"nature": "calculado", "origin": "chegadas depois da data prometida (OP ou ordem planejada)"},
    "uncovered_value_at_promise": {"nature": "calculado", "origin": "unidades descobertas × Precos_Produtos.Preço unitário (R$)"},
    "region": {"nature": "cadastral", "origin": "Parceiros_Canais.Região"},
}
SHORT_LABELS = {
    "canal_direto": "canal direto",
    "cobertura_baixa_parceiro": "cobertura baixa no parceiro",
    "estoque_acumulando_parceiro": "estoque acumulando no parceiro",
    "pedido_pequeno": "pedido pequeno",
}


# ------------------------------------------------------------------------------------------ configuração


def load_allocation_settings(path: str | Path | None = None) -> dict[str, Any]:
    values = json.loads(json.dumps(DEFAULT_SETTINGS))
    source = DEFAULT_PATH if path is None else Path(path)
    if source.exists() or path is not None:
        overrides = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(values):
            raise ValueError("Configuração da alocação contém campos desconhecidos")
        weights = overrides.pop("weights", {})
        if not isinstance(weights, dict) or set(weights) - set(values["weights"]):
            raise ValueError("Pesos da alocação contêm campos desconhecidos")
        values["weights"].update(weights)
        values.update(overrides)
    return _validate_settings(values)


def _validate_settings(values: dict[str, Any]) -> dict[str, Any]:
    def number(value: Any, key: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Parâmetro da alocação inválido: {key}")
        return float(value)

    values["weights"] = {key: number(value, f"weights.{key}") for key, value in values["weights"].items()}
    for key in ("low_coverage_days", "high_coverage_days", "urgency_horizon_days"):
        if number(values[key], key) != int(values[key]) or values[key] < 1:
            raise ValueError(f"Parâmetro precisa ser inteiro ≥ 1: {key}")
        values[key] = int(values[key])
    if values["low_coverage_days"] >= values["high_coverage_days"]:
        raise ValueError("low_coverage_days deve ser menor que high_coverage_days")
    if not isinstance(values["allow_partial"], bool):
        raise ValueError("allow_partial deve ser verdadeiro ou falso")
    return values


# ------------------------------------------------------------------------------------------ apoio


def _day(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _br(value: date | None) -> str:
    return "—" if value is None else f"{value.day:02d}/{value.month:02d}"


def _units(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def _component(name: str, points: float, value: Any, nature: str, reason: str) -> dict[str, Any]:
    return {"component": name, "points": round(float(points), 4), "value": value, "nature": nature, "reason": reason}


# ------------------------------------------------------------------------------------------ pontuação


def score_order(order: dict[str, Any], client_meta: dict[str, Any] | None, partner_row: dict[str, Any] | None,
                settings: dict[str, Any], reference_date: str | date) -> tuple[float, list[dict[str, Any]]]:
    """Pontuação do pedido e seus componentes. `order["max_quantity"]` é o maior pedido do SKU (para `pedido_pequeno`)."""
    weights = settings["weights"]
    reference = _day(reference_date)
    components = []

    promised = _day(order.get("promised_date"))
    if promised is None:
        components.append(_component("urgencia", 0.0, None, "ausente", "Pedido sem data prometida: sem ponto de urgência."))
    else:
        days = (promised - reference).days
        factor = 1.0 if days <= 0 else max(0.0, 1 - days / settings["urgency_horizon_days"])
        if days < 0:
            text = f"Vencido em {_br(promised)}, {-days} dias antes da referência."
        elif days == 0:
            text = f"Prometido para a data de referência ({_br(promised)})."
        else:
            text = f"Prometido para {_br(promised)}, {days} dias após a referência (horizonte de urgência de {settings['urgency_horizon_days']} dias)."
        components.append(_component("urgencia", weights["urgency"] * factor, days, "observado", text))

    client_type = None if client_meta is None else client_meta.get("Tipo")
    direct = client_type == DIRECT_CHANNEL_TYPE
    components.append(_component(
        "canal_direto", weights["direct_channel"] if direct else 0.0, client_type, "cadastral" if client_type else "ausente",
        "Canal direto: a falta é venda perdida ao consumidor." if direct
        else f"{client_type or 'Tipo não cadastrado'}: não é canal direto."))

    if not direct:
        sufficient = partner_row is not None and partner_row.get("data_quality") == "sufficient"
        coverage = None if partner_row is None else partner_row.get("coverage_days")
        if not sufficient or coverage is None:
            quality = None if partner_row is None else partner_row.get("data_quality")
            detail = "sem linha de sell-out do par" if partner_row is None else f"sell-out {'desatualizado' if quality == 'stale' else 'insuficiente'}"
            components.append(_component("sem_sell_out", 0.0, quality, "ausente",
                                         f"Sem dado do parceiro ({detail}); a cobertura no parceiro não é inferida."))
        else:
            low = coverage <= settings["low_coverage_days"]
            components.append(_component(
                "cobertura_baixa_parceiro", weights["low_partner_coverage"] if low else 0.0, round(coverage, 1), "estimado",
                f"Cobertura estimada de {coverage:.0f} dias no parceiro ({'até' if low else 'acima de'} {settings['low_coverage_days']} dias)."))
            buildup = any(signal.get("code") == "PARTNER_STOCK_BUILDUP" for signal in partner_row.get("signals") or [])
            high = coverage >= settings["high_coverage_days"]
            if buildup:
                text = "Estoque acumulando no parceiro: atende depois dos demais."
            elif high:
                text = f"Cobertura estimada de {coverage:.0f} dias no parceiro (≥ {settings['high_coverage_days']} dias): atende depois dos demais."
            else:
                text = "Sem estoque acumulando nem cobertura alta no parceiro."
            components.append(_component("estoque_acumulando_parceiro", weights["partner_buildup_or_high_coverage"] if buildup or high else 0.0,
                                         "PARTNER_STOCK_BUILDUP" if buildup else round(coverage, 1), "estimado", text))

    quantity = float(order["quantity"])
    largest = max(float(order.get("max_quantity") or quantity), quantity)
    share = 1 - quantity / largest if largest > 0 else 0.0
    components.append(_component("pedido_pequeno", weights["small_order"] * share, quantity, "observado",
                                 f"{_units(quantity)} un. contra o maior pedido do SKU de {_units(largest)} un."))
    return round(sum(item["points"] for item in components), 4), components


# ------------------------------------------------------------------------------------------ alocação


def _events(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"date": _day(event["date"]), "left": float(event["quantity"]), "source": event["source"], "ref": event.get("ref")}
            for event in plan.get("supply_events") or [] if float(event["quantity"]) > 0]


def _serve(events: list[dict[str, Any]], order: dict[str, Any], reference: date, allow_partial: bool) -> dict[str, Any]:
    """Consome a oferta para um pedido: chegadas até a data mais tardias primeiro; o que faltar, das primeiras depois."""
    promised = _day(order["promised_date"])
    deadline = max(promised, reference)
    need = float(order["quantity"])
    before = [event for event in events if event["date"] <= deadline]
    after = [event for event in events if event["date"] > deadline]
    available = sum(event["left"] for event in before)
    target = need if available + TOLERANCE >= need else (available if allow_partial else 0.0)
    now, later, last = 0.0, [], None
    for event in reversed(before):
        if target - now <= TOLERANCE:
            break
        take = min(event["left"], target - now)
        if take > TOLERANCE:
            event["left"] -= take
            now += take
            last = event["date"] if last is None else max(last, event["date"])
    remaining = need - now
    for event in after:
        if remaining <= TOLERANCE:
            break
        take = min(event["left"], remaining)
        if take > TOLERANCE:
            event["left"] -= take
            remaining -= take
            later.append({"quantity": round(take, 4), "expected_date": _iso(max(event["date"], reference)), "source_ref": event["ref"],
                          "source": event["source"]})
            last = event["date"]
    covered = remaining <= TOLERANCE
    expected = max(last, reference) if covered and last is not None else (reference if covered else None)
    delay = None if expected is None else max(0, (expected - promised).days)
    return {"allocated_now": round(now, 4), "uncovered_at_promise": round(max(0.0, need - now), 4), "allocated_later": later,
            "expected_date": _iso(expected), "delay_days": delay}


def _fifo_uncovered(plan: dict[str, Any], reference: date) -> dict[str, float]:
    """Unidades descobertas na data prometida atendendo a carteira por data prometida (a regra atual, sem escolha)."""
    events = _events(plan)
    dated = [item for item in plan.get("open_orders") or [] if _day(item.get("promised_date")) is not None]
    orders = sorted(dated, key=lambda item: (_day(item["promised_date"]), item["order"]))
    return {order["order"]: _serve(events, order, reference, True)["uncovered_at_promise"] for order in orders}


def allocate_sku(plan: dict[str, Any], orders_scored: list[dict[str, Any]], allow_partial: bool) -> list[dict[str, Any]]:
    """Atende os pedidos na ordem da pontuação (desempate: data prometida, pedido) e devolve o resultado por pedido.

    Pedido sem data prometida fica fora, como no plano de suprimento (que também não o projeta).
    """
    orders_scored = [item for item in orders_scored if _day(item.get("promised_date")) is not None]
    reference = _day(plan["reference_date"])
    events = _events(plan)
    fifo = {item["order"]: item for item in plan.get("affected_orders") or []}
    ranked = sorted(orders_scored, key=lambda item: (-round(item["allocation_score"], 6), _day(item["promised_date"]), item["order"]))
    result = []
    for rank, order in enumerate(ranked, start=1):
        served = _serve(events, order, reference, allow_partial)
        late = fifo.get(order["order"])
        row = {**order, "rank": rank, **served, "fifo_delay_days": 0 if late is None else late["delay_days"]}
        row["reason"] = _order_reason(row)
        result.append(row)
    return result


def _order_reason(row: dict[str, Any]) -> str:
    drivers = []
    for item in sorted(row["score_components"], key=lambda part: -abs(part["points"])):
        if item["component"] == "sem_sell_out":
            continue
        if item["points"] == 0:
            continue
        if item["component"] == "urgencia":
            days = item["value"]
            drivers.append("urgência (vencido)" if days < 0 else "urgência (vence na referência)" if days == 0 else f"urgência (vence em {days} dias)")
        else:
            drivers.append(SHORT_LABELS[item["component"]] + (" (atende depois)" if item["points"] < 0 else ""))
    text = f"{row['rank']}º na fila, pontuação {row['allocation_score']:g}"
    text += f": {', '.join(drivers)}." if drivers else ": nenhum componente pontuou; vale a data prometida."
    if any(item["component"] == "sem_sell_out" for item in row["score_components"]):
        text += " Sem dado do parceiro: cobertura não inferida."
    quantity = float(row["quantity"])
    if row["uncovered_at_promise"] <= TOLERANCE and row["delay_days"]:
        text += f" Atendido integralmente ({_units(quantity)} un.) na data de referência; o pedido já estava vencido há {row['delay_days']} dia(s)."
    elif row["uncovered_at_promise"] <= TOLERANCE:
        text += f" Atendido integralmente ({_units(quantity)} un.) até a data prometida."
    elif row["expected_date"] is None:
        text += f" Recebe {_units(row['allocated_now'])} un. até a data prometida; {_units(row['uncovered_at_promise'] - sum(part['quantity'] for part in row['allocated_later']))} un. ficam sem cobertura no horizonte."
    else:
        refs = ", ".join(dict.fromkeys(part["source_ref"] or "ordem planejada" for part in row["allocated_later"]))
        if row["allocated_now"] > TOLERANCE:
            text += f" Recebe {_units(row['allocated_now'])} un. até a data prometida e o restante em {_br(_day(row['expected_date']))} ({refs})."
        else:
            text += f" Nada chega a tempo para ele; recebe tudo em {_br(_day(row['expected_date']))} ({refs})."
    fifo = row["fifo_delay_days"]
    if fifo != row["delay_days"]:
        before = "sem cobertura no horizonte" if fifo is None else f"atraso de {fifo} dias"
        text += f" Pela data prometida (regra atual): {before}."
    return text


def _has_partner_coverage(row: dict[str, Any]) -> bool:
    return any(part["component"] in ("cobertura_baixa_parceiro", "estoque_acumulando_parceiro") for part in row["score_components"])


def _decision_text(orders: list[dict[str, Any]], has_shortfall: bool) -> str:
    if not orders:
        return "Sem pedidos abertos"
    if not has_shortfall:
        return "Todos os pedidos são atendidos na data prometida; não há escolha a fazer"
    parts = []
    for row in orders:
        client, quantity = row["client"], float(row["quantity"])
        if row["uncovered_at_promise"] <= TOLERANCE:
            parts.append(f"Atender {client} ({_units(quantity)} un.) integralmente")
            continue
        refs = " e ".join(dict.fromkeys(f"a {part['source_ref']}" if part["source_ref"] else "a ordem planejada" for part in row["allocated_later"]))
        if row["expected_date"] is None:
            parts.append(f"{client} recebe {_units(row['allocated_now'])} un. agora e o restante fica sem cobertura no horizonte")
        elif row["allocated_now"] > TOLERANCE:
            parts.append(f"{client} recebe {_units(row['allocated_now'])} un. agora e o restante em {_br(_day(row['expected_date']))} com {refs}")
        else:
            parts.append(f"{client} ({_units(quantity)} un.) recebe em {_br(_day(row['expected_date']))} com {refs}")
    return "; ".join(parts)


# ------------------------------------------------------------------------------------------ resultado


def build_allocation(plans: dict[str, dict[str, Any]], partners: pd.DataFrame, partner_items: list[dict[str, Any]],
                     prices: dict[str, float | None], settings: dict[str, Any], reference_date: str) -> dict[str, Any]:
    reference = _day(reference_date)
    registry = {str(row["Código"]): row for row in partners.to_dict("records")}
    pairs = {(str(item["partner"]), str(item["sku"])): item for item in partner_items}
    skus: dict[str, dict[str, Any]] = {}
    for sku, plan in sorted(plans.items()):
        open_orders = plan.get("open_orders") or []
        if not open_orders:
            continue
        plan = {**plan, "reference_date": plan.get("reference_date") or _iso(reference)}
        largest = max(float(order["quantity"]) for order in open_orders)
        scored = []
        for order in open_orders:
            meta = registry.get(order["client"])
            row = pairs.get((order["client"], sku))
            score, components = score_order({**order, "max_quantity": largest}, meta, row, settings, reference)
            region = None if meta is None else meta.get("Região")
            scored.append({
                "order": order["order"], "client": order["client"], "client_type": None if meta is None else meta.get("Tipo"),
                "region": region if isinstance(region, str) and region.strip() else UNKNOWN_REGION,
                "quantity": float(order["quantity"]), "promised_date": order.get("promised_date"),
                "allocation_score": score, "score_components": components,
            })
        # Pedidos afetados antes da alocação: os do plano (inclui vencidos na referência); sem eles, o FIFO por data prometida.
        if "affected_orders" in plan:
            affected = plan["affected_orders"]
        else:
            fifo = _fifo_uncovered(plan, reference)
            affected = [order for order in open_orders if fifo.get(order["order"], 0.0) > TOLERANCE]
        has_shortfall = bool(affected)
        contested = len({order["client"] for order in affected}) >= 2
        orders = allocate_sku(plan, scored, settings["allow_partial"])
        # Sell-out suficiente = a cobertura no parceiro entrou na pontuação; canal direto não tem esse componente e não conta.
        with_data = sum(1 for row in orders if _has_partner_coverage(row))
        price = prices.get(sku)
        price = None if price is None or (isinstance(price, float) and math.isnan(price)) else float(price)
        uncovered = round(sum(row["uncovered_at_promise"] for row in orders), 4)
        clients = list(dict.fromkeys(row["client"] for row in orders))  # distintos, na ordem de atendimento
        note = f"{with_data} de {len(orders)} pedidos têm sell-out suficiente do parceiro"
        note += "." if with_data == len(orders) else "; nos demais, urgência, canal e tamanho do pedido decidem a ordem (sem dado do parceiro não vira ponto)."
        undated = [order["order"] for order in open_orders if _day(order.get("promised_date")) is None]
        if undated:
            note += f" Sem data prometida, fora da alocação: {', '.join(undated)}."
        skus[sku] = {
            "sku": sku, "has_shortfall": has_shortfall, "contested": contested, "clients": clients, "unit_price": price,
            "orders": orders, "uncovered_units_at_promise": uncovered,
            "uncovered_value_at_promise": None if price is None else round(uncovered * price, 2),
            "decision_text": _decision_text(orders, has_shortfall),
            "first_client": clients[0] if clients else None, "last_client": clients[-1] if len(clients) >= 2 else None,
            "orders_with_partner_data": with_data, "data_note": note, "orders_without_date": undated,
        }
        if price is None:
            skus[sku]["missing_price_reason"] = "Sem preço vigente em Precos_Produtos para o SKU."

    regions: dict[str, dict[str, Any]] = {}
    by_partner: dict[str, dict[str, Any]] = {}
    missing_price = sorted(sku for sku, item in skus.items() if item["unit_price"] is None and item["uncovered_units_at_promise"] > TOLERANCE)

    def bucket(store: dict[str, dict[str, Any]], key: str, **extra: Any) -> dict[str, Any]:
        return store.setdefault(key, {**extra, "uncovered_units": 0.0, "uncovered_value": 0.0, "orders": 0, "skus": [], "_priced": True})

    for sku, item in skus.items():
        for row in item["orders"]:
            if row["uncovered_at_promise"] <= TOLERANCE:
                continue
            for target in (bucket(regions, row["region"], region=row["region"]),
                           bucket(by_partner, row["client"], partner=row["client"], type=row["client_type"], region=row["region"])):
                target["uncovered_units"] += row["uncovered_at_promise"]
                target["orders"] += 1
                if sku not in target["skus"]:
                    target["skus"].append(sku)
                if item["unit_price"] is None:
                    target["_priced"] = False
                else:
                    target["uncovered_value"] += row["uncovered_at_promise"] * item["unit_price"]
    contested_skus = sorted(sku for sku, item in skus.items() if item["contested"])
    for sku in contested_skus:
        first = skus[sku]["first_client"]
        meta = registry.get(first) or {}
        region = meta.get("Região") if isinstance(meta.get("Região"), str) and meta.get("Região").strip() else UNKNOWN_REGION
        entry = by_partner.setdefault(first, {"partner": first, "type": meta.get("Tipo"), "region": region, "uncovered_units": 0.0,
                                              "uncovered_value": 0.0, "orders": 0, "skus": [], "_priced": True})
        entry.setdefault("first_in_contested", []).append(sku)

    def finish(entry: dict[str, Any]) -> dict[str, Any]:
        priced = entry.pop("_priced")
        entry["uncovered_units"] = round(entry["uncovered_units"], 4)
        entry["uncovered_value"] = round(entry["uncovered_value"], 2) if priced else None
        return entry

    region_rows = sorted((finish(entry) for entry in regions.values()), key=lambda entry: (-entry["uncovered_units"], entry["region"]))
    partner_rows = []
    for entry in by_partner.values():
        entry = finish(entry)
        partner_rows.append({"partner": entry["partner"], "type": entry["type"], "region": entry["region"], "uncovered_orders": entry["orders"],
                             "uncovered_units": entry["uncovered_units"], "uncovered_value": entry["uncovered_value"], "skus": entry["skus"],
                             "first_in_contested": entry.get("first_in_contested", [])})
    partner_rows.sort(key=lambda entry: (-entry["uncovered_units"], entry["partner"]))

    uncovered_rows = [row for item in skus.values() for row in item["orders"] if row["uncovered_at_promise"] > TOLERANCE]
    total_units = round(sum(row["uncovered_at_promise"] for row in uncovered_rows), 4)
    total_value = None if missing_price else round(sum(item["uncovered_value_at_promise"] or 0.0 for item in skus.values()), 2)
    with_data = sum(1 for row in uncovered_rows if _has_partner_coverage(row))
    limitations = [
        LIMITATION,
        "Distribui só o estoque do CD, as OPs abertas e as ordens planejadas entre pedidos confirmados; a demanda prevista não é alocada a clientes.",
        "A oferta das ordens planejadas depende de uma liberação que ainda não foi feita.",
        "O faturamento por cliente de Vendas_24m não é usado como peso: é um rateio uniforme e daria um peso falso.",
        f"Só {with_data} de {len(uncovered_rows)} pedidos descobertos têm sell-out suficiente do parceiro; nos demais a cobertura no parceiro "
        "não é inferida e a urgência, o canal e o tamanho do pedido decidem a ordem.",
    ]
    if missing_price:
        limitations.append(f"Sem preço vigente para {', '.join(missing_price)}: o valor descoberto fica indisponível (não vira zero).")
    return {
        "reference_date": _iso(reference), "settings": settings, "skus": skus,
        "regions": region_rows, "partners": partner_rows,
        "totals": {"uncovered_units": total_units, "uncovered_value": total_value, "orders": len(uncovered_rows),
                   "skus": sum(1 for item in skus.values() if item["uncovered_units_at_promise"] > TOLERANCE),
                   "contested_skus": contested_skus,
                   "shortfall_skus": sorted(sku for sku, item in skus.items() if item["has_shortfall"])},
        "field_nature": FIELD_NATURE,
        "limitations": limitations,
        "requires_human_review": True,
    }
