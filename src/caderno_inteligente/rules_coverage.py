"""Etapa 16.6 (P6): cobertura de regras, quanto cada regra dispara nas saídas reais e por que as que não disparam.

Somente leitura. Lista as regras operacionais (`config/prioritization_weights.json`; disparos = SKUs distintos em `issues`) e
todos os códigos de `LABELS` (disparos = contagem nos SKUs, nas linhas comerciais, nos parceiros e nas linhas de canal). Regra
sem disparo traz o motivo com número calculado na base, o dado que faltaria e o caso congelado que comprova a regra.
Dado ausente nunca vira zero: sem base para calcular o número, o motivo diz isso e o número fica nulo.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from caderno_inteligente.action_labels import DEFINITIONS, LABELS, PRECEDENCE, label_channel_row

WEIGHTS_FILE = Path(__file__).resolve().parents[2] / "config" / "prioritization_weights.json"

OPERATIONAL_CONDITIONS = {
    "PROJECTED_SHORTFALL": "Falta projetada antes que uma reposição nova consiga chegar (data de planejamento + lead time).",
    "OP_FOR_DISCONTINUED": "Há OP aberta para produto em descontinuação.",
    "CAPACITY_SHORTFALL": "Ordem planejada não cabe na capacidade livre da linha até a data de necessidade.",
    "PARTNER_STOCK_BUILDUP": "Parceiro com estoque acumulando: recebe mais do que vende.",
    "PROJECTED_EXCESS": "Depois da chegada da OP, o estoque projetado passa do limite de excesso.",
    "RUP_LEAD_TIME": "Cobertura de estoque abaixo do lead time.",
    "RUP_SAFETY_STOCK": "Cobertura de estoque abaixo do estoque de segurança.",
    "ORDER_WITHOUT_PRODUCTION": "Há pedido em carteira sem ordem de produção registrada para o SKU.",
    "PRODUCTION_AFTER_PROMISE": "A primeira conclusão de produção é posterior à primeira data prometida do SKU.",
    "EXCESS_COVERAGE": "Cobertura de estoque acima do limite de excesso configurado.",
    "LOW_SELLOUT_VISIBILITY": "Não há sell-out observado para o SKU; a análise possui menor visibilidade de canal.",
}

# Casos congelados do Centro de Validação que comprovam a regra mesmo sem ocorrência na base atual.
REFERENCE_CASES = {
    "ampliar_mix": {"case": "VC-14", "origin": "synthetic", "title": "Ampliar mix em canal com faturamento completo"},
    "recomendar_recompra": {"case": "VC-15", "origin": "synthetic", "title": "Recomendar recompra quando o parceiro vende mas parou de receber"},
    "reativar": {"case": "VC-16", "origin": "synthetic", "title": "Reativar SKU que parou de vender no canal"},
}
DATA_NEEDED = {
    "ampliar_mix": "SKU ativo sem nenhum faturamento em um canal direto nos 24 meses (sinal NOT_SOLD).",
    "recomendar_recompra": "Par parceiro–SKU com giro de sell-out positivo e lacuna de sell-in maior que o ritmo do próprio par (sinal RECOMPRA_GAP).",
    "reativar": "SKU que vendia no canal direto e ficou meses sem faturar (sinal STOPPED).",
}
GENERIC_DATA_NEEDED = "Dado que satisfaça a condição da regra."


def _frame_rows(frame: Any) -> list[dict]:
    return frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])


def _code_of(action: Any) -> str | None:
    return action.get("code") if isinstance(action, dict) else None


def _direct_rows(direct_channels: dict) -> list[dict]:
    rows = []
    for channel_rows in (direct_channels or {}).get("rows", {}).values():
        for row in channel_rows:
            # A factory do router recebe a análise crua dos canais; o rótulo é derivado aqui só quando falta.
            rows.append(row if row.get("challenge_action") else {**row, "challenge_action": label_channel_row(row)})
    return rows


def _zero_reason(code: str, direct: list[dict], dataset: dict) -> tuple[str, float | None]:
    """Motivo com número calculado na base para os códigos sem disparo; (texto, número)."""
    if code in ("ampliar_mix", "reativar") and direct:
        window = max(row.get("months_sold") or 0 for row in direct)
        full = sum(1 for row in direct if row.get("months_sold") == window)
        total = len(direct)
        base = f"Vendas_24m tem faturamento em {window} de {window} meses (sem lacunas) em {full} de {total} pares canal × SKU"
        if code == "ampliar_mix":
            not_sold = sum(1 for row in direct if "NOT_SOLD" in (row.get("signals") or []))
            return f"{base}; SKUs ativos sem faturamento no canal (NOT_SOLD): {not_sold}.", float(full)
        stopped = sum(1 for row in direct if "STOPPED" in (row.get("signals") or []))
        last = max((row["last_month"] for row in direct if row.get("last_month")), default=None)
        at_last = sum(1 for row in direct if row.get("last_month") == last)
        return f"{base}; {at_last} de {total} pares faturaram no último mês ({last}); parados (STOPPED): {stopped}.", float(at_last)
    if code == "recomendar_recompra":
        sell_in = (dataset or {}).get("Sell_In")
        if sell_in is not None and len(sell_in) and {"Mês", "Cliente", "SKU"} <= set(sell_in.columns):
            months = pd.to_datetime(sell_in["Mês"]).dt.to_period("M")
            span = int(months.nunique())
            per_pair = months.groupby([sell_in["Cliente"], sell_in["SKU"]]).nunique()
            continuous = int((per_pair == span).sum())
            return f"Sell_In é contínuo: {continuous} de {len(per_pair)} pares parceiro × SKU têm envio em {span} de {span} meses, então não há lacuna de recompra.", float(continuous)
    return "Nenhuma linha das saídas atuais satisfaz a condição desta regra; sem base para calcular um número.", None


def _price_by_sku(dataset: dict) -> dict[str, float]:
    prices = (dataset or {}).get("Precos_Produtos")
    if prices is None or not len(prices):
        return {}
    ordered = prices.sort_values("Vigência fictícia") if "Vigência fictícia" in prices else prices
    return {str(row["SKU"]): float(row["Preço unitário (R$)"]) for _, row in ordered.iterrows() if pd.notna(row.get("Preço unitário (R$)"))}


def sell_out_requests(commercial_rows: list[dict], dataset: dict) -> list[dict]:
    """Pares KA com carteira aberta e sem sell-out suficiente: onde pedir o sell-out ao parceiro vale mais (valor pelo último preço)."""
    prices = _price_by_sku(dataset)
    result = []
    for row in commercial_rows:
        if row.get("row_kind") != "partner" or row.get("action") != "dados_insuficientes" or not (row.get("backlog_quantity") or 0) > 0:
            continue
        price = prices.get(row["sku"])
        result.append({"partner": row["partner"], "sku": row["sku"], "product": row.get("product"), "backlog_quantity": row["backlog_quantity"],
                       "backlog_value": None if price is None else round(row["backlog_quantity"] * price, 2),
                       "orders": [order.get("order") if isinstance(order, dict) else order for order in row.get("orders") or []]})
    return sorted(result, key=lambda item: (item["backlog_value"] is None, -(item["backlog_value"] or 0), item["partner"], item["sku"]))


def _code_for_precedence(line: str) -> str | None:
    for code, label in sorted(LABELS.items(), key=lambda item: -len(item[1])):
        if line.casefold().startswith(label.casefold()):
            return code
    return None


def build_rules_coverage(issues: Any, forecast_items: list[dict], commercial: dict, direct_channels: dict, dataset: dict,
                         weights_file: str | Path | None = None) -> dict[str, Any]:
    weights = json.loads(Path(weights_file or WEIGHTS_FILE).read_text(encoding="utf-8"))
    issue_rows = _frame_rows(issues)
    skus_by_rule: dict[str, set] = {}
    for issue in issue_rows:
        skus_by_rule.setdefault(issue["code"], set()).add(issue["sku"])
    commercial_rows = list((commercial or {}).get("items") or [])
    direct = _direct_rows(direct_channels)
    by_level = {
        "sku": [_code_of(item.get("challenge_action")) for item in forecast_items or []],
        "commercial": [_code_of(row.get("challenge_action")) for row in commercial_rows],
        "partner": [_code_of(partner.get("challenge_action")) for partner in (commercial or {}).get("partners") or []],
        "channel": [_code_of(row.get("challenge_action")) for row in direct],
    }
    rules = []
    flagged_skus = len({issue["sku"] for issue in issue_rows})
    for rule, weight in weights.items():
        fires = len(skus_by_rule.get(rule, set()))
        rules.append({"rule": rule, "kind": "operational", "label": rule.replace("_", " ").capitalize(), "condition": OPERATIONAL_CONDITIONS.get(rule, rule),
                      "weight": weight, "fires": fires,
                      "zero_reason": None if fires else f"Nenhum dos {flagged_skus} SKUs com apontamento satisfaz a condição na base atual.",
                      "evidence_number": None if fires else float(flagged_skus), "data_needed": None if fires else GENERIC_DATA_NEEDED, "reference_case": None})
    fires_by_code: dict[str, int] = {}
    for code, label in LABELS.items():
        levels = {level: sum(1 for item in codes if item == code) for level, codes in by_level.items()}
        fires = sum(levels.values())
        fires_by_code[code] = fires
        zero_reason, evidence = (None, None) if fires else _zero_reason(code, direct, dataset)
        rules.append({"rule": code, "kind": "label", "label": label, "condition": DEFINITIONS.get(code, label), "fires": fires, "fires_by_level": levels,
                      "zero_reason": zero_reason, "evidence_number": evidence, "data_needed": None if fires else DATA_NEEDED.get(code, GENERIC_DATA_NEEDED),
                      "reference_case": None if fires else REFERENCE_CASES.get(code)})
    precedence = []
    for level, lines in PRECEDENCE.items():
        for position, line in enumerate(lines, 1):
            code = _code_for_precedence(line)
            precedence.append({"level": level, "position": position, "line": line, "code": code, "code_fires": fires_by_code.get(code)})
    return {"rules": rules, "sell_out_requests": sell_out_requests(commercial_rows, dataset), "precedence": precedence,
            "field_nature": {"fires": "calculado sobre as saídas atuais", "zero_reason": "calculado sobre a planilha",
                             "sell_out_requests": "carteira observada; valor estimado pelo último preço"},
            "limitations": ["A contagem por código soma SKU, linhas comerciais, parceiros e linhas de canal; linhas diretas aparecem nas fontes comercial e de canal.",
                            "Caso de referência sintético comprova a regra, não a ocorrência na operação.",
                            "Em precedence, code_fires é a contagem do código do rótulo daquela linha; a ordem de precedência não é reexecutada aqui."],
            "requires_human_review": True}
