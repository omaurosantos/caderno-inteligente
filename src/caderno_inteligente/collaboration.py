"""Programa de Colaboração: Índice de Colaboração, nível por parceiro, simulação de níveis e linha de base.

Camada aditiva e somente leitura: não altera ranking, regras nem previsão. Tudo o que vem da base é observado ou calculado;
pesos, limiares e níveis são proposta a validar (config/collaboration.json). Benefícios são hipóteses, nunca concessão."""
import json
import math
from pathlib import Path

import pandas as pd

DIMENSIONS = {
    "completeness": "Completude",
    "freshness": "Atualidade",
    "frequency": "Frequência",
    "consistency": "Consistência",
    "quality": "Qualidade",
    "continuity": "Continuidade",
}


def load_collaboration_settings(path: str | Path) -> dict:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    weights = values.get("weights") or {}
    if set(weights) != set(DIMENSIONS) or any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()) or abs(sum(weights.values()) - 1) > 1e-6:
        raise ValueError("Pesos do Índice de Colaboração devem cobrir as seis dimensões e somar 1")
    levels = values.get("levels") or []
    if not levels or [lv.get("level") for lv in levels] != list(range(1, len(levels) + 1)):
        raise ValueError("Níveis de colaboração devem ser numerados em sequência a partir de 1")
    if int(values.get("window_months", 0)) < 1:
        raise ValueError("window_months deve ser positivo")
    return values


def _months(series: pd.Series) -> pd.PeriodIndex:
    return pd.PeriodIndex(pd.to_datetime(series), freq="M")


def _streak(periods: set, latest) -> int:
    count = 0
    while latest - count in periods:
        count += 1
    return count


def _partner_metrics(sell_out: pd.DataFrame, latest, total_skus: int, rows: list[dict], cfg: dict) -> dict:
    window = int(cfg["window_months"])
    first = latest - (window - 1)
    quantity = pd.to_numeric(sell_out["Quantidade vendida"], errors="coerce")
    stock = pd.to_numeric(sell_out["Estoque estimado cliente"], errors="coerce")
    valid = quantity.ge(0) & stock.ge(0) & sell_out["Natureza do dado"].eq("Observado pelo parceiro") & ~sell_out.duplicated(["Mês", "SKU"])
    periods = _months(sell_out["Mês"])
    by_sku: dict[str, set] = {}
    for sku, period in zip(sell_out["SKU"], periods):
        if first <= period <= latest:
            by_sku.setdefault(sku, set()).add(period)
    pair_count = len(by_sku)
    lag = latest - periods.max()
    scored = [r for r in rows if r.get("data_quality") != "insufficient"]
    consistent = [r for r in scored if r.get("stock_identity_consistent") is not False
                  and (r.get("divergence_ratio") is None or r["divergence_ratio"] <= cfg["divergence_limit"])]
    return {
        "completeness": sell_out["SKU"].nunique() / total_skus if total_skus else 0.0,
        "freshness": max(0.0, 1 - lag.n / cfg["freshness_zero_after_months"]),
        "frequency": sum(len(m) for m in by_sku.values()) / (pair_count * window) if pair_count else 0.0,
        "consistency": len(consistent) / len(scored) if scored else 0.0,
        "quality": float(valid.mean()) if len(valid) else 0.0,
        "continuity": sum(_streak(m, latest) for m in by_sku.values()) / (pair_count * window) if pair_count else 0.0,
        "_lag_months": int(lag.n), "_pairs": int(sell_out["SKU"].nunique()), "_records": int(len(valid)), "_invalid": int((~valid).sum()),
        "_consistent": len(consistent), "_scored": len(scored),
    }


_BASIS = {
    "completeness": lambda m: f"{m['_pairs']} SKUs com sell-out de {m['_total']} do catálogo",
    "freshness": lambda m: f"último dado {m['_lag_months']} mês(es) antes do mês mais recente da base; a base é mensal, então a latência em dias não é medida",
    "frequency": lambda m: f"meses com dado nos últimos {m['_window']} por par parceiro–SKU",
    "consistency": lambda m: f"{m['_consistent']} de {m['_scored']} pares com estoque que fecha e divergência dentro do limite",
    "quality": lambda m: f"{m['_records'] - m['_invalid']} de {m['_records']} registros válidos (sem negativos, duplicidade ou dado não observado)",
    "continuity": lambda m: "sequência de meses sem falha até o mês mais recente, por par parceiro–SKU",
}


