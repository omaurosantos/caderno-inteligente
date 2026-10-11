"""Snapshot payload and run-to-run comparison. Read-only: explains changes, never recomputes the ranking."""
from __future__ import annotations

import math
from typing import Any

from caderno_inteligente.impact import _brl

SCHEMA_VERSION = 1
RANKING_FIELDS = ("sku", "priority", "attention_score", "confidence", "reasons", "urgency_tier", "value_at_risk")
# Etapa 16.3: faixa e valor em risco só existem em snapshots novos; os antigos continuam comparáveis pelos sinais e pesos.
OPTIONAL_RANKING_FIELDS = ("urgency_tier", "value_at_risk")
FORECAST_FIELDS = {
    "status": "Status da previsão",
    "model": "Modelo",
    "forecast_next_month": "Previsão do próximo mês",
    "forecast_total_3m": "Previsão de 3 meses",
    "backtest_wape": "WAPE no holdout",
    "forecast_confidence": "Confiança da previsão",
    "trend": "Tendência",
}
RECOMMENDATION_FIELDS = {
    "action": "Ação operacional",
    "suggested_quantity": "Quantidade sugerida",
    "capacity_status": "Capacidade",
    "confidence": "Confiança da recomendação",
}
PARTNER_FIELDS = {
    "coverage": "Cobertura observada",
    "observed_skus": "SKUs com sell-out",
    "total_catalog_skus": "SKUs do catálogo",
    "latest_sell_out_month": "Último sell-out",
}


