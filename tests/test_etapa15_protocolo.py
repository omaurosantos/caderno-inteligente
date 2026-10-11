"""Etapa 15.0: protocolo gravado antes do código (configurações, pesos e casos congelados pendentes)."""
from __future__ import annotations

import copy
import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app, data
from caderno_inteligente.forecast_engine_config import DEFAULTS, load_engine_config
from caderno_inteligente.partner_insights import load_commercial_thresholds
from caderno_inteligente.prioritization import load_weights
from caderno_inteligente.supply_plan import load_supply_settings
from caderno_inteligente.validation_center import _check, evaluate_frozen_cases, load_validation_config

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "config/validation_center.json"
NEW_CODES = {"PROJECTED_SHORTFALL", "CAPACITY_SHORTFALL", "OP_FOR_DISCONTINUED", "PARTNER_STOCK_BUILDUP", "PROJECTED_EXCESS"}
SUBSTEPS = {"15.1", "15.2", "15.3", "15.4", "15.5"}


def test_peak_evaluation_protocol_is_unchanged_since_15_0():
    config = load_engine_config()
    assert config["evaluation"] == {"first_origin": "2025-11", "last_origin": "2026-05", "horizon_months": 3,
                                    "peak_months": [11, 1, 2], "max_abs_peak_bias": 0.10}


@pytest.mark.parametrize("change", [
    {"first_origin": "2026-06", "last_origin": "2026-05"},
    {"first_origin": "2025-13"},
    {"peak_months": [11, 11]},
    {"peak_months": [13]},
    {"max_abs_peak_bias": 0},
    {"origens": "2025-11"},
])
def test_invalid_evaluation_protocol_is_rejected(tmp_path, change):
    values = deepcopy(DEFAULTS)
    values["evaluation"] = {**values["evaluation"], **change}
    path = tmp_path / "forecast_engine.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(ValueError):
        load_engine_config(path)


def test_supply_plan_settings_load_from_the_versioned_file():
    assert load_supply_settings() == {"reference_date": "2026-09-14", "decision_window_weeks": 4, "target_cover_weeks": 4,
                                      "excess_coverage_days": 90, "days_per_month": 30.4}


