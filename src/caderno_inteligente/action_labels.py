"""Rótulos de ação do desafio como camada derivada dos sinais já calculados.

Não é um motor novo: lê a ação operacional, a ação comercial, os alertas de evento e os sinais dos canais diretos e
emite um segundo campo (`challenge_action`) com rótulo, sinais usados, evidências e limitações. Os campos `action`
existentes, o score, o ranking e as quantidades não são alterados. Dado insuficiente sempre vence: sem evidência, o
rótulo é "Investigar" com o motivo, nunca uma oportunidade inferida.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SETTINGS: dict[str, Any] = {
    "priority_top_n": 10,
    "event_decision_window_days": 30,
    "partner_min_opportunities": 2,
    "recompra_min_sell_in_months": 3,
    "recompra_min_months_without_sell_in": 2,
}

LABELS = {
    "produzir": "Produzir",
    "repor": "Repor",
    "priorizar_producao": "Priorizar produção",
    "priorizar_parceiro": "Priorizar parceiro",
    "ampliar_mix": "Ampliar mix",
    "recomendar_recompra": "Recomendar recompra",
    "reativar": "Reativar",
    "monitorar": "Monitorar",
    "investigar": "Investigar",
    "sem_acao_necessaria": "Sem ação necessária",
}
# As nove ações do PDF do desafio; "Reativar" vem das oportunidades de reativação do mesmo documento.
CHALLENGE_PDF_CODES = ("produzir", "repor", "priorizar_producao", "priorizar_parceiro", "ampliar_mix", "recomendar_recompra", "monitorar", "investigar", "sem_acao_necessaria")

DEFINITIONS = {
    "produzir": "Há ordem planejada a liberar dentro da janela de decisão.",
    "repor": "O estoque estimado do parceiro cobre poucos dias do giro observado; avaliar reposição comercial.",
    "priorizar_producao": "Produzir com urgência: há alavanca real de produção (antecipar uma OP, garantir quantidade para pedido sem cobertura) ou decisão de evento próxima.",
    "priorizar_parceiro": "Decidir quem atender com o estoque existente (pedidos sem cobertura disputados) ou parceiro com várias oportunidades de reposição.",
    "ampliar_mix": "Produto ativo sem nenhum faturamento em um canal com visibilidade completa; avaliar incluí-lo no mix.",
    "recomendar_recompra": "O parceiro vende bem, mas parou de receber sell-in há mais tempo que o ritmo do próprio par; recomendar nova compra.",
    "reativar": "O SKU vendia no canal e ficou meses sem faturar; avaliar reativação.",
    "monitorar": "Sem urgência: excesso de estoque, saída de linha, crescimento ou próxima ordem planejada fora da janela.",
    "investigar": "Faltam dados ou há divergência; investigar antes de decidir. Nenhuma oportunidade é inferida.",
    "sem_acao_necessaria": "Nenhum sinal que justifique ação neste horizonte.",
}

PRECEDENCE = {
    "operational": ["investigar (dado insuficiente)", "priorizar parceiro (pedido sem cobertura disputado por 2 ou mais clientes)", "priorizar produção (antecipar OP)",
                    "priorizar produção (pedido sem cobertura e ordem urgente)", "monitorar (pedido sem cobertura e sem produção: renegociar)",
                    "produzir ou monitorar (falta só na previsão)", "investigar (rever OP)", "priorizar produção (ordem urgente, faixa 1 ou evento na janela)",
                    "produzir (ordem a liberar na janela de decisão; depois dela, monitorar)", "monitorar (excesso)", "sem ação necessária"],
    "commercial": ["investigar (dado antigo, insuficiente ou divergente)", "investigar (estoque acumulando no parceiro)", "repor", "recomendar recompra", "monitorar"],
    "partner": ["priorizar parceiro (várias reposições com SKU de alta prioridade)"],
    "channel": ["ampliar mix", "reativar", "monitorar saída de linha", "investigar queda", "monitorar crescimento", "sem ação necessária"],
}

# Alavancas de decisão (P3): o que o usuário pode fazer agora.
LEVERS = ("alocar", "antecipar_op", "produzir_agora", "renegociar", "produzir_futuro", "rever_op", "nenhuma")

LIMITATIONS = {
    "operational": [
        "Não cria nem libera ordem de produção; a quantidade oficial não muda.",
        "Capacidade da família é só contexto e não comprova viabilidade individual.",
    ],
    "commercial": [
        "Estoque do parceiro é estimado, não é o estoque do CD.",
        "Ausência de registro não é venda zero; nenhum parceiro sem sell-out recebe oportunidade inferida.",
        "Sugestão demonstrativa; exige revisão humana.",
    ],
    "partner": [
        "Conta apenas pares parceiro–SKU com sell-out suficiente; ausência de dado não conta como oportunidade.",
        "A prioridade do SKU vem do ranking oficial e não é alterada.",
    ],
    "channel": [
        "A visibilidade vem do faturamento; os canais diretos não têm sell-in nem sell-out.",
        "Sem estoque por canal. Sugestão demonstrativa; exige revisão humana.",
    ],
}


def load_action_settings(path: str | Path | None = None) -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    if path is not None:
        overrides = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(values):
            raise ValueError("Configuração dos rótulos de ação contém campos desconhecidos")
        values.update(overrides)
    return _validate_settings(values)


def _validate_settings(values: dict[str, Any]) -> dict[str, Any]:
    if set(values) != set(DEFAULT_SETTINGS):
        raise ValueError("Parâmetro dos rótulos de ação desconhecido")
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
            raise ValueError(f"Parâmetro dos rótulos de ação deve ser inteiro: {key}")
        values[key] = int(value)
    if values["priority_top_n"] < 1 or values["partner_min_opportunities"] < 1 or values["recompra_min_sell_in_months"] < 2:
        raise ValueError("Limites mínimos dos rótulos de ação inválidos")
    if values["event_decision_window_days"] < 0 or values["recompra_min_months_without_sell_in"] < 1:
        raise ValueError("Janela dos rótulos de ação inválida")
    return values


def _result(code: str, source: str, origin_action: str | None, signals: list[str], evidence: list[dict[str, Any]], reason: str, extra_limitations: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "code": code, "label": LABELS[code], "source": source, "origin_action": origin_action, "reason": reason,
        "signals_used": signals, "evidence": evidence, "limitations": [*LIMITATIONS[source], *extra_limitations],
        "requires_human_review": True,
    }


def _ev(label: str, value: Any, origin: str) -> dict[str, Any]:
    return {"label": label, "value": value, "origin": origin}


# --------------------------------------------------------------- SKU (operacional)

def label_operational(
    action: str, priority: int | None, forecast_status: str | None, event_alerts: list[dict] | None, capacity_status: str | None,
    reference_date: date | None, settings: dict[str, Any], context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ação operacional do SKU → rótulo do desafio. `event_alerts` None significa análise de eventos indisponível.

    Com `context` (ver `build_lever_context`) vale a tabela de decisão por alavanca; sem ele, o caminho legado, que só ganha `lever`/`decide_by` None.
    """
    if context is not None:
        return _label_by_lever(action, priority, forecast_status, event_alerts, capacity_status, reference_date, settings, context)
    return {**_label_operational_legacy(action, priority, forecast_status, event_alerts, capacity_status, reference_date, settings),
            "lever": None, "decide_by": None, "decide_by_reason": None}


