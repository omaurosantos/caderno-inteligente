import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app

ROOT = Path(__file__).resolve().parents[1]
GUARDED_FILES = [
    ROOT / "config/prioritization_weights.json",
    ROOT / "config/rule_thresholds.json",
    ROOT / "config/commercial_thresholds.json",
    ROOT / "data/source/Base de Dados - Caderno Inteligente.xlsm",
]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validation_summary_contract():
    response = TestClient(app).get("/api/validation/summary")
    assert response.status_code == 200
    body = response.json()
    assert {"process_comparison", "analysis_time", "forecast_evaluation", "frozen_cases", "safe_behavior",
            "known_failures", "known_limitations", "adjustments", "requires_human_review", "source"} <= set(body)
    assert body["requires_human_review"] is True
    natures = {(row["informed"]["nature"], row["recalculated"]["nature"]) for row in body["process_comparison"]}
    assert natures == {("informado", "recalculado")}
    cases = body["frozen_cases"]
    assert len(cases["items"]) == 34
    assert cases["passed"] + cases["failed"] + cases["not_found"] + cases["pending"] == 34
    # Fechamento da Onda 2 (Etapa 16.2–16.4): os 34 casos passam, nenhum pendente; VC-20 revisto para Priorizar parceiro.
    results = {item["id"]: item["result"] for item in cases["items"]}
    assert all(result == "passou" for result in results.values()) and cases["pending"] == 0 and cases["failed"] == 0
    by_id = {item["id"]: item for item in cases["items"]}
    assert by_id["VC-20"]["obtained"]["challenge_code"] == "priorizar_parceiro" and by_id["VC-20"]["obtained"]["lever"] == "alocar"
    assert by_id["VC-33"]["obtained"]["contested"] is True and set(by_id["VC-33"]["obtained"]["ranked_clients"]) >= {"KA-02", "KA-05"}
    assert by_id["VC-32"]["obtained"]["value_at_risk_estimated"] is None and by_id["VC-32"]["obtained"]["outranks_higher_value_active"] is False
    for item in cases["items"]:
        assert item["result"] in {"passou", "falhou", "nao_encontrado", "pendente"}
        assert item["limitation"] and item["adjustment"]
    # Só a Etapa 15 muda modelo ou pesos, e sempre com a evidência da subetapa no histórico.
    for entry in body["adjustments"]:
        assert entry["changed_weights_or_models"] is False or "docs/historico.md — Etapa 15." in entry["evidence"]


def test_forecast_evaluation_reports_sample_and_matches_existing_backtest():
    client = TestClient(app)
    evaluation = client.get("/api/validation/summary").json()["forecast_evaluation"]
    forecasts = {item["sku"]: item["forecast"] for item in client.get("/api/forecasts").json()}
    assert evaluation["eligible_skus"] + evaluation["insufficient_skus"] == evaluation["total_skus"] == len(forecasts)
    assert evaluation["beat_baseline_skus"] + evaluation["did_not_beat_baseline_skus"] + evaluation["not_comparable_skus"] == evaluation["eligible_skus"]
    for item in evaluation["items"]:
        assert item["selected_model"] == forecasts[item["sku"]]["model"]
        assert item["selected_wape"] == forecasts[item["sku"]]["backtest_wape"]
    roles = [row["role"] for row in evaluation["models"]]
    assert roles.count("baseline") == 1 and roles.count("selecionado") == 1


def test_known_failures_expose_models_that_did_not_beat_baseline():
    body = TestClient(app).get("/api/validation/summary").json()
    if body["forecast_evaluation"]["did_not_beat_baseline_skus"]:
        assert any(item["area"] == "previsão" for item in body["known_failures"])