@pytest.mark.parametrize("change", [
    {"reference_date": "2026-09-15"},  # terça-feira: as semanas da capacidade começam na segunda
    {"reference_date": "14/09/2026"},
    {"decision_window_weeks": 0},
    {"days_per_month": 45},
    {"horizonte": 6},
])
def test_invalid_supply_plan_settings_are_rejected(tmp_path, change):
    path = tmp_path / "supply_plan.json"
    path.write_text(json.dumps({**load_supply_settings(), **change}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_supply_settings(path)


def test_partner_buildup_thresholds_are_versioned_and_validated(tmp_path):
    values = load_commercial_thresholds(ROOT / "config/commercial_thresholds.json")
    assert {key: values[key] for key in ("buildup_months", "buildup_max_sell_through", "buildup_min_stock_growth", "stock_identity_tolerance")} == {
        "buildup_months": 6, "buildup_max_sell_through": 0.9, "buildup_min_stock_growth": 0.3, "stock_identity_tolerance": 1}
    for change in ({"buildup_months": 1}, {"buildup_months": 2.5}, {"buildup_max_sell_through": 1.2}):
        path = tmp_path / "commercial.json"
        path.write_text(json.dumps({**values, **change}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_commercial_thresholds(path)


def test_new_rule_weights_exist_and_only_the_later_rules_are_still_silent():
    assert NEW_CODES <= set(load_weights(ROOT / "config/prioritization_weights.json"))
    _, _, issues, _ = data()
    emitted = set(issues["code"])
    assert {"PROJECTED_SHORTFALL", "OP_FOR_DISCONTINUED", "PROJECTED_EXCESS", "CAPACITY_SHORTFALL"} <= emitted  # Etapas 15.3 e 15.4
    assert "CAPACITY_CONFLICT" not in emitted  # substituída na 15.4 (D4)
    assert "PARTNER_STOCK_BUILDUP" in emitted  # Etapa 15.5


def test_stage_15_cases_are_pending_until_their_substep_except_the_regression_guard():
    cases = {case["id"]: case for case in load_validation_config(VALIDATION)["cases"]}
    stage = [cases[f"VC-{number}"] for number in range(20, 31)]
    assert {case["pending_until"] for case in stage if "pending_until" in case} <= SUBSTEPS
    # Liberados ao longo da Etapa 15 (VC-27 desde a 15.0); na 15.5 nenhum caso fica pendente.
    assert {case["id"] for case in stage if "pending_until" not in case} == {f"VC-{number}" for number in range(20, 31)}


def _with_pending(monkeypatch):
    """A Etapa 15 terminou sem pendentes; o comportamento continua testado com um caso marcado em memória."""
    import backend.validation as validation_router

    original = validation_router.load_validation_config

    def patched(path):
        config = original(path)
        config["cases"] = [{**case, "pending_until": "15.x"} if case["id"] == "VC-24" else case for case in config["cases"]]
        return config

    monkeypatch.setattr(validation_router, "load_validation_config", patched)


def test_pending_cases_are_listed_but_not_counted_as_passed_or_failed(monkeypatch):
    real = TestClient(app).get("/api/validation/summary").json()["frozen_cases"]
    # Etapa 16: VC-31 liberado na 16.1 e VC-32 a VC-34 no fechamento da Onda 2 (16.2/16.3): nenhum caso pendente.
    pending_ids = {item["id"] for item in real["items"] if item["result"] == "pendente"}
    assert pending_ids == set() and real["failed"] == real["not_found"] == 0 and real["passed"] == real["total"] == 34
    _with_pending(monkeypatch)
    body = TestClient(app).get("/api/validation/summary").json()["frozen_cases"]
    items = {item["id"]: item for item in body["items"]}
    assert body["pending"] == 1
    assert items["VC-24"]["result"] == "pendente" and items["VC-24"]["checks"] == [] and items["VC-24"]["pending_until"] == "15.x"
    assert body["failed"] == 0 and body["not_found"] == 0


def test_pending_marker_skips_execution_even_for_unknown_kinds():
    config = load_validation_config(VALIDATION)
    only = copy.deepcopy(config)
    only["cases"] = [{**case, "pending_until": "15.x"} for case in only["cases"] if case["id"] in {"VC-28", "VC-29"}]
    empty = {"indicators": pd.DataFrame(columns=["SKU"]), "issues": pd.DataFrame(columns=["sku", "code"]),
             "ranking": pd.DataFrame(columns=["sku", "priority"]), "forecasts": pd.DataFrame(columns=["sku"]),
             "partner_items": [], "thresholds": {}}
    result = evaluate_frozen_cases(only, **empty, source_sha256=config["frozen_source_sha256"])
    assert [item["result"] for item in result["items"]] == ["pendente", "pendente"]
    assert result["pending"] == 2 and result["passed"] == result["failed"] == 0


def test_includes_any_check():
    assert _check("signals", {"includes_any": ["A", "B"]}, ["B", "C"])["passed"] is True
    assert _check("signals", {"includes_any": ["A", "B"]}, ["C"])["passed"] is False
    assert _check("signals", {"includes_any": ["A"]}, None)["passed"] is False


def test_decision_snapshot_is_read_only_and_deterministic():
    sys.path.insert(0, str(ROOT / "scripts"))
    import snapshot_decisions

    guarded = [ROOT / "runtime" / name for name in ("feedback.db", "cases.db", "runs.db")]
    before = {path: path.stat().st_mtime_ns for path in guarded if path.exists()}
    first = snapshot_decisions.build_snapshot()
    second = snapshot_decisions.build_snapshot()
    assert first == second
    assert len(first["skus"]) == 50 and len(first["top10"]) == 10
    assert first["source_sha256"] == load_validation_config(VALIDATION)["frozen_source_sha256"]
    assert {path: path.stat().st_mtime_ns for path in guarded if path.exists()} == before


def test_pending_cases_are_not_reported_as_known_failures(monkeypatch):
    _with_pending(monkeypatch)
    body = TestClient(app).get("/api/validation/summary").json()
    pending = {item["id"] for item in body["frozen_cases"]["items"] if item["result"] == "pendente"}
    assert pending and not any(case in failure["description"] for failure in body["known_failures"] for case in pending)


def test_before_after_comparison_reports_the_stage_15_cases():
    sys.path.insert(0, str(ROOT / "scripts"))
    import snapshot_decisions

    before = json.loads((ROOT / "docs/etapa-15/antes.json").read_text(encoding="utf-8"))
    after = json.loads((ROOT / "docs/etapa-15/depois.json").read_text(encoding="utf-8"))
    report = snapshot_decisions.compare(before, after)
    assert "| `sem_acao_necessaria` | 30 | 0 |" in report
    assert "| KA-02 · CI-0009: ação comercial | `investigar_divergencia` | `conter_reposicao` |" in report
    assert "## Capacidade (depois)" in report
    # O script é compartilhado com a Etapa 16 (título e frase de origem mudaram); as tabelas do relatório gravado continuam as mesmas.
    saved = (ROOT / "docs/etapa-15/antes-depois.md").read_text(encoding="utf-8")
    assert [line for line in saved.splitlines() if line.startswith("|")] == [line for line in report.splitlines() if line.startswith("|")]