def _label_operational_legacy(
    action: str, priority: int | None, forecast_status: str | None, event_alerts: list[dict] | None, capacity_status: str | None,
    reference_date: date | None, settings: dict[str, Any],
) -> dict[str, Any]:
    if action == "investigar_dados" or forecast_status == "insufficient_data":
        return _result("investigar", "operational", action, ["INSUFFICIENT_FORECAST_HISTORY"], [_ev("Previsão", "histórico insuficiente", "forecasting")],
                       "Histórico insuficiente para prever; investigar e completar os dados antes de sugerir produção.")
    if action in ("atraso_inevitavel", "antecipar_op"):
        reason = ("Falta antes que qualquer reposição nova chegue: garantir a OP, priorizar os pedidos e renegociar prazos com os clientes afetados."
                  if action == "atraso_inevitavel" else "Uma OP ainda não iniciada pode chegar antes da falta: antecipar o início.")
        evidence = [] if priority is None else [_ev("Posição na fila de atenção", priority, "ranking oficial")]
        return _result("priorizar_producao", "operational", action, ["PROJECTED_SHORTFALL" if action == "atraso_inevitavel" else "OP_ANTICIPATION"], evidence, reason,
                       ["A data da falta vem da projeção diária: carteira na data prometida, previsão rateada e OPs na conclusão prevista."])
    if action == "rever_op":
        return _result("investigar", "operational", action, ["OP_REVIEW"], [] if priority is None else [_ev("Posição na fila de atenção", priority, "ranking oficial")],
                       "Rever a OP: ela supera a necessidade projetada ou é de produto em descontinuação. Não produzir antes de confirmar.")
    if action in ("produzir", "produzir_validar_capacidade"):
        signals, evidence, reasons = [f"operational_action:{action}"], [], []
        extra = ["A capacidade da família está pressionada: validar antes de executar."] if action == "produzir_validar_capacidade" or capacity_status == "requires_review" else []
        if priority is not None:
            evidence.append(_ev("Posição na fila de atenção", priority, "ranking oficial"))
            if priority <= settings["priority_top_n"]:
                signals.append(f"priority_top_{settings['priority_top_n']}")
                reasons.append(f"posição {priority} na fila de atenção (limite {settings['priority_top_n']})")
        urgent_event = None
        if event_alerts and reference_date is not None:
            limit = reference_date + timedelta(days=settings["event_decision_window_days"])
            for alert in sorted(event_alerts, key=lambda item: item.get("decision_date") or "9999"):
                if alert.get("decision_date") and alert.get("in_horizon") and date.fromisoformat(alert["decision_date"]) <= limit:
                    urgent_event = alert
                    break
        if urgent_event:
            signals.append(f"event_decision:{urgent_event['event_id']}")
            evidence.append(_ev(f"Decisão de {urgent_event['event']}", urgent_event["decision_date"], "Calendario_Eventos − lead time"))
            reasons.append(f"decisão de {urgent_event['event']} até {urgent_event['decision_date']} (janela de {settings['event_decision_window_days']} dias)")
        if event_alerts is None:
            extra.append("A análise de eventos estava indisponível; o critério de evento não foi avaliado.")
        if reasons:
            return _result("priorizar_producao", "operational", action, signals, evidence, "Produzir com urgência: " + "; ".join(reasons) + ".", extra)
        return _result("produzir", "operational", action, signals, evidence, "Há necessidade líquida de produção no próximo mês, sem urgência de fila ou de evento.", extra)
    if action == "monitorar_excesso":
        return _result("monitorar", "operational", action, ["EXCESS_COVERAGE"], [], "Excesso de cobertura; acompanhar sem produzir.")
    return _result("sem_acao_necessaria", "operational", action, [], [], "Sem necessidade de produção neste horizonte; os riscos do SKU continuam.")


