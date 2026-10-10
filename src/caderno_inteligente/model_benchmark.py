"""Benchmark de modelos de previsão de demanda contra o motor oficial, no mesmo protocolo de avaliação.

Todos os modelos são medidos nas origens rolantes de `config/forecast_engine.json → evaluation` (as mesmas que dão o erro
e a confiança da previsão oficial): em cada origem, cada modelo treina só com os meses até ela e prevê os
`horizon_months` seguintes. O erro é o WAPE agrupado (Σ|erro| ÷ Σ real), também separado em meses de pico e normais.

As bibliotecas externas (statsforecast, Prophet, scikit-learn, LightGBM) são importadas só quando o modelo roda e ficam
em `requirements-ml.txt`, fora da API publicada. Sem a biblioteca, o modelo fica `unavailable`; erro na execução fica
`failed`. Quando um modelo não consegue prever um SKU numa origem, vale a previsão oficial naquele ponto e o ponto é
contado em `fallback_points`, para a comparação não esconder a lacuna.

Nada aqui altera a previsão oficial: o resultado é evidência gravada em `benchmark_store`.
"""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass, field
from importlib import metadata
from time import perf_counter
from typing import Any, Callable

import numpy as np
import pandas as pd

from .official_forecast import chain_forecast, evaluation_origins, ratio, window_errors
from .rolling_backtest import naive_last

# Previsão de um modelo para todos os SKUs numa origem: treino por SKU (até a origem) → previsão por SKU ou None.
Predictor = Callable[[dict[str, pd.Series], pd.PeriodIndex], dict[str, "list[float] | None"]]

ERROR_MESSAGE_LIMIT = 300
SEASON_LENGTH = 12


@dataclass(frozen=True)
class BenchmarkModel:
    code: str
    label: str
    library: str  # distribuição pip cuja versão é registrada; "caderno-inteligente" para os modelos internos
    description: str
    build: Callable[[dict[str, Any]], Predictor]  # recebe a configuração do motor; importa a biblioteca aqui
    params: dict[str, Any] = field(default_factory=dict)
    slow: bool = False


# --- Modelos internos -------------------------------------------------------------------------------------------------

def _official(config: dict[str, Any]) -> Predictor:
    def predict(train: dict[str, pd.Series], targets: pd.PeriodIndex) -> dict[str, list[float] | None]:
        return {sku: chain_forecast(history, targets, config)[1] for sku, history in train.items()}
    return predict


def _naive_last(_: dict[str, Any]) -> Predictor:
    def predict(train: dict[str, pd.Series], targets: pd.PeriodIndex) -> dict[str, list[float] | None]:
        return {sku: naive_last(history, targets) for sku, history in train.items()}
    return predict


# --- statsforecast ----------------------------------------------------------------------------------------------------

def _statsforecast(model_name: str) -> Callable[[dict[str, Any]], Predictor]:
    def build(_: dict[str, Any]) -> Predictor:
        from statsforecast import StatsForecast
        from statsforecast import models as sf_models

        model_class = getattr(sf_models, model_name)

        def predict(train: dict[str, pd.Series], targets: pd.PeriodIndex) -> dict[str, list[float] | None]:
            frame = pd.concat(
                [pd.DataFrame({"unique_id": sku, "ds": history.index.to_timestamp(), "y": history.to_numpy(dtype=float)})
                 for sku, history in train.items()],
                ignore_index=True,
            )
            engine = StatsForecast(models=[model_class(season_length=SEASON_LENGTH)], freq="MS", n_jobs=1)
            output = engine.forecast(df=frame, h=len(targets))
            output = output.reset_index() if "unique_id" not in output.columns else output
            column = next(name for name in output.columns if name not in ("unique_id", "ds"))
            return {str(sku): [float(value) for value in group.sort_values("ds")[column]] for sku, group in output.groupby("unique_id")}
        return predict
    return build


# --- Prophet ----------------------------------------------------------------------------------------------------------

def _prophet(_: dict[str, Any]) -> Predictor:
    from prophet import Prophet

    logging.getLogger("cmdstanpy").disabled = True
    logging.getLogger("prophet").setLevel(logging.ERROR)

    def predict(train: dict[str, pd.Series], targets: pd.PeriodIndex) -> dict[str, list[float] | None]:
        result: dict[str, list[float] | None] = {}
        future = pd.DataFrame({"ds": targets.to_timestamp()})
        for sku, history in train.items():
            model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False, seasonality_mode="multiplicative")
            model.fit(pd.DataFrame({"ds": history.index.to_timestamp(), "y": history.to_numpy(dtype=float)}))
            result[sku] = [float(value) for value in model.predict(future)["yhat"]]
        return result
    return predict