def _level_gaps(level: dict, metrics: dict, index: float, has_stock: bool) -> list[dict]:
    gaps = []
    checks = [("completeness", "Completude", metrics["completeness"], level["min_completeness"]),
              ("frequency", "Frequência", metrics["frequency"], level["min_frequency"]),
              ("index", "Índice de Colaboração", index, level["min_index"])]
    for key, label, current, required in checks:
        if current + 1e-9 < required:
            gaps.append({"criterion": key, "current": round(current, 4), "required": required, "text": f"{label} {current:.0%}, mínimo {required:.0%}"})
    if level["requires_stock_position"] and not has_stock:
        gaps.append({"criterion": "stock_position", "current": None, "required": True,
                     "text": "Posição de estoque informada pelo parceiro (hoje o estoque do parceiro é estimado a partir de sell-in e sell-out)"})
    return gaps


def _simulate(current_level: int, metrics: dict, index: float, has_stock: bool, rows: list[dict], total_skus: int, cfg: dict) -> list[dict]:
    pending = sorted((r for r in rows if r.get("data_quality") == "insufficient"), key=lambda r: -(r.get("backlog_quantity") or 0))
    with_data = [r for r in rows if r.get("data_quality") != "insufficient"]
    scenarios = []
    for level in cfg["levels"]:
        if level["level"] <= current_level:
            continue
        add = max(0, math.ceil(total_skus * level["min_completeness"]) - metrics["_pairs"])
        chosen = pending[:add]
        scenarios.append({
            "level": level["level"], "name": level["name"], "gives": level["gives"],
            "gaps": _level_gaps(level, metrics, index, has_stock),
            "additional_skus": add,
            "rows_with_estimated_stock": len(with_data) if level["requires_stock_position"] and not has_stock else 0,
            "unlocked": {
                "rows_without_data_now": len(pending),
                "candidate_skus": [{"sku": r["sku"], "product": r.get("product"), "backlog_quantity": r.get("backlog_quantity"),
                                    "orders": r.get("backlog_order_count")} for r in chosen[:5]],
                "covered_backlog_quantity": sum(r.get("backlog_quantity") or 0 for r in chosen),
                "covered_orders": sum(r.get("backlog_order_count") or 0 for r in chosen),
            },
            "nature": "calculado: efeito esperado sobre os dados da base, não garantido nem acordado com o parceiro",
        })
    return scenarios