# --------------------------------------------------------------- SKU (tabela de decisão por alavanca)

def build_lever_context(plan: dict[str, Any], allocation_sku: dict[str, Any] | None, tier_info: dict[str, Any] | None,
                        capacity_status: str | None, reference_date: date | str | None) -> dict[str, Any]:
    """Resume plano de suprimento, alocação e faixa de urgência nos fatos que a tabela de alavancas consome. Nada é recalculado."""
    if allocation_sku is not None:
        uncovered = [
            {"order": item["order"], "client": item["client"], "quantity": item["quantity"], "uncovered_at_promise": item["uncovered_at_promise"], "promised_date": item.get("promised_date")}
            for item in allocation_sku.get("orders", []) if (item.get("uncovered_at_promise") or 0) > 0
        ]
    else:  # sem alocação: pedidos afetados do plano; a parcela descoberta não é conhecida e não vira zero
        uncovered = [{"order": item["order"], "client": item["client"], "quantity": item["quantity"], "uncovered_at_promise": None, "promised_date": item.get("promised_date")}
                     for item in plan.get("affected_orders", [])]
    planned = plan.get("planned_orders", [])
    urgent = sorted((order for order in planned if order.get("urgent")), key=lambda order: order["release_date"])
    contested = bool(allocation_sku and allocation_sku.get("contested")) and bool(uncovered)
    return {
        "urgency_tier": (tier_info or {}).get("tier"), "discontinued": bool(plan.get("discontinued")), "uncovered_orders": uncovered,
        "contested": contested, "decision_text": allocation_sku.get("decision_text") if allocation_sku else None,
        "first_client": allocation_sku.get("first_client") if allocation_sku else None, "last_client": allocation_sku.get("last_client") if allocation_sku else None,
        "urgent_planned_quantity": float(sum(order["quantity"] for order in urgent)),
        "next_urgent_release_date": urgent[0]["release_date"] if urgent else None,
        "first_planned_release_date": min((order["release_date"] for order in planned), default=None),
        "anticipable_ops": [item["order"] for item in plan.get("op_adjustments", []) if item.get("adjustment") == "antecipar"],
        "forecast_only_shortfall": bool(plan.get("early_shortfall")) and not uncovered,
        "first_shortfall_date": plan.get("first_shortfall_date"), "decision_window_end": plan.get("decision_window_end"),
        "capacity_status": capacity_status, "reference_date": reference_date.isoformat() if isinstance(reference_date, date) else reference_date,
    }