# --- Modelos globais (um único modelo treinado com todos os SKUs) -----------------------------------------------------

MISSING = -1.0  # marcador de feature indisponível (histórico curto); a árvore aprende a separá-lo


def _features(history: pd.Series, origin: pd.Period, step: int) -> tuple[list[float], float]:
    """Features na origem para prever `origin + step`, relativas ao nível atual (média dos 3 últimos meses)."""
    target = origin + step
    level = float(history.loc[origin - 2:origin].mean())
    year_ago = float(history.loc[origin - 14:origin - 12].mean()) if (origin - 14) in history.index else MISSING
    same_month = float(history[target - 12]) if (target - 12) in history.index else MISSING

    def relative(value: float) -> float:
        return value / level if level > 0 and value >= 0 else MISSING

    return [float(step), float(target.month), relative(same_month), relative(year_ago), relative(float(history[origin]))], level


def _global_model(factory: Callable[[], Any]) -> Predictor:
    def predict(train: dict[str, pd.Series], targets: pd.PeriodIndex) -> dict[str, list[float] | None]:
        horizon = len(targets)
        rows, labels = [], []
        for history in train.values():
            last = history.index.max()
            for origin in history.index[2:]:
                for step in range(1, horizon + 1):
                    if origin + step > last:
                        break
                    features, level = _features(history, origin, step)
                    if level > 0:
                        rows.append(features)
                        labels.append(float(history[origin + step]) / level)
        if not rows:
            return {sku: None for sku in train}
        model = factory().fit(np.array(rows, dtype=float), np.array(labels, dtype=float))
        result: dict[str, list[float] | None] = {}
        for sku, history in train.items():
            origin = history.index.max()
            built = [_features(history, origin, step) for step in range(1, horizon + 1)]
            if built[0][1] <= 0:
                result[sku] = None
                continue
            predicted = model.predict(np.array([features for features, _ in built], dtype=float))
            result[sku] = [float(value) * level for value, (_, level) in zip(predicted, built)]
        return result
    return predict


def _sklearn_hgb(_: dict[str, Any]) -> Predictor:
    from sklearn.ensemble import HistGradientBoostingRegressor

    return _global_model(lambda: HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, min_samples_leaf=20, random_state=0))


def _lightgbm(_: dict[str, Any]) -> Predictor:
    from lightgbm import LGBMRegressor

    return _global_model(lambda: LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20, verbose=-1, random_state=0))