def build_collaboration(data: dict[str, pd.DataFrame], insights: dict, cfg: dict, unit_visibility_share: float | None = None) -> dict:
    sell_out, products, registry = data["Sell_Out"], data["Produtos"], data["Parceiros_Canais"]
    total_skus = int(products["SKU"].nunique())
    latest = _months(sell_out["Mês"]).max()
    rows_by_partner: dict[str, list[dict]] = {}
    for row in insights["items"]:
        if row.get("row_kind") == "partner":
            rows_by_partner.setdefault(row["partner"], []).append(row)
    partners = []
    for _, meta in registry.iterrows():
        code = meta["Código"]
        if meta["Tipo"] == "Canal direto":
            continue
        own = sell_out[sell_out["Cliente"] == code]
        rows = rows_by_partner.get(code, [])
        info = {"code": code, "name": meta["Nome fictício"], "type": meta["Tipo"], "region": meta["Região"], "size": meta["Porte"]}
        if own.empty:
            empty = {"_pairs": 0, "completeness": 0.0, "frequency": 0.0}
            partners.append({**info, "level": 0, "level_name": "Sem dado de sell-out", "index": None, "dimensions": None, "observed_skus": 0,
                             "total_skus": total_skus, "stock_position": "estimada", "next_level": cfg["levels"][0]["name"], "insufficient_rows": len(rows),
                             "gaps": _level_gaps(cfg["levels"][0], empty, 0.0, False), "scenarios": _simulate(0, empty, 0.0, False, rows, total_skus, cfg)})
            continue
        metrics = _partner_metrics(own, latest, total_skus, rows, cfg)
        metrics.update(_total=total_skus, _window=cfg["window_months"])
        index = sum(cfg["weights"][k] * metrics[k] for k in DIMENSIONS)
        has_stock = code in cfg.get("stock_position_partners", [])
        level = 0
        for lv in cfg["levels"]:
            if _level_gaps(lv, metrics, index, has_stock):
                break
            level = lv["level"]
        nxt = next((lv for lv in cfg["levels"] if lv["level"] == level + 1), None)
        partners.append({
            **info, "level": level, "level_name": next((lv["name"] for lv in cfg["levels"] if lv["level"] == level), "Sem nível"),
            "index": round(index, 4), "stock_position": "informada" if has_stock else "estimada",
            "observed_skus": metrics["_pairs"], "total_skus": total_skus,
            "dimensions": [{"key": k, "label": DIMENSIONS[k], "value": round(metrics[k], 4), "weight": cfg["weights"][k],
                            "basis": _BASIS[k](metrics), "nature": "calculado"} for k in DIMENSIONS],
            "gaps": _level_gaps(nxt, metrics, index, has_stock) if nxt else [],
            "next_level": nxt["name"] if nxt else None,
            "scenarios": _simulate(level, metrics, index, has_stock, rows, total_skus, cfg),
            "insufficient_rows": sum(1 for r in rows if r.get("data_quality") == "insufficient"),
        })
    eligible = len(partners)
    observed_pairs = sum(p["observed_skus"] for p in partners)
    matrix = observed_pairs / (eligible * total_skus) if eligible and total_skus else 0.0
    indexes = [p["index"] for p in partners if p["index"] is not None]
    joined = sum(1 for p in partners if p["level"] >= 1)
    unit_text = (f"{format(unit_visibility_share, ".1%").replace(".", ",")} é a parcela das unidades faturadas com venda ao consumidor observada, que inclui os canais diretos."
                 if unit_visibility_share is not None else "a parcela de unidades observadas inclui os canais diretos.")
    program = {
        "eligible_partners": eligible, "participating_partners": joined, "adhesion": joined / eligible if eligible else None,
        "matrix_pairs_observed": observed_pairs, "matrix_pairs_total": eligible * total_skus, "matrix_coverage": matrix,
        "mean_index": round(sum(indexes) / len(indexes), 4) if indexes else None,
        "by_level": [{"level": 0, "name": "Sem dado de sell-out", "partners": sum(1 for p in partners if p["level"] == 0)}]
                    + [{"level": lv["level"], "name": lv["name"], "partners": sum(1 for p in partners if p["level"] == lv["level"])} for lv in cfg["levels"]],
        "unit_visibility_share": unit_visibility_share,
        "reconciliation": f"Dois recortes, ambos corretos: {matrix:.0%} é a cobertura da matriz parceiro × SKU (só parceiros, sell-out informado); {unit_text}",
        "evolution": None,
        "evolution_reason": "Há apenas uma fotografia da base: sem histórico de envios não existe evolução a mostrar. Esta é a linha de base do programa.",
        "decisions": {"available": False,
                      "reason": "O histórico de decisões não registra o parceiro nem se o dado do parceiro mudou a decisão; a métrica 'decisões que mudaram com o dado' ainda não é medida."},
    }
    return {
        "reference_month": str(latest), "status": cfg.get("status"), "note": cfg.get("note"),
        "levels": [{k: lv[k] for k in ("level", "name", "gives", "min_completeness", "min_frequency", "min_index", "requires_stock_position")} for lv in cfg["levels"]],
        "weights": cfg["weights"], "partners": partners, "program": program,
        "field_nature": {"index": "calculado a partir de sell-out observado pelo parceiro",
                         "level": "classificação demonstrativa por regras propostas, não acordo comercial",
                         "scenarios": "calculado: efeito esperado, não garantido", "benefits": "hipótese a validar; sem promessa de concessão"},
        "limitations": ["Pesos e limiares do índice e dos níveis são proposta a validar com parceiros.",
                        "A latência real do envio não é medida: a base é mensal.",
                        "Maturidade tecnológica e engajamento do parceiro não constam na base.",
                        "A posição de estoque do parceiro é estimada; nenhum parceiro informa estoque observado, por isso nenhum chega ao nível 2."],
        "requires_human_review": True,
    }