def _lever(label: dict[str, Any], lever: str, decide_by: str | None, decide_by_reason: str | None) -> dict[str, Any]:
    return {**label, "lever": lever, "decide_by": decide_by, "decide_by_reason": decide_by_reason}


def _earliest_promise(orders: list[dict[str, Any]], reference: str | None) -> tuple[str | None, bool]:
    """Menor data prometida entre os pedidos descobertos; vencida → a própria referência. Devolve (data, vencida)."""
    promised = min((item["promised_date"] for item in orders if item.get("promised_date")), default=None)
    if promised is not None and reference is not None and promised < reference:
        return reference, True
    return promised, False


def _capacity_note(label: dict[str, Any], capacity_status: str | None) -> dict[str, Any]:
    if capacity_status != "insuficiente_estimado" or label["code"] not in ("priorizar_producao", "produzir"):
        return label
    return {**label, "limitations": [*label["limitations"], "Não cabe nem na capacidade estimada"],
            "evidence": [*label["evidence"], _ev("Capacidade da família", "não cabe nem na capacidade estimada", "capacity_plan, semanas estimadas")]}


def _label_by_lever(action, priority, forecast_status, event_alerts, capacity_status, reference_date, settings, context) -> dict[str, Any]:
    # a data de planejamento do plano (contexto) manda nos prazos; a referência dos eventos só vale sem ela
    reference = context.get("reference_date") or (reference_date.isoformat() if reference_date is not None else None)
    uncovered = context.get("uncovered_orders") or []
    discontinued = bool(context.get("discontinued"))
    urgent_qty = context.get("urgent_planned_quantity") or 0
    tier = context.get("urgency_tier")
    base_evidence = [] if priority is None else [_ev("Posição na fila de atenção", priority, "ranking oficial")]
    if tier is not None:
        base_evidence.append(_ev("Faixa de urgência", tier, "impact.urgency_tier"))
    if uncovered:
        base_evidence.append(_ev("Pedidos sem cobertura na data prometida", ", ".join(f"{item['order']} ({item['client']})" for item in uncovered), "Carteira_Pedidos, alocação"))
    promised, overdue = _earliest_promise(uncovered, reference)
    promise_reason = None if promised is None else ("pedido já vencido: decidir hoje" if overdue else "menor data prometida entre os pedidos sem cobertura")

    def done(label: dict[str, Any], lever: str, decide_by: str | None, why: str | None) -> dict[str, Any]:
        # o aviso de capacidade vem do status da família no contexto, não do status da recomendação
        if decide_by and reference and decide_by < reference:
            # prazo já vencido na referência: a decisão é para hoje, e o motivo diz desde quando
            day, month = decide_by[8:10], decide_by[5:7]
            why = f"prazo vencido em {day}/{month}: decidir hoje" + (f" ({why})" if why else "")
            decide_by = reference
        return _lever(_capacity_note(label, context.get("capacity_status")), lever, decide_by, why)

    legacy_args = (action, priority, forecast_status, event_alerts, capacity_status, reference_date, settings)
    # 1. dado insuficiente vence tudo
    if action == "investigar_dados" or forecast_status == "insufficient_data":
        return _lever(_label_operational_legacy(*legacy_args), "nenhuma", None, None)
    # 2. pedidos sem cobertura disputados por 2 ou mais clientes: a decisão é quem atender
    if uncovered and context.get("contested"):
        first, last, text = context.get("first_client"), context.get("last_client"), context.get("decision_text")
        # clientes distintos na ordem de atendimento: nunca "Atender A antes de A"
        head = f"Atender {first} antes de {last}" if first and last and first != last else "Decidir a ordem de atendimento entre os clientes que disputam o estoque"
        label = _result("priorizar_parceiro", "operational", action, ["UNCOVERED_ORDER", "ALLOCATION_CONTESTED"], base_evidence,
                        f"{head}." + (f" {text.rstrip('.')}." if text else ""), ["Alocação sugerida; não reserva estoque nem altera pedidos."])
        return done(label, "alocar", promised, promise_reason)
    # 3. OP não iniciada que pode chegar antes da falta (descontinuado nunca recebe rótulo de produção)
    if (action == "antecipar_op" or context.get("anticipable_ops")) and not discontinued:
        ops = ", ".join(context.get("anticipable_ops") or []) or "a OP em aberto"
        label = _result("priorizar_producao", "operational", action, ["OP_ANTICIPATION"], base_evidence, f"Antecipar {ops}: ainda não iniciada, pode chegar antes da falta.",
                        ["A data da falta vem da projeção diária: carteira na data prometida, previsão rateada e OPs na conclusão prevista."])
        return done(label, "antecipar_op", reference, "antecipar hoje preserva a janela")
    # 4. pedido sem cobertura com ordem urgente de quantidade > 0 (produto ativo)
    if uncovered and not discontinued and urgent_qty > 0:
        label = _result("priorizar_producao", "operational", action, ["UNCOVERED_ORDER", "URGENT_PLANNED_ORDER"], base_evidence,
                        f"Garantir {urgent_qty:g} un. e renegociar {uncovered[0]['order']}: a ordem urgente só chega depois da data prometida.",
                        ["A ordem urgente chega depois da data prometida; o pedido só se resolve renegociando o prazo."])
        return done(label, "produzir_agora", context.get("next_urgent_release_date"), "liberação da ordem urgente")
    # 5. pedido sem cobertura e sem alavanca de produção (quantidade urgente 0 ou descontinuado)
    if uncovered:
        target = ", ".join(item["order"] for item in uncovered)
        why = "produto em descontinuação" if discontinued else "sem ordem urgente"
        label = _result("monitorar", "operational", action, ["UNCOVERED_ORDER", "NO_PRODUCTION_LEVER"], base_evidence,
                        f"Renegociar {target}: o estoque e a OP existentes não cobrem a data; sem nova produção ({why}).")
        return done(label, "renegociar", promised, promise_reason)
    # 6. falta só na previsão (sem pedido afetado); atraso_inevitavel sem pedido descoberto é o mesmo caso
    if context.get("forecast_only_shortfall") or action == "atraso_inevitavel":
        shortfall = context.get("first_shortfall_date")
        evidence = [*base_evidence, _ev("Primeira falta projetada", shortfall, "projeção diária")]
        note = ["Nenhum pedido confirmado é afetado: a falta depende da previsão, não da carteira."]
        if urgent_qty > 0 and not discontinued:
            label = _result("produzir", "operational", action, ["PROJECTED_SHORTFALL", "FORECAST_ONLY"], evidence,
                            f"Falta estimada pela previsão (sem pedido confirmado afetado); produzir {urgent_qty:g} un. na ordem urgente.", note)
            return done(label, "produzir_agora", context.get("next_urgent_release_date"), "liberação da ordem urgente")
        label = _result("monitorar", "operational", action, ["PROJECTED_SHORTFALL", "FORECAST_ONLY"], evidence,
                        "Falta estimada pela previsão (sem pedido confirmado afetado) e sem ordem urgente: acompanhar.", note)
        return done(label, "nenhuma", shortfall, "primeira falta projetada" if shortfall else None)
    # 7. rever OP
    if action == "rever_op":
        return _lever(_label_operational_legacy(*legacy_args), "rever_op", context.get("decision_window_end"), "fim da janela de decisão")
    if action in ("produzir", "produzir_validar_capacidade") and not discontinued:
        legacy = _label_operational_legacy(*legacy_args)
        event_signal = next((signal for signal in legacy["signals_used"] if signal.startswith("event_decision:")), None)
        extra = [limit for limit in legacy["limitations"] if limit not in LIMITATIONS["operational"]]
        # 8. produzir urgente só vira "Priorizar produção" na faixa 1 ou com decisão de evento na janela
        if tier == 1 or event_signal:
            signals, reasons, evidence = [f"operational_action:{action}"], [], list(base_evidence)
            if tier == 1:
                signals.append("urgency_tier_1")
                reasons.append("faixa 1 de urgência (pedido confirmado sem cobertura)")
            event_date = None
            if event_signal:
                signals.append(event_signal)
                events = [item for item in legacy["evidence"] if item["label"].startswith("Decisão de ")]
                evidence.extend(events)
                event_date = events[0]["value"] if events else None
                reasons.append(f"{events[0]['label'][:1].lower()}{events[0]['label'][1:]} até {event_date} (janela de {settings['event_decision_window_days']} dias)" if events else "decisão de evento na janela")
            release = context.get("next_urgent_release_date")
            label = _result("priorizar_producao", "operational", action, signals, evidence, "Produzir com urgência: " + "; ".join(reasons) + ".", extra)
            return done(label, "produzir_agora", release or event_date, "liberação da ordem urgente" if release else "decisão do evento")
        # 9. produzir no horizonte: só vira "Produzir" se a próxima liberação cair na janela de decisão; depois dela, acompanhar
        release, window_end = context.get("first_planned_release_date"), context.get("decision_window_end")
        if release and window_end and release > window_end:
            when = f"{release[8:10]}/{release[5:7]}"
            label = _result("monitorar", "operational", action, [f"operational_action:{action}", "PLANNED_RELEASE_AFTER_WINDOW"],
                            [*base_evidence, _ev("Próxima liberação planejada", release, "plano de suprimento")],
                            f"Próxima ordem planejada a liberar em {when}, depois da janela de decisão (até {window_end[8:10]}/{window_end[5:7]}); nada a decidir agora.", extra)
            return done(label, "produzir_futuro", release, f"próxima ordem planejada a liberar em {when}")
        label = _result("produzir", "operational", action, [f"operational_action:{action}"], base_evidence,
                        "Há necessidade líquida de produção no horizonte, sem pedido sem cobertura nem decisão de evento na janela.", extra)
        return done(label, "produzir_futuro", release, "primeira liberação planejada")
    # 10. excesso
    if action == "monitorar_excesso":
        return _lever(_result("monitorar", "operational", action, ["EXCESS_COVERAGE"], [], "Excesso de cobertura; acompanhar sem produzir."), "nenhuma", None, None)
    # 11. demais
    return _lever(_result("sem_acao_necessaria", "operational", action, [], [], "Sem necessidade de produção neste horizonte; os riscos do SKU continuam."), "nenhuma", None, None)


