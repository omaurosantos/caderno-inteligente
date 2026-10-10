from pathlib import Path

import pandas as pd
import pytest

from caderno_inteligente.forecast_engine_config import load_engine_config
from caderno_inteligente.ingestion import load_workbook
from caderno_inteligente.model_benchmark import MODELS, BenchmarkModel, benchmark_origins, evaluate_model, run_benchmark
from caderno_inteligente.official_forecast import build_official_forecasts
from caderno_inteligente.rolling_backtest import series_by_sku
from caderno_inteligente.transformations import normalise_dataset

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/source/Base de Dados - Caderno Inteligente.xlsm"
CONFIG = load_engine_config(ROOT / "config/forecast_engine.json")


def _series(level: float, months: int = 24) -> pd.Series:
    index = pd.period_range("2024-09", periods=months, freq="M")
    return pd.Series([level * (1.5 if period.month in (11, 1) else 1.0) for period in index], index=index, dtype=float)


SERIES = {"A": _series(100.0), "B": _series(40.0)}


def _constant(value):
    def build(_):
        return lambda train, targets: {sku: [value] * len(targets) for sku in train}
    return build


def test_origins_follow_engine_protocol():
    origins = benchmark_origins(SERIES, CONFIG)
    assert [str(origin) for origin in origins] == [str(p) for p in pd.period_range(CONFIG["evaluation"]["first_origin"], CONFIG["evaluation"]["last_origin"], freq="M")]


def test_perfect_model_has_zero_error_and_wrong_model_has_bias():
    origins = benchmark_origins(SERIES, CONFIG)
    perfect = BenchmarkModel("perfect", "Perfeito", "caderno-inteligente", "",
                             lambda _: (lambda train, targets: {sku: SERIES[sku].reindex(targets).tolist() for sku in train}))
    result = evaluate_model(perfect, SERIES, CONFIG, origins)
    assert result["status"] == "ok"
    assert result["wape"] == 0
    assert result["evaluated_points"] == len(origins) * CONFIG["evaluation"]["horizon_months"] * len(SERIES)

    zero = evaluate_model(BenchmarkModel("zero", "Zero", "caderno-inteligente", "", _constant(0.0)), SERIES, CONFIG, origins)
    assert zero["wape"] == pytest.approx(1.0)
    assert zero["bias"] == pytest.approx(-1.0)
    assert zero["peak_wape"] == pytest.approx(1.0)


def test_missing_library_is_unavailable_not_error():
    def build(_):
        raise ImportError("no module", name="prophet")
    result = evaluate_model(BenchmarkModel("x", "X", "prophet-not-installed", "", build), SERIES, CONFIG, benchmark_origins(SERIES, CONFIG))
    assert result["status"] == "unavailable"
    assert result["wape"] is None  # sem resultado não vira zero
    assert "prophet" in result["error_message"]
    assert result["library_version"] is None


def test_failure_during_prediction_is_recorded():
    def build(_):
        def predict(train, targets):
            raise RuntimeError("explodiu")
        return predict
    result = evaluate_model(BenchmarkModel("x", "X", "caderno-inteligente", "", build), SERIES, CONFIG, benchmark_origins(SERIES, CONFIG))
    assert result["status"] == "failed"
    assert result["error_message"] == "RuntimeError: explodiu"
    assert result["wape"] is None


def test_missing_sku_prediction_falls_back_to_official_and_is_counted():
    def build(_):
        return lambda train, targets: {"A": [100.0] * len(targets)}  # nunca prevê B
    origins = benchmark_origins(SERIES, CONFIG)
    result = evaluate_model(BenchmarkModel("x", "X", "caderno-inteligente", "", build), SERIES, CONFIG, origins)
    horizon = CONFIG["evaluation"]["horizon_months"]
    assert result["status"] == "ok"
    assert result["fallback_points"] == len(origins) * horizon
    assert result["evaluated_points"] == len(origins) * horizon * 2


def test_run_benchmark_keeps_order_and_reports_each_result():
    seen = []
    protocol, results = run_benchmark(SERIES, CONFIG, [MODELS["naive_last"], MODELS["official"]], on_result=seen.append)
    assert [result["model"] for result in results] == ["naive_last", "official"] == [result["model"] for result in seen]
    assert protocol["horizon_months"] == CONFIG["evaluation"]["horizon_months"]
    assert protocol["peak_months"] == CONFIG["evaluation"]["peak_months"]


def test_official_model_matches_official_forecast_error_on_real_data():
    sales = normalise_dataset(load_workbook(SOURCE))["Vendas_24m"]
    series_map = series_by_sku(sales)
    result = evaluate_model(MODELS["official"], series_map, CONFIG, benchmark_origins(series_map, CONFIG))
    official = build_official_forecasts(sales, CONFIG, series_map)
    expected = official["backtest_abs_error_units"].sum() / official["backtest_actual_units"].sum()
    assert result["fallback_points"] == 0
    assert result["wape"] == pytest.approx(expected, abs=1e-3)  # o benchmark mede o oficial igual à previsão oficial


def test_script_records_a_run_and_rejects_unknown_models(tmp_path, capsys):
    import importlib.util

    from caderno_inteligente.benchmark_store import latest_benchmark_run

    spec = importlib.util.spec_from_file_location("benchmark_models", ROOT / "scripts/benchmark_models.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    db = tmp_path / "benchmarks.db"

    assert script.main(["--models", "official,naive_last", "--db", str(db), "--note", "teste"]) == 0
    run = latest_benchmark_run(db)
    assert [result["model"] for result in run["results"]] == ["official", "naive_last"]
    assert run["official_model"] == CONFIG["official"]["model_chain"][0]
    assert run["note"] == "teste"
    assert len(run["source_hash"]) == 64

    with pytest.raises(SystemExit):
        script.main(["--models", "nao_existe", "--db", str(db)])