def build_comparison_payload(forecast_summaries: list[dict], partner_result: dict | None, commercial_thresholds: dict | None,
                             partner_error: str | None = None) -> dict[str, Any]:
    """Preserve per-SKU forecast/recommendation and per-partner coverage exactly as computed; no allocation."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "forecasts": {item["sku"]: {key: item["forecast"].get(key) for key in FORECAST_FIELDS} for item in forecast_summaries},
        "recommendations": {item["sku"]: {key: item["operational_recommendation"].get(key) for key in RECOMMENDATION_FIELDS} for item in forecast_summaries},
        "commercial_thresholds": commercial_thresholds,
        "b2b_coverage": None,
        "b2b_unavailable_reason": partner_error,
    }
    if partner_result is not None:
        payload["b2b_coverage"] = {
            "reference_month": partner_result["reference_month"],
            "partners": {
                partner["code"]: {"name": partner["name"], **{key: partner.get(key) for key in PARTNER_FIELDS}, "action_counts": partner.get("action_counts")}
                for partner in partner_result["partners"]
            },
        }
    return payload


def _meta(run: dict) -> dict[str, Any]:
    comparison = run.get("comparison") or {}
    return {
        "id": run["id"],
        "created_at": run["created_at"],
        "source_hash": run["source_hash"],
        "prioritized_skus": len(run.get("ranking") or []),
        "comparison_schema_version": comparison.get("schema_version"),
    }


def _dict_changes(base: dict | None, target: dict | None) -> list[dict[str, Any]]:
    base, target = base or {}, target or {}
    return [{"key": key, "base": base.get(key), "target": target.get(key)}
            for key in sorted(set(base) | set(target)) if base.get(key) != target.get(key)]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return None if isinstance(value, float) and math.isnan(value) else float(value)


def _delta(base: Any, target: Any) -> float | None:
    left, right = _number(base), _number(target)
    return None if left is None or right is None else round(right - left, 4)


def _ranking_reason(run: dict) -> str | None:
    ranking = run.get("ranking")
    if not isinstance(ranking, list):
        return f"Execução #{run['id']} não possui ranking em formato de lista."
    for item in ranking:
        missing = [field for field in RANKING_FIELDS if field not in OPTIONAL_RANKING_FIELDS and (not isinstance(item, dict) or field not in item)]
        if missing:
            return f"Execução #{run['id']} não preserva os campos do ranking necessários: {', '.join(missing)}."
    return None


def _signals(item: dict) -> list[str]:
    return sorted({reason["code"] for reason in item.get("reasons") or []})


def _evidence(item: dict) -> dict[str, dict]:
    return {entry["code"]: entry.get("values_used") or {} for entry in item.get("evidence") or [] if isinstance(entry, dict) and "code" in entry}


def _ranking_entry(item: dict) -> dict[str, Any]:
    return {"sku": item["sku"], "product": item.get("product"), "family": item.get("family"), "priority": item["priority"],
            "attention_score": item["attention_score"], "confidence": item["confidence"], "signals": _signals(item),
            "urgency_tier": item.get("urgency_tier"), "urgency_label": item.get("urgency_label"), "value_at_risk": item.get("value_at_risk")}


def _risk(item: dict, key: str) -> float | None:
    risk = item.get("value_at_risk")
    return _number(risk.get(key)) if isinstance(risk, dict) else None


def _money(value: float | None) -> str:
    return "valor não calculado" if value is None else _brl(value)


def _signed_money(value: float | None) -> str:
    return "n/d" if value is None else f"{'+' if value >= 0 else '−'}{_brl(abs(value))}"


def _position(base: dict, target: dict, score_delta: float | None) -> dict[str, Any]:
    """Etapa 16.3: diz se a mudança de posição veio da faixa, do valor em risco ou dos sinais (só desempate).

    Snapshots sem faixa ordenavam pela pontuação de sinais: a explicação continua pelos pesos, como antes.
    """
    moved = base["priority"] != target["priority"]
    has_base, has_target = base.get("urgency_tier") is not None, target.get("urgency_tier") is not None
    if not (has_base and has_target):
        if has_base or has_target:
            line = ("Uma execução ordenava só pela pontuação de sinais e a outra por faixa de urgência e valor em risco; "
                    "a troca de posição reflete a mudança de critério.") if moved else None
            return {"ranking_basis": "misto", "position_driver": "criterio" if moved else None, "tier_change": None, "value_change": None, "line": line}
        driver = "sinais" if score_delta else "outros_skus" if moved else None
        return {"ranking_basis": "sinais", "position_driver": driver, "tier_change": None, "value_change": None, "line": None}
    tier_change = None
    if base["urgency_tier"] != target["urgency_tier"]:
        tier_change = {"base": base["urgency_tier"], "target": target["urgency_tier"],
                       "base_label": base.get("urgency_label"), "target_label": target.get("urgency_label")}
    left, right = _risk(base, "weighted"), _risk(target, "weighted")
    value_change = None
    if left != right:
        value_change = {"base": left, "target": right, "delta": _delta(left, right),
                        "observed_delta": _delta(_risk(base, "observed"), _risk(target, "observed")),
                        "estimated_delta": _delta(_risk(base, "estimated"), _risk(target, "estimated"))}
    if tier_change:
        driver = "faixa"
        line = (f"Faixa de urgência mudou de {tier_change['base']} ({tier_change['base_label'] or 'sem rótulo'}) para "
                f"{tier_change['target']} ({tier_change['target_label'] or 'sem rótulo'}); a faixa decide a ordem antes do valor em risco.")
        if target.get("urgency_reason"):
            line += f" Motivo atual: {target['urgency_reason']}"
    elif value_change:
        driver = "valor"
        line = (f"Mesma faixa ({target['urgency_tier']}); o valor em risco ponderado mudou de {_money(left)} para {_money(right)} "
                f"(observado {_signed_money(value_change['observed_delta'])}, estimado {_signed_money(value_change['estimated_delta'])}).")
    elif score_delta:
        driver = "sinais"
        line = "Mesma faixa e mesmo valor em risco; a pontuação de sinais desempatou a posição."
    elif moved:
        driver = "outros_skus"
        line = "Faixa, valor em risco e score iguais; a posição mudou porque outros SKUs entraram, saíram ou mudaram de faixa ou de valor."
    else:
        driver, line = None, None
    return {"ranking_basis": "faixa_e_valor", "position_driver": driver, "tier_change": tier_change, "value_change": value_change, "line": line}


def _explain(base: dict, target: dict, base_weights: dict, target_weights: dict) -> dict[str, Any]:
    base_signals, target_signals = set(_signals(base)), set(_signals(target))
    added, removed = sorted(target_signals - base_signals), sorted(base_signals - target_signals)
    breakdown: list[dict[str, Any]] = []
    for code in added:
        breakdown.append({"code": code, "change": "adicionado", "base_weight": None, "target_weight": target_weights.get(code), "delta": target_weights.get(code)})
    for code in removed:
        weight = base_weights.get(code)
        breakdown.append({"code": code, "change": "removido", "base_weight": weight, "target_weight": None, "delta": None if weight is None else -weight})
    for code in sorted(base_signals & target_signals):
        if base_weights.get(code) != target_weights.get(code):
            breakdown.append({"code": code, "change": "peso alterado", "base_weight": base_weights.get(code), "target_weight": target_weights.get(code),
                              "delta": _delta(base_weights.get(code), target_weights.get(code))})

    score_delta = _delta(base["attention_score"], target["attention_score"])
    deltas = [entry["delta"] for entry in breakdown]
    explained = score_delta is not None and None not in deltas and math.isclose(sum(deltas), score_delta, abs_tol=1e-9)
    lines = []
    for entry in breakdown:
        if entry["change"] == "adicionado":
            lines.append(f"Sinal novo {entry['code']} ({_signed(entry['delta'])}).")
        elif entry["change"] == "removido":
            lines.append(f"Sinal removido {entry['code']} ({_signed(entry['delta'])}).")
        else:
            lines.append(f"Peso de {entry['code']} mudou de {entry['base_weight']} para {entry['target_weight']} ({_signed(entry['delta'])}).")
    position = _position(base, target, score_delta)
    if position["line"]:
        lines.insert(0, position.pop("line"))
    else:
        position.pop("line")
    if position["ranking_basis"] == "sinais" and score_delta == 0 and base["priority"] != target["priority"]:
        lines.append("Score igual; a posição mudou porque outros SKUs entraram, saíram ou mudaram de score.")
    elif score_delta and not explained:
        lines.append("A diferença de score não é explicada pelos sinais e pesos registrados nas duas execuções; revisar os snapshots.")
    if base["confidence"] != target["confidence"]:
        reason = target.get("confidence_reason") or "motivo não registrado"
        lines.append(f"Confiança mudou de {base['confidence']} para {target['confidence']}: {reason}")

    evidence_changes = []
    base_evidence, target_evidence = _evidence(base), _evidence(target)
    for code in sorted(base_signals & target_signals):
        for change in _dict_changes(base_evidence.get(code), target_evidence.get(code)):
            evidence_changes.append({"code": code, "field": change["key"], "base": change["base"], "target": change["target"]})
    return {"signals_added": added, "signals_removed": removed, "score_breakdown": breakdown, "score_delta_explained": explained,
            **position, "explanation": lines, "evidence_changes": evidence_changes}


def _signed(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "peso não registrado"
    return f"{'+' if number >= 0 else '−'}{abs(number):g}"


def _compare_ranking(base: dict, target: dict) -> dict[str, Any]:
    reason = _ranking_reason(base) or _ranking_reason(target)
    if reason:
        return {"available": False, "reason": reason}
    base_items = {item["sku"]: item for item in base["ranking"]}
    target_items = {item["sku"]: item for item in target["ranking"]}
    base_weights, target_weights = base.get("weights") or {}, target.get("weights") or {}
    changed, unchanged = [], 0
    for sku in sorted(set(base_items) & set(target_items), key=lambda code: (target_items[code]["priority"], code)):
        left, right = base_items[sku], target_items[sku]
        same = (left["priority"], left["attention_score"], left["confidence"], _signals(left), left.get("urgency_tier"), left.get("value_at_risk")) ==                (right["priority"], right["attention_score"], right["confidence"], _signals(right), right.get("urgency_tier"), right.get("value_at_risk"))
        if same and _evidence(left) == _evidence(right):
            unchanged += 1
            continue
        changed.append({
            "sku": sku, "product": right.get("product"), "family": right.get("family"),
            "base": _ranking_entry(left), "target": _ranking_entry(right),
            "position_delta": left["priority"] - right["priority"],
            "score_delta": _delta(left["attention_score"], right["attention_score"]),
            "confidence_changed": left["confidence"] != right["confidence"],
            **_explain(left, right, base_weights, target_weights),
        })
    entered = [_ranking_entry(target_items[sku]) for sku in sorted(set(target_items) - set(base_items), key=lambda code: target_items[code]["priority"])]
    exited = [_ranking_entry(base_items[sku]) for sku in sorted(set(base_items) - set(target_items), key=lambda code: base_items[code]["priority"])]
    return {
        "available": True,
        "entered": entered,
        "exited": exited,
        "changed": changed,
        "unchanged_count": unchanged,
        "summary": {
            "entered": len(entered), "exited": len(exited), "changed": len(changed), "unchanged": unchanged,
            "moved_up": sum(item["position_delta"] > 0 for item in changed),
            "moved_down": sum(item["position_delta"] < 0 for item in changed),
            "score_changed": sum(bool(item["score_delta"]) for item in changed),
            "confidence_changed": sum(item["confidence_changed"] for item in changed),
            "with_new_signals": sum(bool(item["signals_added"]) for item in changed),
            "unexplained": sum(bool(item["score_delta"]) and not item["score_delta_explained"] for item in changed),
            "by_driver": {driver: sum(item["position_driver"] == driver for item in changed)
                          for driver in ("faixa", "valor", "sinais", "outros_skus", "criterio")},
        },
    }


def _payload_reason(run: dict, key: str, label: str) -> str | None:
    comparison = run.get("comparison")
    if not isinstance(comparison, dict):
        return f"Execução #{run['id']} foi registrada antes da comparação ampliada e não preserva {label}."
    if comparison.get("schema_version") != SCHEMA_VERSION:
        return f"Execução #{run['id']} usa formato de snapshot {comparison.get('schema_version')}, incompatível com a versão {SCHEMA_VERSION}."
    if comparison.get(key) is None:
        extra = comparison.get("b2b_unavailable_reason") if key == "b2b_coverage" else None
        return f"Execução #{run['id']} não registrou {label}." + (f" Motivo: {extra}" if extra else "")
    return None


def _field_changes(base: dict, target: dict, fields: dict[str, str], prefix: str) -> list[dict[str, Any]]:
    return [{"field": f"{prefix}.{key}", "label": label, "base": base.get(key), "target": target.get(key), "delta": _delta(base.get(key), target.get(key))}
            for key, label in fields.items() if base.get(key) != target.get(key)]


def _compare_forecasts(base: dict, target: dict) -> dict[str, Any]:
    reason = _payload_reason(base, "forecasts", "previsão e recomendação") or _payload_reason(target, "forecasts", "previsão e recomendação")
    if reason:
        return {"available": False, "reason": reason}
    left, right = base["comparison"], target["comparison"]
    common = sorted(set(left["forecasts"]) & set(right["forecasts"]))
    items = []
    for sku in common:
        changes = _field_changes(left["forecasts"][sku], right["forecasts"][sku], FORECAST_FIELDS, "forecast")
        changes += _field_changes(left["recommendations"].get(sku) or {}, right["recommendations"].get(sku) or {}, RECOMMENDATION_FIELDS, "recommendation")
        if changes:
            items.append({"sku": sku, "changes": changes})
    fields = lambda name: sum(any(change["field"] == name for change in item["changes"]) for item in items)  # noqa: E731
    return {
        "available": True,
        "items": items,
        "only_in_base": sorted(set(left["forecasts"]) - set(right["forecasts"])),
        "only_in_target": sorted(set(right["forecasts"]) - set(left["forecasts"])),
        "summary": {
            "compared_skus": len(common), "changed_skus": len(items),
            "action_changes": fields("recommendation.action"),
            "quantity_changes": fields("recommendation.suggested_quantity"),
            "model_changes": fields("forecast.model"),
            "forecast_changes": fields("forecast.forecast_next_month"),
        },
    }


def _compare_b2b(base: dict, target: dict) -> dict[str, Any]:
    reason = _payload_reason(base, "b2b_coverage", "cobertura B2B2C") or _payload_reason(target, "b2b_coverage", "cobertura B2B2C")
    if reason:
        return {"available": False, "reason": reason}
    left, right = base["comparison"]["b2b_coverage"], target["comparison"]["b2b_coverage"]
    items = []
    for code in sorted(set(left["partners"]) & set(right["partners"])):
        changes = _field_changes(left["partners"][code], right["partners"][code], PARTNER_FIELDS, "partner")
        if changes:
            items.append({"partner": code, "name": right["partners"][code].get("name"), "changes": changes})
    return {
        "available": True,
        "base_reference_month": left["reference_month"],
        "target_reference_month": right["reference_month"],
        "items": items,
        "entered_partners": sorted(set(right["partners"]) - set(left["partners"])),
        "exited_partners": sorted(set(left["partners"]) - set(right["partners"])),
        "summary": {"compared_partners": len(set(left["partners"]) & set(right["partners"])), "changed_partners": len(items)},
    }


def compare_runs(base: dict, target: dict) -> dict[str, Any]:
    """Compare two stored snapshots; sections without compatible data are refused with a reason."""
    base_meta, target_meta = _meta(base), _meta(target)
    commercial_base = (base.get("comparison") or {}).get("commercial_thresholds")
    commercial_target = (target.get("comparison") or {}).get("commercial_thresholds")
    notes = []
    if str(target["created_at"]) < str(base["created_at"]):
        notes.append("A execução alvo é anterior à base; as variações indicam o caminho da mais nova para a mais antiga.")
    context = {
        "source_changed": base["source_hash"] != target["source_hash"],
        "weights_changes": _dict_changes(base.get("weights"), target.get("weights")),
        "thresholds_changes": _dict_changes(base.get("thresholds"), target.get("thresholds")),
        "commercial_thresholds": (
            {"available": True, "changes": _dict_changes(commercial_base, commercial_target)}
            if commercial_base is not None and commercial_target is not None else
            {"available": False, "reason": "Limiares comerciais só são preservados em execuções registradas com a comparação ampliada."}
        ),
    }
    if not context["source_changed"] and not context["weights_changes"] and not context["thresholds_changes"]:
        notes.append("Mesma planilha e mesma configuração operacional: diferenças no ranking indicariam mudança de código entre as execuções.")
    sections = {"ranking": _compare_ranking(base, target), "forecasts": _compare_forecasts(base, target), "b2b_coverage": _compare_b2b(base, target)}
    return {
        "base": base_meta,
        "target": target_meta,
        "context": context,
        "comparable": any(section["available"] for section in sections.values()),
        **sections,
        "notes": notes,
        "limitations": [
            "A comparação usa somente o que cada snapshot preservou; nada é recalculado retroativamente.",
            "Cobertura B2B2C é comparada por parceiro cadastrado; dados globais de estoque, produção e forecast não são distribuídos.",
            "A explicação decompõe o score em sinais e pesos; a causa operacional de um novo sinal está nos valores de evidência.",
            "Com faixa e valor em risco nos dois snapshots, a posição é explicada por faixa, depois valor, depois sinais (desempate).",
        ],
    }
