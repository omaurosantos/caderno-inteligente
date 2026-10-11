from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from caderno_inteligente import forecast_candidates as fc
from caderno_inteligente.forecasting import MODEL_LABELS, _MODELS, _moving_average, _seasonal_naive, build_demand_forecasts
from caderno_inteligente.ingestion import load_workbook
from caderno_inteligente.transformations import normalise_dataset

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source" / "Base de Dados - Caderno Inteligente.xlsm"
SNAPSHOT = ROOT / "docs" / "etapa-14-0" / "snapshot-previsao-v1.json"


def _series(values: list[float], start: str = "2024-01") -> pd.Series:
    return pd.Series([float(value) for value in values], index=pd.period_range(start, periods=len(values), freq="M"))


def _targets(history: pd.Series, horizon: int = 3) -> pd.PeriodIndex:
    return pd.period_range(history.index[-1] + 1, periods=horizon, freq="M")


def _run(code: str, values: list[float]) -> list[float] | None:
    history = _series(values)
    return fc.run_candidate(code, history, _targets(history))


# --- SES ---------------------------------------------------------------------------------------------------------

def test_ses_constant_series_repeats_the_level():
    assert _run("ses", [10] * 8) == [10.0, 10.0, 10.0]


def test_ses_ties_pick_the_smallest_alpha():
    # Só o último ponto erra (por 10, em qualquer alpha): o SSE empata e vale alpha = 0,1 → nível 10 + 0,1 × 10.
    assert _run("ses", [10, 10, 10, 10, 10, 20]) == pytest.approx([11.0, 11.0, 11.0])


def test_ses_step_series_prefers_a_fast_alpha():
    # alpha = 0,9 reage ao degrau: nível 10 → 19 → 19,9 → 19,99.
    assert _run("ses", [10, 10, 10, 20, 20, 20]) == pytest.approx([19.99] * 3)


# --- Holt amortecido ---------------------------------------------------------------------------------------------

def test_holt_constant_series_has_no_trend():
    assert _run("holt_damped", [5] * 9) == pytest.approx([5.0, 5.0, 5.0])


def test_holt_growing_series_continues_up_but_damped():
    values = [10 + 2 * month for month in range(12)]
    predictions = _run("holt_damped", values)

    assert predictions[0] > values[-1]
    assert predictions[0] < predictions[1] < predictions[2]
    undamped = [values[-1] + 2 * step for step in (1, 2, 3)]
    assert all(predicted <= straight + 1e-9 for predicted, straight in zip(predictions, undamped))
    # O acréscimo por mês encolhe: a tendência perde força.
    assert predictions[2] - predictions[1] < predictions[1] - predictions[0]


def test_holt_never_returns_negative_for_a_collapsing_series():
    predictions = _run("holt_damped", [90, 80, 70, 60, 50, 40, 30, 20, 10, 5, 1])
    assert all(value >= 0 for value in predictions)


# --- Mês do ano anterior ajustado pelo nível --------------------------------------------------------------------

YEAR = [40, 40, 40, 44, 48, 60, 70, 80, 90, 100, 110, 120]


def test_seasonal_level_scales_last_year_by_level_growth():
    # nível agora = (20+40+60)/3 = 40; nível há um ano = (40+40+40)/3 = 40; razões 44/40, 48/40 e 60/40.
    assert _run("seasonal_level", YEAR + [20, 40, 60]) == pytest.approx([44.0, 48.0, 60.0])


def test_seasonal_level_caps_the_ratio_at_two():
    series = [20, 20, 20, 40, 50, 60, 70, 80, 90, 100, 110, 120, 20, 40, 60]
    # nível agora 40; nível há um ano 20; razões 2, 2,5 e 3 limitadas a 2 → 80.
    assert _run("seasonal_level", series) == pytest.approx([80.0, 80.0, 80.0])


def test_seasonal_level_floors_the_ratio_at_half():
    series = [100, 100, 100, 10, 10, 10, 70, 80, 90, 100, 110, 120, 20, 40, 60]
    # nível agora 40; nível há um ano 100; razão 0,1 limitada a 0,5 → 20.
    assert _run("seasonal_level", series) == pytest.approx([20.0, 20.0, 20.0])


def test_seasonal_level_needs_15_months_and_a_positive_base():
    assert _run("seasonal_level", YEAR + [20, 40]) is None
    assert _run("seasonal_level", [0, 0, 0] + YEAR[3:] + [20, 40, 60]) is None


# --- Combinação -------------------------------------------------------------------------------------------------

