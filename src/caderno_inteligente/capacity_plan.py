"""Capacidade semanal finita (Etapa 15.4): encaixa as ordens planejadas na capacidade livre de cada linha.

`Capacidade_Semanal.Capacidade disponível` já desconta os compromissos base e as OPs existentes (LEIA_ME), então só as
ordens planejadas da Etapa 15.3 consomem essa sobra. Premissas, declaradas na tela:

- capacidade em unidades homogêneas dentro da família (linha);
- a ordem consome capacidade na semana de início (= liberação), como a coluna "Ordens planejadas" da base;
- "compromissos base" é demanda não detalhada (não validado com a empresa);
- não há capacidade informada depois da última semana do calendário: ordem que começa depois fica "a confirmar" ou, com a
  extensão de `config/capacity_extension.json` ligada (Etapa 16.5), usa capacidade ESTIMADA (central: máxima menos a média
  dos compromissos base recentes; conservador: menor disponível observada), sempre marcada como estimada.

Alocação: por data de necessidade, depois curva ABC e SKU. A ordem usa a semana de liberação; se faltar, antecipa
semana a semana até a data de planejamento (pré-produção). O que não couber fica sem programação (`insuficiente`).
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

STATUS_ORDER = {"ok": 0, "pre_producao": 1, "ok_estimado": 2, "a_confirmar": 3, "insuficiente_estimado": 4, "insuficiente": 5}
STATUS_LABELS = {"ok": "Cabe na semana planejada", "pre_producao": "Cabe com pré-produção", "a_confirmar": "Capacidade a confirmar (fora do calendário)",
                 "insuficiente": "Não cabe até a data de necessidade"}
ESTIMATED_LABELS = {"ok_estimado": "Cabe na capacidade estimada", "insuficiente_estimado": "Não cabe nem na capacidade estimada"}
EXTENSION_PATH = Path(__file__).resolve().parents[2] / "config/capacity_extension.json"
EXTENSION_KEYS = {"enabled", "method", "scenario", "lookback_weeks", "conservative_method"}
CENTRAL_METHODS = {"media_compromissos_8_semanas"}
CONSERVATIVE_METHODS = {"minimo_disponivel_observado"}
SCENARIOS = ("central", "conservador")
ASSUMPTIONS = [
    "Capacidade disponível da base já desconta compromissos base e OPs existentes; só as ordens planejadas consomem a sobra.",
    "Capacidade em unidades homogêneas dentro da família; a ordem consome capacidade na semana de início (liberação).",
    "Compromissos base são demanda não detalhada; a premissa não foi validada com a empresa.",
    "Não há capacidade informada depois da última semana do calendário: ordens que começariam depois ficam a confirmar.",
    "Antecipação de OP e redução de OP não liberam nem consomem capacidade nesta conta (conservador).",
]
ESTIMATED_ASSUMPTION = ("Semanas além do calendário da base são estimadas: central = capacidade máxima menos a média dos compromissos base das "
                        "últimas {weeks} semanas observadas; conservador = menor capacidade disponível observada. Não é capacidade informada pela empresa.")
FIELD_NATURE = {
    "available": {"nature": "observado na fonte", "origin": "Capacidade_Semanal.Capacidade disponível"},
    "allocated": {"nature": "calculado", "origin": "ordens planejadas da projeção (Etapa 15.3) encaixadas na semana de liberação ou antes"},
    "status": {"nature": "calculado", "origin": "alocação: ok, pré-produção, a confirmar ou insuficiente"},
}


def load_capacity_extension(path: str | Path | None = None) -> dict[str, Any]:
    """Lê `config/capacity_extension.json` (chaves estritas); `path=None` usa o arquivo padrão."""
    return _validate_extension(json.loads(Path(path or EXTENSION_PATH).read_text(encoding="utf-8")))


def _validate_extension(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict) or set(values) != EXTENSION_KEYS:
        raise ValueError("Configuração de capacidade estimada com campos ausentes ou desconhecidos")
    if not isinstance(values["enabled"], bool):
        raise ValueError("Parâmetro de capacidade estimada inválido: enabled")
    lookback = values["lookback_weeks"]
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
        raise ValueError("Parâmetro de capacidade estimada precisa ser inteiro positivo: lookback_weeks")
    if values["method"] not in CENTRAL_METHODS or values["conservative_method"] not in CONSERVATIVE_METHODS:
        raise ValueError("Método de capacidade estimada desconhecido")
    if values["scenario"] not in SCENARIOS:
        raise ValueError("Cenário de capacidade estimada desconhecido")
    return dict(values)


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _calendar(capacity: pd.DataFrame) -> dict[str, dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    has_base = "Compromissos base" in capacity.columns
    for _, row in capacity.sort_values("Semana inicial").iterrows():
        family = str(row["Família"])
        start = pd.Timestamp(row["Semana inicial"]).date()
        entry = families.setdefault(family, {"line": str(row.get("Linha") or ""), "weeks": {}})
        base = float(row["Compromissos base"]) if has_base and pd.notna(row["Compromissos base"]) else None
        entry["weeks"][_week(start)] = {"available": float(row["Capacidade disponível"]), "maximum": float(row["Capacidade máxima"]),
                                        "occupation": float(row["Ocupação"]), "base": base}
    return families


def _estimated_weeks(calendar: dict[str, dict[str, Any]], extension: dict[str, Any], last_release: dict[str, date]) -> dict[str, dict[date, dict[str, Any]]]:
    """Semanas estimadas por família e cenário: da semana seguinte ao calendário até a semana da última liberação."""
    result: dict[str, dict[date, dict[str, Any]]] = {}
    for family, item in calendar.items():
        weeks = sorted(item["weeks"])
        recent = [item["weeks"][week]["base"] for week in weeks[-extension["lookback_weeks"]:]]
        if not weeks or family not in last_release or any(value is None for value in recent):
            continue  # sem compromissos base observados a estimativa fica indisponível e a ordem segue "a confirmar"
        average = sum(recent) / len(recent)
        maximum = item["weeks"][weeks[-1]]["maximum"]
        floor = min(item["weeks"][week]["available"] for week in weeks)
        week = weeks[-1] + timedelta(days=7)
        estimated: dict[date, dict[str, Any]] = {}
        while week <= _week(last_release[family]):
            estimated[week] = {"maximum": maximum, "central": max(0.0, maximum - average), "conservador": floor}
            week += timedelta(days=7)
        if estimated:
            result[family] = estimated
    return result


def _allocate(plans: dict[str, dict[str, Any]], info: dict[str, Any], weeks_by_family: dict[str, dict[date, float]],
              estimated: dict[str, set[date]], reference_week: date) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[date, float]]]:
    """Encaixa as ordens planejadas nas semanas (consome `weeks_by_family`); devolve os resultados por SKU e o alocado por semana."""
    allocated = {family: {week: 0.0 for week in weeks} for family, weeks in weeks_by_family.items()}
    queue = []
    for sku, plan in plans.items():
        for index, order in enumerate(plan.get("planned_orders") or []):
            row = info.get(sku, {})
            queue.append((order["due_date"], str(row.get("abc_curve") or "Z"), sku, index, order, str(row.get("family") or "")))
    results: dict[str, list[dict[str, Any]]] = {sku: [] for sku in plans}
    for due, _, sku, index, order, family in sorted(queue, key=lambda item: item[:4]):
        weeks = weeks_by_family.get(family)
        release_week = max(_week(date.fromisoformat(order["release_date"])), reference_week)
        entry = {"index": index, "due_date": order["due_date"], "release_date": order["release_date"], "quantity": order["quantity"],
                 "family": family, "allocations": [], "unscheduled": 0.0}
        if not weeks or release_week > max(weeks):
            entry["status"] = "a_confirmar"
            results[sku].append(entry)
            continue
        need = float(order["quantity"])
        for week in sorted((week for week in weeks if reference_week <= week <= release_week), reverse=True):
            take = min(need, weeks[week])
            if take <= 0:
                continue
            weeks[week] -= take
            allocated[family][week] += take
            need -= take
            entry["allocations"].append({"week_start": week.isoformat(), "quantity": round(take, 1)})
            if need <= 0:
                break
        entry["unscheduled"] = round(need, 1)
        early = any(item["week_start"] < release_week.isoformat() for item in entry["allocations"])
        entry["status"] = "insuficiente" if need > 0 else "pre_producao" if early else "ok"
        marked = estimated.get(family, set())
        if marked:
            used = any(date.fromisoformat(item["week_start"]) in marked for item in entry["allocations"])
            if entry["status"] == "insuficiente" and release_week in marked:
                entry["status"] = "insuficiente_estimado"
            elif entry["status"] != "insuficiente" and used:
                entry["status"] = "ok_estimado"
            for item in entry["allocations"]:
                item["nature"] = "estimada" if date.fromisoformat(item["week_start"]) in marked else "observada"
        results[sku].append(entry)
    return results, allocated


def _worst(statuses: Any) -> str:
    return max(statuses, key=STATUS_ORDER.get, default="ok")


def build_capacity_plan(plans: dict[str, dict[str, Any]], indicators: pd.DataFrame, capacity: pd.DataFrame,
                        orders: pd.DataFrame | None = None, reference_date: str | None = None, peak_months: list[int] | None = None,
                        extension: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aloca as ordens planejadas e devolve o resultado por SKU, por família e semana e o resumo por família.

    `extension=None` carrega `config/capacity_extension.json`; com `enabled: false` a saída é a de antes da Etapa 16.5.
    """
    extension = load_capacity_extension() if extension is None else _validate_extension(extension)
    calendar = _calendar(capacity)
    info = {str(row["SKU"]): row for row in indicators.to_dict("records")}
    reference = date.fromisoformat(reference_date) if reference_date else min((week for item in calendar.values() for week in item["weeks"]), default=date.today())
    reference_week = _week(reference)
    peaks = set(peak_months or [])

    last_release: dict[str, date] = {}
    for sku, plan in plans.items():
        family = str(info.get(sku, {}).get("family") or "")
        for order in plan.get("planned_orders") or []:
            released = date.fromisoformat(order["release_date"])
            last_release[family] = max(last_release.get(family, released), released)
    extra = _estimated_weeks(calendar, extension, last_release) if extension["enabled"] else {}
    active = bool(extra)

    def run(scenario: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[date, float]], dict[str, dict[date, float]]]:
        remaining = {family: {week: values["available"] for week, values in item["weeks"].items()} for family, item in calendar.items()}
        for family, weeks in extra.items():
            remaining[family].update({week: values[scenario] for week, values in weeks.items()})
        marked = {family: set(weeks) for family, weeks in extra.items()}
        results, allocated = _allocate(plans, info, remaining, marked, reference_week)
        return results, allocated, remaining

    results, allocated, remaining = run(extension["scenario"])
    scenario_results = {extension["scenario"]: results}
    if active:
        other = next(name for name in SCENARIOS if name != extension["scenario"])
        scenario_results[other] = run(other)[0]

    skus = {}
    for sku, entries in results.items():
        plan = plans[sku]
        urgent = [entry for entry, order in zip(sorted(entries, key=lambda e: e["index"]), plan.get("planned_orders") or []) if order.get("urgent")]
        worst = _worst(entry["status"] for entry in entries)
        worst_now = _worst(entry["status"] for entry in urgent)
        skus[sku] = {
            "status": worst if entries else "sem_ordens",
            "status_now": worst_now if urgent else "sem_ordens",
            "status_label": {**STATUS_LABELS, **(ESTIMATED_LABELS if active else {})}.get(worst, "Sem ordens planejadas"),
            "unscheduled_quantity": round(sum(entry["unscheduled"] for entry in entries), 1),
            "executable_quantity_now": round(sum(entry["quantity"] - entry["unscheduled"] for entry in urgent), 1),
            "orders": sorted(entries, key=lambda entry: entry["index"]),
            "family": str(info.get(sku, {}).get("family") or ""),
        }

    open_orders = orders if orders is not None else pd.DataFrame(columns=["SKU"])
    short_statuses = ("insuficiente", "insuficiente_estimado")
    families = []
    for family, item in calendar.items():
        members = [sku for sku, value in skus.items() if value["family"] == family]
        entries = [entry for sku in members for entry in skus[sku]["orders"]]
        short = [entry for entry in entries if entry["status"] in short_statuses]
        peak_entries = [entry for entry in entries if date.fromisoformat(entry["due_date"]).month in peaks]
        peak_status = _worst(entry["status"] for entry in peak_entries) if peak_entries else None
        short_skus = sorted({sku for sku in members if skus[sku]["status"] in short_statuses})
        affected = open_orders[open_orders["SKU"].isin(short_skus)] if short_skus and not open_orders.empty else open_orders.iloc[0:0]
        weeks = sorted(item["weeks"])
        estimated_weeks = sorted(extra.get(family, {}))
        row = {
            "family": family, "line": item["line"],
            "calendar_start": weeks[0].isoformat() if weeks else None, "calendar_end": (weeks[-1] + timedelta(days=6)).isoformat() if weeks else None,
            "available_until_calendar_end": round(sum(values["available"] for values in item["weeks"].values()), 1),
            "planned_in_calendar": round(sum(allocated[family][week] for week in weeks), 1),
            "planned_after_calendar": round(sum(entry["quantity"] for entry in entries if entry["status"] == "a_confirmar"), 1),
            "unscheduled_quantity": round(sum(entry["unscheduled"] for entry in short), 1),
            "first_shortfall_due": min((entry["due_date"] for entry in short), default=None),
            "status": _worst(entry["status"] for entry in entries),
            "peak_months": sorted(peaks), "peak_need_units": round(sum(entry["quantity"] for entry in peak_entries), 1), "peak_status": peak_status,
            "skus_short": short_skus,
            "affected_orders": [{"order": str(order["Pedido"]), "sku": str(order["SKU"]), "client": str(order["Cliente/Canal"]), "quantity": float(order["Quantidade"])}
                                for _, order in affected.iterrows()],
            "weeks": [{"week_start": week.isoformat(), "maximum": item["weeks"][week]["maximum"], "available": item["weeks"][week]["available"],
                       "allocated": round(allocated[family][week], 1), "remaining": round(remaining[family][week], 1),
                       "occupation_base": item["weeks"][week]["occupation"], **({"nature": "observada", "method": None} if active else {})}
                      for week in weeks],
        }
        if active:
            method = extension["method"] if extension["scenario"] == "central" else extension["conservative_method"]
            row["weeks"] += [{"week_start": week.isoformat(), "maximum": extra[family][week]["maximum"], "available": round(extra[family][week][extension["scenario"]], 1),
                              "allocated": round(allocated[family][week], 1), "remaining": round(remaining[family][week], 1),
                              "occupation_base": None, "nature": "estimada", "method": method} for week in estimated_weeks]
            row["estimated_from"] = estimated_weeks[0].isoformat() if estimated_weeks else None
            row["planned_in_estimated"] = round(sum(allocated[family][week] for week in estimated_weeks), 1)
            row["scenarios"] = {}
            for name in SCENARIOS:
                scenario_entries = [entry for sku in members for entry in scenario_results[name][sku]]
                scenario_peak = [entry for entry in scenario_entries if date.fromisoformat(entry["due_date"]).month in peaks]
                row["scenarios"][name] = {"peak_status": _worst(entry["status"] for entry in scenario_peak) if scenario_peak else None,
                                          "unscheduled_quantity": round(sum(entry["unscheduled"] for entry in scenario_entries), 1)}
        families.append(row)
    families.sort(key=lambda family: (-STATUS_ORDER[family["status"]], family["family"]))
    assumptions = list(ASSUMPTIONS)
    labels = dict(STATUS_LABELS)
    field_nature = dict(FIELD_NATURE)
    if active:
        assumptions[3] = ESTIMATED_ASSUMPTION.format(weeks=extension["lookback_weeks"])
        labels.update(ESTIMATED_LABELS)
        field_nature["status"] = {"nature": "calculado", "origin": "alocação: ok, pré-produção, a confirmar, insuficiente ou a variante estimada (ok_estimado, insuficiente_estimado)"}
        field_nature["estimated_available"] = {"nature": "estimado", "origin": f"capacidade máxima menos a média dos compromissos base das últimas {extension['lookback_weeks']} semanas (central) ou menor disponível observada (conservador)"}
    elif extension["enabled"]:
        assumptions.append("Capacidade estimada indisponível: faltam compromissos base observados na aba Capacidade_Semanal; mantido a confirmar.")
    return {"reference_date": reference.isoformat(), "skus": skus, "families": families, "assumptions": assumptions,
            "field_nature": field_nature, "status_labels": labels,
            "extension": {key: extension[key] for key in ("enabled", "method", "lookback_weeks", "scenario")}}