def decisions_today(items: list[dict[str, Any]], reference_date: date, window_days: int = 7) -> dict[str, Any]:
    """Decisões com `decide_by` até a referência + `window_days`, das mais próximas às mais distantes. `items` trazem `challenge_action`."""
    limit = (reference_date + timedelta(days=window_days)).isoformat()
    found = []
    for item in items:
        action = item.get("challenge_action") or {}
        lever, decide_by = action.get("lever"), action.get("decide_by")
        if lever in (None, "nenhuma") or not decide_by or decide_by > limit:
            continue
        found.append({"sku": item["sku"], "product": item.get("product"), "label": action.get("label"), "lever": lever, "decide_by": decide_by, "reason": action.get("reason")})
    found.sort(key=lambda entry: (entry["decide_by"], entry["sku"]))
    return {"window_end": limit, "count": len(found), "items": found, "requires_human_review": True,
            "limitations": ["Lista as decisões com prazo na janela a partir dos rótulos calculados; não executa nem reserva nada."]}


# --------------------------------------------------------------- parceiro–SKU (comercial)

def _month(value: str | None) -> int | None:
    if not value:
        return None
    year, month = value[:7].split("-")
    return int(year) * 12 + int(month) - 1


def recompra_signal(row: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    """Meses sem sell-in acima do ritmo do próprio par, com sell-out recente positivo. None se não houver base."""
    reference = _month(row.get("reference_month"))
    months = sorted({_month(period["month"]) for period in row.get("periods", []) if period.get("sell_in_quantity") is not None and period.get("month")} - {None})
    average = row.get("average_monthly_sell_out")
    if reference is None or len(months) < settings["recompra_min_sell_in_months"] or not average or average <= 0:
        return None
    gaps = sorted(later - earlier for earlier, later in zip(months, months[1:]))
    typical = gaps[len(gaps) // 2] if len(gaps) % 2 else (gaps[len(gaps) // 2 - 1] + gaps[len(gaps) // 2]) / 2
    since = reference - months[-1]
    if since >= max(settings["recompra_min_months_without_sell_in"], math.ceil(typical * 2)):
        return {"last_sell_in_month": f"{months[-1] // 12}-{months[-1] % 12 + 1:02d}", "typical_interval_months": typical, "months_without_sell_in": since, "average_monthly_sell_out": average}
    return None


def label_commercial_row(row: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    action, quality = row["action"], row.get("data_quality")
    pair = f"{row['partner']} · {row['sku']}"
    if action in ("solicitar_atualizacao", "dados_insuficientes", "investigar_divergencia"):
        why = {"solicitar_atualizacao": "Dado antigo ou descontínuo; atualizar antes de qualquer oportunidade.",
               "dados_insuficientes": "Sem sell-out suficiente (amostra, estoque estimado ou natureza declarada); nenhuma oportunidade é inferida.",
               "investigar_divergencia": "Sell-in e sell-out divergem nos mesmos meses; conferir registros antes de decidir."}[action]
        signals = [signal["code"] for signal in row.get("signals", [])] or [action.upper()]
        evidence = [_ev("Qualidade do dado", quality, "partner_insights")]
        if action == "investigar_divergencia":
            evidence.append(_ev("Diferença sell-in − sell-out (un.)", row.get("comparable_difference"), "Sell_In e Sell_Out, meses comparáveis"))
        if action == "solicitar_atualizacao":
            evidence.append(_ev("Idade do último sell-out (meses)", row.get("age_months"), "Sell_Out"))
        if action == "dados_insuficientes" and row.get("row_kind", "partner") == "partner" and (row.get("backlog_quantity") or 0) > 0:
            # Etapa 16.6: pedido na carteira sem sell-out do parceiro; a lacuna se resolve pedindo o dado.
            evidence += [_ev("Carteira sem sell-out (un.)", row.get("backlog_quantity"), "Carteira_Pedidos"), _ev("Pedidos abertos", row.get("backlog_order_count"), "Carteira_Pedidos")]
            return _result("investigar", "commercial", action, [*signals, "SELL_OUT_REQUEST"], evidence,
                           f"Há pedido na carteira de {pair} e nenhum sell-out suficiente: pedir ao parceiro o sell-out deste SKU antes de decidir.")
        return _result("investigar", "commercial", action, signals, evidence, why)
    if action == "canal_direto":
        # Fallback: a API usa label_channel_row (sugestão de canais diretos); aqui só a venda direta observada, sem estoque intermediário.
        evidence = [_ev("Venda direta observada (un./mês)", row.get("average_monthly_sell_out"), "Vendas_24m, faturamento direto")]
        return _result("monitorar", "commercial", action, [signal["code"] for signal in row.get("signals", [])], evidence,
                       f"Venda direta observada pelo faturamento em {pair}; sem estoque intermediário, cobertura e acúmulo não se aplicam.")
    evidence = [_ev("Giro médio de sell-out (un./mês)", row.get("average_monthly_sell_out"), "Sell_Out"), _ev("Estoque estimado no parceiro (un.)", row.get("estimated_stock"), "Sell_Out, estimado")]
    if action == "conter_reposicao":
        through, start = row.get("sell_through_window"), row.get("stock_start")
        evidence = [_ev(f"Vendido ÷ enviado em {row.get('buildup_window_months')} meses", None if through is None else f"{through:.0%}", "Sell_Out ÷ Sell_In"),
                    _ev("Estoque estimado inicial → final (un.)", f"{start:g} → {row.get('estimated_stock'):g}" if start is not None and row.get("estimated_stock") is not None else None, "Sell_Out, estimado"),
                    _ev("Cobertura estimada (dias)", None if row.get("coverage_days") is None else round(row["coverage_days"], 1), "Sell_Out"),
                    _ev("Conta de estoque fecha", {True: "sim", False: "não"}.get(row.get("stock_identity_consistent")), "estoque anterior + sell-in − sell-out")]
        return _result("investigar", "commercial", action, [signal["code"] for signal in row.get("signals", [])], evidence,
                       f"Estoque acumulando em {pair}: o parceiro recebe mais do que vende. Não repor; investigar o giro com o parceiro e combinar ação de sell-out.")
    if action == "monitorar_excesso_parceiro":
        evidence.insert(0, _ev("Cobertura estimada (dias)", None if row.get("coverage_days") is None else round(row["coverage_days"], 1), "Sell_Out"))
        return _result("monitorar", "commercial", action, [signal["code"] for signal in row.get("signals", [])], evidence,
                       f"Estoque alto e estável em {pair}; não ampliar a reposição.")
    if action == "avaliar_reposicao":
        evidence.insert(0, _ev("Cobertura estimada (dias)", None if row.get("coverage_days") is None else round(row["coverage_days"], 1), "Sell_Out"))
        forward = row.get("forward_projection")
        if forward and forward.get("status") == "ok":
            # Etapa 16.6: projeção do parceiro como evidência estimada; não autoriza quantidade.
            evidence += [_ev("Dias até acabar sem reposição", forward["days_until_stockout_without_replenishment"], "Projeção do parceiro, estimada"),
                         _ev("Quantidade para 30 dias (estimada)", forward["replenishment_to_target"], "Projeção do parceiro, estimada"),
                         _ev("Erro medido do sell-out (WAPE)", None if forward["sell_out_wape"] is None else f"{forward['sell_out_wape']:.0%}", "Projeção do parceiro, origens rolantes")]
        return _result("repor", "commercial", action, [signal["code"] for signal in row.get("signals", [])], evidence, f"Cobertura estimada baixa para o giro observado em {pair}; avaliar reposição.")
    recompra = recompra_signal(row, settings)
    if recompra:
        evidence = [_ev("Último sell-in", recompra["last_sell_in_month"], "Sell_In"), _ev("Intervalo típico entre envios (meses)", recompra["typical_interval_months"], "Sell_In do próprio par"),
                    _ev("Meses sem sell-in", recompra["months_without_sell_in"], "Sell_In"), *evidence]
        return _result("recomendar_recompra", "commercial", action, ["RECOMPRA_GAP"], evidence,
                       f"O par {pair} vende (giro positivo) mas está há {recompra['months_without_sell_in']} meses sem sell-in, acima do ritmo do próprio par.")
    return _result("monitorar", "commercial", action, [signal["code"] for signal in row.get("signals", [])], evidence, "Dados suficientes, sem exceção; acompanhar o estoque do parceiro sem afirmar excesso.")


def label_partner(summary: dict[str, Any], rows: list[dict[str, Any]], priority_by_sku: dict[str, int | None], settings: dict[str, Any],
                  allocation_partner: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """`rows` são as linhas do parceiro já com `challenge_action`. Só rotula 'Priorizar parceiro'; os demais ficam sem rótulo no nível do parceiro.

    Com `allocation_partner` (entrada do parceiro em `build_allocation`), também rotula quem é o primeiro atendido em SKU disputado (sinal ALLOCATION_FIRST).
    """
    opportunities = [row for row in rows if row["challenge_action"]["code"] == "repor"]
    top = [row for row in opportunities if (priority_by_sku.get(row["sku"]) or math.inf) <= settings["priority_top_n"]]
    first_in = list((allocation_partner or {}).get("first_in_contested") or [])
    if first_in:
        evidence = [_ev("SKUs disputados em que é o primeiro atendido", ", ".join(first_in), "alocação sugerida")]
        signals = ["ALLOCATION_FIRST"]
        if len(opportunities) >= settings["partner_min_opportunities"] and top:
            evidence.append(_ev("Pares com oportunidade de reposição", len(opportunities), "partner_insights"))
            signals += ["REPOSITION_OPPORTUNITY", f"priority_top_{settings['priority_top_n']}"]
        return _result("priorizar_parceiro", "partner", "alocacao_sugerida", signals, evidence,
                       f"{summary.get('name') or summary['code']} é o primeiro a ser atendido em {len(first_in)} SKU disputado(s) ({', '.join(first_in)}), pela alocação sugerida.",
                       ["Alocação sugerida; não reserva estoque nem altera pedidos."])
    if len(opportunities) < settings["partner_min_opportunities"] or not top:
        return None
    evidence = [_ev("Pares com oportunidade de reposição", len(opportunities), "partner_insights"),
                *[_ev(f"Posição de {row['sku']} na fila de atenção", priority_by_sku[row["sku"]], "ranking oficial") for row in sorted(top, key=lambda item: priority_by_sku[item["sku"]])]]
    return _result("priorizar_parceiro", "partner", "avaliar_reposicao", ["REPOSITION_OPPORTUNITY", f"priority_top_{settings['priority_top_n']}"], evidence,
                   f"{len(opportunities)} pares com oportunidade de reposição em {summary.get('name') or summary['code']}, incluindo SKU entre os {settings['priority_top_n']} primeiros da fila de atenção.")


# --------------------------------------------------------------- canais diretos

_CHANNEL_MAP = {
    "avaliar_ampliacao_mix": "ampliar_mix", "avaliar_reativacao": "reativar", "investigar_queda": "investigar",
    "monitorar_saida_de_linha": "monitorar", "acompanhar_crescimento": "monitorar", "sem_acao_necessaria": "sem_acao_necessaria",
}


def label_channel_row(row: dict[str, Any]) -> dict[str, Any]:
    suggestion = row["suggestion"]
    code = _CHANNEL_MAP[suggestion["code"]]
    evidence = [_ev("Faturamento nos 24 meses", row.get("revenue_24m"), "Vendas_24m"), _ev("Tendência recente", row.get("trend"), "Vendas_24m"), _ev("Último mês com faturamento", row.get("last_month"), "Vendas_24m")]
    return _result(code, "channel", suggestion["code"], list(row.get("signals", [])), evidence, suggestion["reason"])


def known_codes() -> tuple[str, ...]:
    return tuple(LABELS)
