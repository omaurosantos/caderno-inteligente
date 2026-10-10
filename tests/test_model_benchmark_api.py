from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.main as main
from backend.model_benchmark import create_model_benchmark_router
from caderno_inteligente.benchmark_store import save_benchmark_run

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = hashlib.sha256(main.SOURCE.read_bytes()).hexdigest()


def _client(db: Path) -> TestClient:
    app = FastAPI()
    app.include_router(create_model_benchmark_router(pipeline=main.pipeline, source=main.SOURCE,
                                                     engine_config_file=main.ENGINE_CONFIG_FILE, benchmark_db=db))
    return TestClient(app)


def _result(model, wape, status="ok"):
    return {"model": model, "label": model, "library": "test", "library_version": None, "params": {}, "status": status,
            "error_message": None, "wape": wape, "peak_wape": wape, "normal_wape": wape, "bias": 0.0,
            "evaluated_points": 1050, "fallback_points": 0, "duration_seconds": 1.0}


def _save(db, results, source_hash=SOURCE_HASH):
    return save_benchmark_run(db, source_hash=source_hash, protocol={"horizon_months": 3}, official_model="seasonal_level",
                              environment={}, results=results)


@pytest.fixture(scope="module")
def card():
    response = TestClient(main.app).get("/api/model-benchmark")
    assert response.status_code == 200
    return response.json()["official"]


def test_card_describes_what_is_forecast_and_its_assumptions(card):
    assert card["engine"] == "v2"
    assert card["target"]["what"] == "Unidades faturadas por SKU e mês"
    assert [model["model"] for model in card["models"]] == ["seasonal_level", "seasonal_naive_12", "moving_average_3"]
    assert card["models"][0]["skus"] == card["data"]["skus"] == 50
    assert any("0.5 e 3 vezes" in item for item in card["assumptions"])  # limite lido da configuração
    assert card["horizon_months"] == 6
    assert card["limitations"] and card["confidence"]["rule"]


def test_card_error_matches_the_official_forecast(card):
    forecasts = main.pipeline()[5]
    expected = forecasts["backtest_abs_error_units"].sum() / forecasts["backtest_actual_units"].sum()
    assert card["evaluation"]["wape"] == pytest.approx(expected, abs=1e-3)
    assert card["evaluation"]["origins"] == ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    assert card["evaluation"]["peak_wape"] is not None and card["evaluation"]["bias"] is not None


def test_without_database_benchmark_reports_no_run(tmp_path):
    body = _client(tmp_path / "missing.db").get("/api/model-benchmark").json()
    assert body["benchmark"] == {"status": "no_run", "stale": None, "note": body["benchmark"]["note"], "run": None, "history": []}
    assert "benchmark_models.py" in body["benchmark"]["note"]
    assert not (tmp_path / "missing.db").exists()


def test_latest_run_is_ordered_and_compared_with_official(tmp_path):
    db = tmp_path / "benchmarks.db"
    _save(db, [_result("official", 0.08), _result("prophet", 0.36), _result("lightgbm", None, "unavailable"), _result("ets", 0.05)])
    benchmark = _client(db).get("/api/model-benchmark").json()["benchmark"]
    results = benchmark["run"]["results"]

    assert benchmark["status"] == "ok" and benchmark["stale"] is False and benchmark["note"] is None
    assert [result["model"] for result in results] == ["ets", "official", "prophet", "lightgbm"]
    assert [result["beats_official"] for result in results] == [True, None, False, None]
    assert [result["is_official"] for result in results] == [False, True, False, False]
    assert len(benchmark["history"]) == 1


def test_run_from_another_spreadsheet_is_flagged_stale(tmp_path):
    db = tmp_path / "benchmarks.db"
    _save(db, [_result("official", 0.08)], source_hash="0" * 64)
    benchmark = _client(db).get("/api/model-benchmark").json()["benchmark"]
    assert benchmark["stale"] is True
    assert "planilha mudou" in benchmark["note"]


def test_endpoint_never_changes_the_official_forecast():
    client = TestClient(main.app)
    before = client.get("/api/forecasts").json()
    client.get("/api/model-benchmark")
    assert client.get("/api/forecasts").json() == before
