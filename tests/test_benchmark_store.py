import pytest

from caderno_inteligente.benchmark_store import get_benchmark_run, latest_benchmark_run, list_benchmark_runs, save_benchmark_run


def _result(model, wape, status="ok"):
    return {
        "model": model, "label": model.title(), "library": "test", "library_version": "1.0", "params": {"alpha": 0.5},
        "status": status, "error_message": None if status == "ok" else "sem biblioteca",
        "wape": wape, "peak_wape": wape, "normal_wape": wape, "bias": 0.01,
        "evaluated_points": 10, "fallback_points": 0, "duration_seconds": 0.2,
    }


def _save(path, results, source_hash="abc"):
    return save_benchmark_run(path, source_hash=source_hash, protocol={"horizon_months": 3}, official_model="seasonal_level",
                              environment={"python": "3.12"}, results=results, note="teste")


def test_missing_database_is_empty_not_error(tmp_path):
    path = tmp_path / "benchmarks.db"
    assert latest_benchmark_run(path) is None
    assert list_benchmark_runs(path) == []
    assert get_benchmark_run(path, 1) is None
    assert not path.exists()  # leitura não cria o banco


def test_round_trip_keeps_results_and_json_fields(tmp_path):
    path = tmp_path / "benchmarks.db"
    run_id = _save(path, [_result("official", 0.08), _result("prophet", None, status="unavailable")])

    run = get_benchmark_run(path, run_id)
    assert run["source_hash"] == "abc"
    assert run["protocol"] == {"horizon_months": 3}
    assert run["environment"] == {"python": "3.12"}
    assert [result["model"] for result in run["results"]] == ["official", "prophet"]
    assert run["results"][0]["params"] == {"alpha": 0.5}
    assert run["results"][1]["wape"] is None  # ausente continua nulo


def test_latest_and_history_order(tmp_path):
    path = tmp_path / "benchmarks.db"
    _save(path, [_result("official", 0.08)], source_hash="old")
    second = _save(path, [_result("official", 0.08), _result("ets", 0.16), _result("bad", None, status="failed")], source_hash="new")

    assert latest_benchmark_run(path)["id"] == second
    history = list_benchmark_runs(path)
    assert [run["id"] for run in history] == [second, second - 1]
    assert history[0]["models"] == 3
    assert history[0]["best_model"] == "official"
    assert history[0]["best_wape"] == pytest.approx(0.08)


def test_invalid_status_is_rejected_before_writing(tmp_path):
    path = tmp_path / "benchmarks.db"
    with pytest.raises(ValueError):
        _save(path, [_result("official", 0.08, status="done")])
    assert list_benchmark_runs(path) == []