def test_validation_summary_preserves_ranking_forecasts_and_files():
    client = TestClient(app)
    before = {path: _digest(path) for path in GUARDED_FILES}
    priorities = client.get("/api/priorities").json()
    forecasts = client.get("/api/forecasts").json()
    overview = client.get("/api/overview").json()
    assert client.get("/api/validation/summary").status_code == 200
    assert client.get("/api/priorities").json() == priorities
    assert client.get("/api/forecasts").json() == forecasts
    assert client.get("/api/overview").json() == overview
    assert {path: _digest(path) for path in GUARDED_FILES} == before


def test_validation_summary_survives_unavailable_persistence():
    class Broken:
        kind = "broken"

        def list_feedback(self):
            raise RuntimeError("database offline")

    from fastapi import FastAPI
    from backend.validation import create_validation_router

    isolated = FastAPI()
    isolated.include_router(create_validation_router(
        pipeline=main.pipeline, persistence=lambda: Broken(), recommendations=main._all_operational_recommendations,
        sku_detail=main.detail, source=main.SOURCE, config_file=ROOT / "config/validation_center.json",
        thresholds_file=main.THRESHOLDS_FILE, commercial_thresholds_file=ROOT / "config/commercial_thresholds.json",
    ))
    body = TestClient(isolated).get("/api/validation/summary").json()
    assert body["analysis_time"]["records_with_minutes"] == 0
    assert "indisponível" in body["analysis_time"]["note"]
    assert any(item["area"] == "tempo de análise" for item in body["known_failures"])
    # Persistência caída: o valor endereçado é ausente com motivo, nunca R$ 0.
    assert body["addressed_value"]["observed_total"] is None and "Persistência indisponível" in body["addressed_value"]["missing_reason"]


def test_safe_behavior_includes_missing_sku_and_api_error_coverage():
    checks = {item["id"]: item for item in TestClient(app).get("/api/validation/summary").json()["safe_behavior"]}
    assert checks["missing_sku"]["status"] == "aprovado"
    assert checks["api_error"]["status"] == "coberto_por_teste"
    assert {"missing_sell_out", "zero_holdout", "insufficient_forecast", "aggregated_capacity", "human_review", "no_false_precision"} <= set(checks)


def test_validation_summary_exposes_impact_metrics():
    body = TestClient(app).get("/api/validation/summary").json()
    addressed, sop = body["addressed_value"], body["sop_divergence"]
    assert addressed["nature"] == "observado" and addressed["note"]
    assert (addressed["observed_total"] is None) == (addressed["sku_count"] == 0)  # sem decisão com valor: ausente, não R$ 0
    assert addressed["observed_total"] is not None or addressed["missing_reason"]
    assert sop["requires_human_review"] is True
    assert addressed["sku_count"] == len(addressed["decided_skus"]) - len(addressed["skus_without_value"])
    assert sop["threshold"] == 0.2 and sop["note"] and set(sop["months"]) <= {"2026-10", "2026-11", "2026-12"}
    assert all(abs(item["ratio"]) > 0.2 and item["month"] in sop["months"] for item in sop["items"]) and sop["count"] == len(sop["items"])

def test_rebuilt_allocation_matches_the_pipeline_order_for_every_sku():
    """Sem a alocação do pipeline, a validação recalcula pelo mesmo núcleo; a ordem e a disputa devem ser as mesmas da API."""
    from caderno_inteligente.partner_insights import build_partner_insights, load_commercial_thresholds
    from caderno_inteligente.validation_center import _base_allocation

    dataset = main.pipeline()[0]
    partner_items = build_partner_insights(dataset, load_commercial_thresholds(ROOT / "config/commercial_thresholds.json"))["items"]
    plans, piped = main.supply_plans(), main.allocation()["skus"]
    for sku, entry in piped.items():
        rebuilt = _base_allocation(sku, plans, partner_items, None)[0]
        assert rebuilt["contested"] == entry["contested"], sku
        assert [(row["order"], row["uncovered_at_promise"]) for row in rebuilt["orders"]] == [(row["order"], row["uncovered_at_promise"]) for row in entry["orders"]], sku