def test_combo_averages_moving_average_and_seasonal_naive():
    values = [10 + month for month in range(12)]  # 10..21
    history = _series(values)
    targets = _targets(history)

    predictions = fc.run_candidate("combo_ma_sn", history, targets)

    # Média móvel recursiva: 20; 20,3333; 20,4444. Sazonal ingênuo: 10, 11, 12.
    assert predictions == pytest.approx([15.0, (20 + 1 / 3 + 11) / 2, (20 + 4 / 9 + 12) / 2])
    expected = [(a + b) / 2 for a, b in zip(_moving_average(history, targets), _seasonal_naive(history, targets))]
    assert predictions == pytest.approx(expected)


def test_combo_is_none_without_12_months():
    assert _run("combo_ma_sn", [10] * 11) is None


# --- Registro e regras comuns -----------------------------------------------------------------------------------

def test_registry_reuses_the_current_models_without_changing_them():
    assert fc.CANDIDATES["moving_average_3"].function is _MODELS["moving_average_3"]
    assert fc.CANDIDATES["seasonal_naive_12"].function is _MODELS["seasonal_naive_12"]
    assert fc.CANDIDATE_LABELS["moving_average_3"] == MODEL_LABELS["moving_average_3"]
    assert set(MODEL_LABELS) == {"moving_average_3", "seasonal_naive_12"}  # forecasting.py segue intacto


def test_simplicity_order_is_stable_and_complete():
    assert fc.SIMPLICITY_ORDER == ("moving_average_3", "seasonal_naive_12", "ses", "combo_ma_sn", "seasonal_level", "holt_damped")
    assert set(fc.SIMPLICITY_ORDER) == set(fc.CANDIDATES)


def test_minimum_history_is_enforced_without_inventing_values():
    for code, candidate in fc.CANDIDATES.items():
        short = _series([10 + month for month in range(candidate.min_history - 1)]) if candidate.min_history > 1 else _series([])
        assert fc.run_candidate(code, short, _targets(_series([1] * 6))) is None, code


def test_applicable_candidates_follow_history_and_config():
    assert fc.applicable_candidates(5) == ["moving_average_3"]
    assert fc.applicable_candidates(6) == ["moving_average_3", "ses"]
    assert fc.applicable_candidates(9) == ["moving_average_3", "ses", "holt_damped"]
    assert fc.applicable_candidates(12) == ["moving_average_3", "seasonal_naive_12", "ses", "combo_ma_sn", "holt_damped"]
    assert fc.applicable_candidates(24) == list(fc.SIMPLICITY_ORDER)
    assert fc.applicable_candidates(24, ["ses", "moving_average_3"]) == ["moving_average_3", "ses"]


def test_candidates_are_deterministic_nonnegative_and_do_not_mutate_input():
    rng = np.random.default_rng(7)
    values = list(np.abs(rng.normal(100, 30, 24)).round(1))
    history = _series(values)
    before = history.copy()
    targets = _targets(history)

    for code in fc.SIMPLICITY_ORDER:
        first = fc.run_candidate(code, history, targets)
        second = fc.run_candidate(code, history, targets)
        assert first == second, code
        assert len(first) == 3 and all(np.isfinite(value) and value >= 0 for value in first), code
    pd.testing.assert_series_equal(history, before)


def test_seasonal_codes_are_the_candidates_that_embed_last_years_pattern():
    assert fc.SEASONAL_CODES == {"seasonal_naive_12", "combo_ma_sn", "seasonal_level"}
    assert fc.SEASONAL_CODES <= set(fc.CANDIDATES)


# --- Base real: nada oficial mudou ------------------------------------------------------------------------------

def test_every_candidate_forecasts_every_real_sku():
    sales = normalise_dataset(load_workbook(SOURCE))["Vendas_24m"]
    for sku in sorted(sales["SKU"].unique())[:50]:
        subset = sales.loc[sales["SKU"] == sku]
        history = subset.assign(month=pd.to_datetime(subset["Mês"]).dt.to_period("M")).groupby("month")["Quantidade faturada"].sum().astype(float).sort_index()
        targets = _targets(history)
        for code in fc.applicable_candidates(len(history)):
            values = fc.run_candidate(code, history, targets)
            assert values is not None and len(values) == 3 and all(np.isfinite(v) and v >= 0 for v in values), (sku, code)


def test_v1_engine_is_identical_to_the_14_0_snapshot():
    """O motor v1 continua reproduzível; desde a Etapa 15.1 o oficial é o v2 (snapshot em docs/etapa-15)."""
    sales = normalise_dataset(load_workbook(SOURCE))["Vendas_24m"]
    current = json.loads(build_demand_forecasts(sales).sort_values("sku").to_json(orient="records", force_ascii=False))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["forecasts"]

    assert current == snapshot


def test_seasonal_level_description_follows_the_informed_ratio_bounds():
    assert "0,5–3,0" in fc.describe_seasonal_level((0.5, 3.0))
    assert "0,5–2,0" in fc.describe_seasonal_level((0.5, 2.0))
    assert "0,5–2,0" in fc.CANDIDATES["seasonal_level"].description  # padrão do candidato, não da configuração
