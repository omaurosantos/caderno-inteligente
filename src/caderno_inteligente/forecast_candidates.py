"""Modelos candidatos de previsão mensal (Etapa 14.1), todos explicáveis em uma frase e sem dependência além de pandas.

Cada modelo recebe a série mensal contínua (`pd.Series` com `PeriodIndex`) e os meses-alvo e devolve uma lista de
previsões não negativas, ou `None` quando faltam dados. Nunca se inventa zero. Os parâmetros são estimados só com a série
recebida (o treino) e em grades fixas, então o resultado é determinístico e não enxerga o futuro.

Este módulo não altera `forecasting.py`: os dois modelos atuais são reaproveitados de lá, e a escolha oficial continua a
mesma até a decisão de promoção da Etapa 14.5.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable

import pandas as pd

from .forecasting import MODEL_LABELS, _moving_average, _seasonal_naive

Model = Callable[[pd.Series, pd.PeriodIndex], "list[float] | None"]

SES_ALPHAS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
HOLT_ALPHAS = (0.1, 0.3, 0.5, 0.7, 0.9)
HOLT_BETAS = (0.1, 0.3, 0.5)
HOLT_PHIS = (0.8, 0.9, 0.98)
SEASONAL_RATIO_BOUNDS = (0.5, 2.0)
LEVEL_MONTHS = 3
SEASONAL_LEVEL_MIN_HISTORY = 15  # nível atual (3 meses) + nível de um ano atrás (3 meses) + o mês de origem


def _values(history: pd.Series) -> list[float]:
    return [float(value) for value in history.tolist()]


def _ses_sse(values: list[float], alpha: float) -> tuple[float, float]:
    """Soma dos erros ao quadrado de 1 passo à frente e nível final."""
    level, sse = values[0], 0.0
    for observed in values[1:]:
        error = observed - level
        sse += error * error
        level += alpha * error
    return sse, level


def _ses(history: pd.Series, targets: pd.PeriodIndex) -> list[float] | None:
    """Nível que dá mais peso ao recente; o peso (alpha) é o que erra menos 1 mês à frente no próprio treino."""
    values = _values(history)
    if len(values) < 2:
        return None
    _, best_level = min((_ses_sse(values, alpha) for alpha in SES_ALPHAS), key=lambda item: item[0])
    return [max(0.0, best_level)] * len(targets)


def _holt_state(values: list[float], alpha: float, beta: float, phi: float) -> tuple[float, float, float]:
    """Nível + tendência amortecida: soma dos erros de 1 passo, nível e tendência finais."""
    level = values[0]
    trend = (values[3] - values[0]) / 3 if len(values) >= 4 else values[1] - values[0]
    sse = 0.0
    for observed in values[1:]:
        expected = level + phi * trend
        error = observed - expected
        sse += error * error
        new_level = alpha * observed + (1 - alpha) * expected
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return sse, level, trend


def _holt_damped(history: pd.Series, targets: pd.PeriodIndex) -> list[float] | None:
    """Nível + tendência que se amortece com o tempo, para não extrapolar crescimento ou queda indefinidamente."""
    values = _values(history)
    if len(values) < 4:
        return None
    best = None
    for alpha, beta, phi in product(HOLT_ALPHAS, HOLT_BETAS, HOLT_PHIS):
        sse, level, trend = _holt_state(values, alpha, beta, phi)
        if best is None or sse < best[0]:
            best = (sse, level, trend, phi)
    _, level, trend, phi = best
    predictions, damping = [], 0.0
    for step in range(1, len(targets) + 1):
        damping += phi**step
        predictions.append(max(0.0, level + damping * trend))
    return predictions


def describe_seasonal_level(ratio_bounds: tuple[float, float]) -> str:
    """Descrição do candidato `seasonal_level` com o limite da razão sazonal efetivo (não um texto fixo)."""
    low, high = (f"{value:.1f}".replace(".", ",") for value in ratio_bounds)
    return f"Mesmo mês do ano anterior, ajustado pelo crescimento do nível; razão limitada a {low}–{high}."


def _seasonal_level(history: pd.Series, targets: pd.PeriodIndex) -> list[float] | None:
    """Mesmo mês do ano anterior, ajustado pelo crescimento do nível (média de 3 meses agora ÷ há um ano).

    A razão sazonal de cada mês fica limitada pelos limites informados (padrão [0,5; 2,0]) para um mês atípico do ano passado não dominar a previsão.
    """
    return seasonal_level(history, targets, SEASONAL_RATIO_BOUNDS)


def seasonal_level(history: pd.Series, targets: pd.PeriodIndex, ratio_bounds: tuple[float, float]) -> list[float] | None:
    """`seasonal_level` com o limite da razão sazonal informado (o motor oficial v2 lê o limite da configuração)."""
    values = _values(history)
    if len(values) < SEASONAL_LEVEL_MIN_HISTORY:
        return None
    lookup = {period: float(value) for period, value in history.items()}
    current = sum(values[-LEVEL_MONTHS:]) / LEVEL_MONTHS
    year_ago = sum(values[-LEVEL_MONTHS - 12 : -12]) / LEVEL_MONTHS
    if year_ago <= 0:
        return None
    low, high = ratio_bounds
    predictions: list[float] = []
    for target in targets:
        source = target - 12
        if source not in lookup:
            return None
        ratio = min(high, max(low, lookup[source] / year_ago))
        predictions.append(max(0.0, current * ratio))
    return predictions


def _combo_ma_sn(history: pd.Series, targets: pd.PeriodIndex) -> list[float] | None:
    """Média simples da média móvel de 3 meses com o sazonal ingênuo de 12 meses."""
    moving = _moving_average(history, targets)
    seasonal = _seasonal_naive(history, targets)
    if moving is None or seasonal is None:
        return None
    return [(first + second) / 2 for first, second in zip(moving, seasonal)]


@dataclass(frozen=True)
class Candidate:
    code: str
    label: str
    function: Model
    min_history: int
    complexity: int  # 1 = mais simples; desempata e alimenta a regra de parcimônia
    description: str


_CANDIDATES = (
    Candidate("moving_average_3", MODEL_LABELS["moving_average_3"], _moving_average, 3, 1, "Média dos últimos 3 meses."),
    Candidate("seasonal_naive_12", MODEL_LABELS["seasonal_naive_12"], _seasonal_naive, 12, 2, "Repete o mesmo mês do ano anterior."),
    Candidate("ses", "Suavização exponencial simples", _ses, 6, 3, "Nível que dá mais peso aos meses recentes; o peso vem do erro do próprio treino."),
    Candidate("combo_ma_sn", "Média móvel + sazonal ingênuo", _combo_ma_sn, 12, 4, "Média simples da média móvel de 3 meses com o sazonal ingênuo de 12 meses."),
    Candidate("seasonal_level", "Mês do ano anterior ajustado pelo nível", _seasonal_level, SEASONAL_LEVEL_MIN_HISTORY, 5, describe_seasonal_level(SEASONAL_RATIO_BOUNDS)),
    Candidate("holt_damped", "Nível e tendência amortecida (Holt)", _holt_damped, 9, 6, "Nível mais tendência que perde força com o tempo."),
)

CANDIDATES: dict[str, Candidate] = {candidate.code: candidate for candidate in _CANDIDATES}
CANDIDATE_LABELS: dict[str, str] = {code: candidate.label for code, candidate in CANDIDATES.items()}
SIMPLICITY_ORDER: tuple[str, ...] = tuple(candidate.code for candidate in sorted(_CANDIDATES, key=lambda item: item.complexity))
# Candidatos que já repetem o padrão sazonal do ano anterior; Etapa 14.5 usa isto para não contar evento em dobro.
SEASONAL_CODES = frozenset({"seasonal_naive_12", "combo_ma_sn", "seasonal_level"})


def run_candidate(code: str, history: pd.Series, targets: pd.PeriodIndex) -> list[float] | None:
    """Previsão do candidato ou `None` se a série for curta demais para ele."""
    candidate = CANDIDATES[code]
    if len(history) < candidate.min_history:
        return None
    return candidate.function(history, targets)


def applicable_candidates(history_months: int, enabled: tuple[str, ...] | list[str] | None = None) -> list[str]:
    """Candidatos habilitados que o histórico informado comporta, do mais simples ao mais complexo."""
    allowed = set(CANDIDATES) if enabled is None else set(enabled)
    return [code for code in SIMPLICITY_ORDER if code in allowed and history_months >= CANDIDATES[code].min_history]