MODELS: dict[str, BenchmarkModel] = {model.code: model for model in (
    BenchmarkModel("official", "Motor oficial (cadeia configurada)", "caderno-inteligente",
                   "A previsão oficial: mês do ano anterior ajustado pelo nível, com recuo para sazonal ingênuo e média móvel.", _official),
    BenchmarkModel("naive_last", "Repetir o último mês (baseline)", "caderno-inteligente",
                   "Referência mínima: repete o último mês observado.", _naive_last),
    BenchmarkModel("auto_ets", "AutoETS sazonal", "statsforecast",
                   "Suavização exponencial com erro, tendência e sazonalidade escolhidos automaticamente.", _statsforecast("AutoETS"),
                   {"season_length": SEASON_LENGTH}),
    BenchmarkModel("auto_arima", "AutoARIMA sazonal", "statsforecast",
                   "ARIMA sazonal com ordens escolhidas automaticamente.", _statsforecast("AutoARIMA"), {"season_length": SEASON_LENGTH}),
    BenchmarkModel("auto_theta", "AutoTheta sazonal", "statsforecast",
                   "Método Theta com dessazonalização automática.", _statsforecast("AutoTheta"), {"season_length": SEASON_LENGTH}),
    BenchmarkModel("sklearn_hgb", "Gradient boosting global (scikit-learn)", "scikit-learn",
                   "Um único modelo para todos os SKUs, com mês, nível recente e mesmo mês do ano anterior como variáveis.", _sklearn_hgb,
                   {"max_iter": 200, "learning_rate": 0.05, "min_samples_leaf": 20}),
    BenchmarkModel("lightgbm", "LightGBM global", "lightgbm",
                   "Um único modelo para todos os SKUs, com as mesmas variáveis do gradient boosting.", _lightgbm,
                   {"n_estimators": 300, "learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 20}),
    BenchmarkModel("prophet", "Prophet", "prophet",
                   "Um modelo por SKU com tendência e sazonalidade anual multiplicativa.", _prophet,
                   {"yearly_seasonality": True, "seasonality_mode": "multiplicative"}, slow=True),
)}


def _library_version(library: str) -> str | None:
    try:
        return metadata.version(library)
    except metadata.PackageNotFoundError:
        return None


def protocol(config: dict[str, Any], origins: list[pd.Period]) -> dict[str, Any]:
    evaluation = config["evaluation"]
    return {
        "origins": [str(origin) for origin in origins], "horizon_months": evaluation["horizon_months"],
        "peak_months": list(evaluation["peak_months"]), "metric": "WAPE agrupado = Σ|previsto − real| ÷ Σ real",
        "fallback": "ponto sem previsão do modelo usa a previsão oficial e é contado em fallback_points",
    }


def environment() -> dict[str, Any]:
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}


def _result(model: BenchmarkModel, status: str, started: float, **values: Any) -> dict[str, Any]:
    return {
        "model": model.code, "label": model.label, "library": model.library, "library_version": _library_version(model.library),
        "params": model.params, "status": status, "error_message": None,
        "wape": None, "peak_wape": None, "normal_wape": None, "bias": None,
        "evaluated_points": 0, "fallback_points": 0, "duration_seconds": round(perf_counter() - started, 2),
        **values,
    }


def evaluate_model(model: BenchmarkModel, series_map: dict[str, pd.Series], config: dict[str, Any],
                   origins: list[pd.Period]) -> dict[str, Any]:
    """Mede um modelo em todas as origens; nunca levanta exceção (o status registra o problema)."""
    started = perf_counter()
    try:
        predict = model.build(config)
    except ImportError as error:
        return _result(model, "unavailable", started, error_message=f"Biblioteca ausente: {error.name or error}")
    horizon = config["evaluation"]["horizon_months"]
    official = _official(config)
    windows, fallback_points = [], 0
    try:
        for origin in origins:
            targets = pd.period_range(origin + 1, periods=horizon, freq="M")
            train = {sku: series[series.index <= origin] for sku, series in series_map.items()}
            predicted = predict(train, targets)
            missing = [sku for sku in train if not predicted.get(sku) or len(predicted[sku]) != horizon]
            if missing:
                fallback = official({sku: train[sku] for sku in missing}, targets)
                predicted = {**predicted, **fallback}
                fallback_points += horizon * len(missing)
            for sku, series in series_map.items():
                values = predicted.get(sku)
                if values is None:  # nem o oficial previu: o ponto fica fora da medida
                    continue
                windows.append({
                    "months": [period.month for period in targets],
                    "actual": [float(value) for value in series.reindex(targets).tolist()],
                    "predicted": [max(0.0, float(value)) for value in values],
                })
    except Exception as error:  # noqa: BLE001 - a rodada registra a falha e segue para o próximo modelo
        message = f"{type(error).__name__}: {error}"[:ERROR_MESSAGE_LIMIT]
        return _result(model, "failed", started, error_message=message)
    errors = window_errors(windows, config["evaluation"]["peak_months"])
    return _result(
        model, "ok", started,
        wape=ratio(errors["all_abs"], errors["all_actual"]),
        peak_wape=ratio(errors["peak_abs"], errors["peak_actual"]),
        normal_wape=ratio(errors["normal_abs"], errors["normal_actual"]),
        bias=ratio(errors["all_signed"], errors["all_actual"]),
        evaluated_points=sum(len(window["months"]) for window in windows),
        fallback_points=fallback_points,
    )


def benchmark_origins(series_map: dict[str, pd.Series], config: dict[str, Any]) -> list[pd.Period]:
    """Origens do protocolo avaliáveis na série mais longa (os SKUs da base compartilham o calendário)."""
    if not series_map:
        return []
    longest = max(series_map.values(), key=len)
    return evaluation_origins(longest, config)


def run_benchmark(series_map: dict[str, pd.Series], config: dict[str, Any], models: list[BenchmarkModel],
                  on_result: Callable[[dict[str, Any]], None] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Protocolo e um resultado por modelo, na ordem pedida."""
    origins = benchmark_origins(series_map, config)
    results = []
    for model in models:
        result = evaluate_model(model, series_map, config, origins)
        results.append(result)
        if on_result:
            on_result(result)
    return protocol(config, origins), results
