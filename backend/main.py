from __future__ import annotations

import logging
import math

import pandas as pd
import os
import sys
from pathlib import Path
from threading import Lock
from time import monotonic, perf_counter

from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from caderno_inteligente.cases import STATUSES  # noqa: E402
from caderno_inteligente.feedback import (  # noqa: E402
    ACTIONS,
    PARTNER_DATA_EFFECTS,
)
from caderno_inteligente.forecast_engine_config import load_engine_config  # noqa: E402
from caderno_inteligente.official_forecast import build_official_forecasts  # noqa: E402
from caderno_inteligente.action_labels import label_commercial_row, label_operational, label_partner, load_action_settings  # noqa: E402
from caderno_inteligente.events import build_event_analysis, load_event_settings  # noqa: E402
from caderno_inteligente.revenue import build_revenue_forecasts  # noqa: E402
from caderno_inteligente.indicators import build_sku_indicators, registered_demand_warning  # noqa: E402
from caderno_inteligente.supply_plan import attach_partner_buildup, build_supply_plans, load_supply_settings  # noqa: E402
from caderno_inteligente.partner_insights import build_partner_insights, load_commercial_thresholds  # noqa: E402
from caderno_inteligente.direct_channels import build_direct_channels, load_direct_channel_settings  # noqa: E402
from caderno_inteligente.visibility import billing_uniform_split_warning, build_visibility_journey, sellin_billing_divergence_warning  # noqa: E402
from caderno_inteligente.action_labels import build_lever_context, decisions_today, label_channel_row  # noqa: E402
from caderno_inteligente.allocation import build_allocation, load_allocation_settings  # noqa: E402
from caderno_inteligente.impact import abc_registry_divergence_warning, load_impact_settings, measured_abc, urgency_tier  # noqa: E402
from caderno_inteligente.capacity_plan import build_capacity_plan, load_capacity_extension  # noqa: E402
from caderno_inteligente.production_plan import build_production_plan  # noqa: E402
from caderno_inteligente.projected_stock import build_projected_stock  # noqa: E402
from caderno_inteligente.ingestion import load_workbook  # noqa: E402
from caderno_inteligente.auth import UserStore  # noqa: E402
from caderno_inteligente.dataset_store import Database, DatasetStore  # noqa: E402
from caderno_inteligente.prioritization import load_weights, prioritize  # noqa: E402
from caderno_inteligente.persistence import build_persistence  # noqa: E402
from caderno_inteligente.recommendations import build_operational_recommendation  # noqa: E402
from caderno_inteligente.rules import evaluate_rules, load_rule_thresholds  # noqa: E402
from caderno_inteligente.transformations import normalise_dataset  # noqa: E402
from caderno_inteligente.validation import validate_dataset  # noqa: E402

SOURCE = ROOT / "data/source/Base de Dados - Caderno Inteligente.xlsm"
FEEDBACK_DB = ROOT / "runtime/feedback.db"
CASES_DB = ROOT / "runtime/cases.db"
RUNS_DB = ROOT / "runtime/runs.db"
DATASET_DB = ROOT / "runtime/dataset.db"
BENCHMARK_DB = ROOT / "runtime/benchmarks.db"
WEIGHTS_FILE = ROOT / "config/prioritization_weights.json"
THRESHOLDS_FILE = ROOT / "config/rule_thresholds.json"
EVENT_FACTORS_FILE = ROOT / "config/event_factors.json"
CHALLENGE_ACTIONS_FILE = ROOT / "config/challenge_actions.json"
ENGINE_CONFIG_FILE = ROOT / "config/forecast_engine.json"
SUPPLY_PLAN_FILE = ROOT / "config/supply_plan.json"
# Etapa 16: configurações novas entram na assinatura do cache desde já (lidas pelas tarefas da Onda 2).
ALLOCATION_FILE = ROOT / "config/allocation.json"
IMPACT_FILE = ROOT / "config/prioritization_impact.json"
CAPACITY_EXTENSION_FILE = ROOT / "config/capacity_extension.json"
ETAPA16_CONFIG_FILES = (ALLOCATION_FILE, IMPACT_FILE, CAPACITY_EXTENSION_FILE)
COMMERCIAL_THRESHOLDS_FILE = ROOT / "config/commercial_thresholds.json"
DIRECT_CHANNEL_FILE = ROOT / "config/direct_channel_thresholds.json"
PARTNER_PROJECTION_FILE = ROOT / "config/partner_projection.json"
# Camadas aditivas: arquivo ausente entra na assinatura como None (a camada cai sozinha, a API não).
OPTIONAL_CONFIG_FILES = (*ETAPA16_CONFIG_FILES, COMMERCIAL_THRESHOLDS_FILE, DIRECT_CHANNEL_FILE, PARTNER_PROJECTION_FILE)
# Fallback da capacidade quando config/capacity_extension.json está ausente ou inválido: só o calendário da base.
CAPACITY_EXTENSION_OFF = {"enabled": False, "method": "media_compromissos_8_semanas", "scenario": "central", "lookback_weeks": 8,
                          "conservative_method": "minimo_disponivel_observado"}

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("caderno_inteligente.api")

from backend.registry import auth_required, auth_secret, create_registry_router  # noqa: E402
from backend.security import (  # noqa: E402
    MAX_ANALYSIS_MINUTES,
    TEXT_LIMITS,
    clean_text,
    install_error_handling,
    install_log_redaction,
    load_settings,
    public_message,
    write_guard,
)

install_log_redaction()
SETTINGS = load_settings()


def settings():
    """Read at call time so tests and future reloads can replace SETTINGS."""
    return SETTINGS


require_write_access = Depends(write_guard(settings))


def _persistence():
    """Select PostgreSQL in production and retain SQLite for local development."""
    return build_persistence(
        database_url=os.getenv("DATABASE_URL"),
        cases_db=CASES_DB,
        feedback_db=FEEDBACK_DB,
        runs_db=RUNS_DB,
    )


DATA_SOURCES = ("planilha", "banco")


def data_source() -> str:
    """DATA_SOURCE escolhe de onde vêm as abas: planilha (padrão) ou banco (fase 3). Valor desconhecido mantém a planilha."""
    value = (os.getenv("DATA_SOURCE") or "planilha").strip().lower()
    return value if value in DATA_SOURCES else "planilha"


_database_cache: tuple[tuple, Database] | None = None


def _database() -> Database:
    """Mesmo banco da persistência: PostgreSQL com DATABASE_URL; sem ela, SQLite em runtime/dataset.db."""
    global _database_cache
    url = os.getenv("DATABASE_URL")
    key = (url, None if url else DATASET_DB)
    if _database_cache is None or _database_cache[0] != key:
        _database_cache = (key, Database(database_url=url) if url else Database(sqlite_path=DATASET_DB))
    return _database_cache[1]


def dataset_store() -> DatasetStore:
    return DatasetStore(_database())


def user_store() -> UserStore:
    return UserStore(_database())


app = FastAPI(
    title="Caderno Inteligente API",
    description="API local e auditável para apoio à decisão do PCP.",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(SETTINGS.cors_origins),
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["X-Request-ID"],
    allow_credentials=False,
)
install_error_handling(app, settings)
logger.info(
    "api_settings environment=%s demo_mode=%s write_enabled=%s cors_origins=%s persistence=%s data_source=%s",
    SETTINGS.environment, SETTINGS.demo_mode, SETTINGS.write_enabled, len(SETTINGS.cors_origins),
    "postgres" if os.getenv("DATABASE_URL") else "sqlite", data_source(),
)


def _file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _optional_file_signature(path: Path) -> tuple[int, int] | None:
    try:
        return _file_signature(path)
    except FileNotFoundError:
        return None


VERSION_CHECK_SECONDS = 5.0
_version_seen: tuple[float, int] | None = None


def _dataset_version() -> int:
    """Versão dos dados no banco, consultada no máximo a cada VERSION_CHECK_SECONDS; outra instância que alterou um SKU é vista em seguida."""
    global _version_seen
    now = monotonic()
    if _version_seen is not None and now - _version_seen[0] < VERSION_CHECK_SECONDS:
        return _version_seen[1]
    version = dataset_store().version()
    _version_seen = (now, version)
    return version


def invalidate_dataset_version() -> None:
    """Chamado depois de cada alteração de SKU: a instância que gravou recalcula já na próxima consulta."""
    global _version_seen
    _version_seen = None


def _source_signature() -> tuple:
    if data_source() == "banco":
        return ("banco", _dataset_version())
    return _file_signature(SOURCE)


def _pipeline_signature() -> tuple[tuple, ...]:
    return (_source_signature(), *(_file_signature(path) for path in (WEIGHTS_FILE, THRESHOLDS_FILE, ENGINE_CONFIG_FILE, SUPPLY_PLAN_FILE)),
            *(_optional_file_signature(path) for path in OPTIONAL_CONFIG_FILES))


def load_source() -> dict[str, pd.DataFrame]:
    """As mesmas abas, da planilha ou do banco; o restante do pipeline não sabe a diferença."""
    if data_source() == "banco":
        return dataset_store().load_dataset()
    return load_workbook(SOURCE)


_pipeline_lock = Lock()
# Slots: (assinatura, resultado, planos, capacidade, alocação ou a exceção que a bloqueou, impacto ou None).
_pipeline_cache: tuple[tuple[tuple, ...], tuple, dict, dict, dict | Exception, dict | None] | None = None
_cache_hits = 0


def _current_prices(dataset: dict[str, pd.DataFrame]) -> dict[str, float | None]:
    """Preço vigente por SKU: o último de Precos_Produtos por Vigência fictícia. SKU sem preço fica fora (vira None na alocação)."""
    prices = dataset.get("Precos_Produtos")
    if prices is None or prices.empty:
        return {}
    return prices.sort_values("Vigência fictícia").groupby("SKU")["Preço unitário (R$)"].last().to_dict()


def _layer_warning(code: str, config_file: Path, message: str, error: Exception) -> dict:
    """Aviso de qualidade de uma camada aditiva que caiu; o restante do pipeline segue."""
    logger.warning("additive_layer_failed code=%s error_type=%s", code, type(error).__name__)
    # Em produção a causa técnica fica só no log (mesma regra das mensagens de erro da API).
    return {"code": code, "sheet": f"config/{config_file.name}", "count": 1, "message": public_message(settings(), message, error)}


def _capacity_extension(quality: dict) -> dict:
    """Extensão da capacidade (Etapa 16.5); ausente ou inválida, a capacidade usa só o calendário da base e avisa."""
    try:
        return load_capacity_extension(CAPACITY_EXTENSION_FILE)
    except (OSError, ValueError, KeyError, TypeError) as error:
        quality["warnings"].append(_layer_warning("CAPACITY_EXTENSION_UNAVAILABLE", CAPACITY_EXTENSION_FILE,
                                                  "Capacidade estimada desligada; só o calendário da base foi usado", error))
        return dict(CAPACITY_EXTENSION_OFF)


def _build_pipeline():
    started = perf_counter()
    dataset = normalise_dataset(load_source())
    quality = validate_dataset(dataset)
    thresholds = load_rule_thresholds()
    supply_settings = load_supply_settings(SUPPLY_PLAN_FILE)
    # A previsão vem antes dos indicadores: a cobertura usa a demanda de referência (Etapa 15.2).
    forecasts = build_official_forecasts(dataset["Vendas_24m"], load_engine_config(ENGINE_CONFIG_FILE))
    demand_settings = {"days_per_month": supply_settings["days_per_month"], "registered_demand_divergence": thresholds["registered_demand_divergence"]}
    indicators = build_sku_indicators(dataset, forecasts, demand_settings)
    warning = registered_demand_warning(indicators, thresholds["registered_demand_divergence"])
    if warning:
        quality["warnings"].append(warning)
    # Etapa 16.1 (P7c): fontes comerciais que não fecham entre si viram aviso de qualidade.
    for source_warning in (sellin_billing_divergence_warning(dataset), billing_uniform_split_warning(dataset)):
        if source_warning:
            quality["warnings"].append(source_warning)
    # Etapa 15.3: plano datado por SKU (projeção diária, ordens planejadas, ajustes de OP) alimenta regras e ações.
    plans = build_supply_plans(dataset, indicators, forecasts, supply_settings)
    # Etapa 15.5: pares parceiro–SKU com estoque acumulando chegam ao SKU (sinal e evidência na OP a rever).
    partner_items = build_partner_insights(dataset, load_commercial_thresholds(COMMERCIAL_THRESHOLDS_FILE))["items"]
    attach_partner_buildup(plans, partner_items)
    # Etapa 15.4: as ordens planejadas disputam a capacidade livre de cada linha, semana a semana.
    capacity = build_capacity_plan(plans, indicators, dataset["Capacidade_Semanal"], dataset["Carteira_Pedidos"], supply_settings["reference_date"],
                                   load_engine_config(ENGINE_CONFIG_FILE)["evaluation"]["peak_months"], extension=_capacity_extension(quality))
    for sku, plan in plans.items():
        plan["capacity"] = capacity["skus"].get(sku)
        if plan["capacity"] and plan["capacity"]["status"] == "insuficiente":
            plan["signals"].append("CAPACITY_SHORTFALL")
    # Etapa 16.2: o estoque escasso é distribuído só entre pedidos confirmados (sugestão; nada é reservado).
    # Camada aditiva: configuração inválida derruba só a alocação (e o impacto); a fila volta a ordenar por sinais, com aviso.
    prices = _current_prices(dataset)
    try:
        allocation = build_allocation(plans, dataset["Parceiros_Canais"], partner_items, prices, load_allocation_settings(ALLOCATION_FILE), supply_settings["reference_date"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        allocation = error if isinstance(error, (ValueError, KeyError)) else ValueError(str(error))
        quality["warnings"].append(_layer_warning("ALLOCATION_UNAVAILABLE", ALLOCATION_FILE, "Alocação indisponível; a fila foi ordenada por sinais", error))
    # Etapa 16.3: faixa de urgência e valor em risco ordenam a fila; a ABC medida é exibida ao lado da do cadastro.
    impact = None
    if not isinstance(allocation, Exception):
        try:
            impact_settings = load_impact_settings(IMPACT_FILE)
            abc = measured_abc(dataset["Vendas_24m"], impact_settings)
            abc_warning = abc_registry_divergence_warning(dataset["Produtos"], abc)
            if abc_warning:
                quality["warnings"].append(abc_warning)
            impact = {"plans": plans, "allocation": allocation, "prices": prices, "abc": abc, "settings": impact_settings}
        except (OSError, ValueError, KeyError, TypeError) as error:
            quality["warnings"].append(_layer_warning("IMPACT_UNAVAILABLE", IMPACT_FILE, "Faixa e valor em risco indisponíveis; a fila foi ordenada por sinais", error))
    issues = evaluate_rules(indicators, thresholds, plans)
    weights = load_weights()
    try:
        ranking = prioritize(issues, weights, indicators, impact=impact)
    except (ValueError, KeyError, TypeError) as error:
        if impact is None:
            raise
        quality["warnings"].append(_layer_warning("IMPACT_UNAVAILABLE", IMPACT_FILE, "Faixa e valor em risco indisponíveis; a fila foi ordenada por sinais", error))
        impact = None
        ranking = prioritize(issues, weights, indicators)
    logger.info(
        "pipeline_built duration_ms=%.1f skus=%s issues=%s",
        (perf_counter() - started) * 1000,
        len(indicators),
        len(issues),
    )
    return (dataset, quality, indicators, issues, ranking, forecasts), plans, capacity, allocation, impact


def _cached():
    global _pipeline_cache, _cache_hits
    signature = _pipeline_signature()
    with _pipeline_lock:
        if _pipeline_cache and _pipeline_cache[0] == signature:
            _cache_hits += 1
            return _pipeline_cache
        result, plans, capacity, allocation, impact = _build_pipeline()
        _pipeline_cache = (signature, result, plans, capacity, allocation, impact)
        return _pipeline_cache


def pipeline():
    """Return cached data, invalidated when the source or configuration changes."""
    return _cached()[1]


def supply_plans() -> dict[str, dict]:
    """Plano de suprimento datado por SKU (Etapa 15.3), do mesmo cache do pipeline."""
    return _cached()[2]


def capacity_plan() -> dict:
    """Capacidade semanal finita (Etapa 15.4), do mesmo cache do pipeline."""
    return _cached()[3]


def allocation() -> dict:
    """Alocação sugerida do estoque escasso entre pedidos confirmados (Etapa 16.2), do mesmo cache do pipeline.

    Se a configuração bloqueou a alocação, levanta a mesma causa (ValueError/KeyError → 422 nas rotas), sem recalcular."""
    result = _cached()[4]
    if isinstance(result, Exception):
        raise ValueError(str(result))
    return result


def _allocation_or_none() -> dict | None:
    """Para camadas que só enriquecem (rótulos, detalhe, validação): alocação indisponível vira None."""
    result = _cached()[4]
    return None if isinstance(result, Exception) else result


def _impact() -> dict | None:
    """Entradas do ranking por faixa e valor (Etapa 16.3): plans, allocation, prices, abc e settings; None se a camada caiu."""
    return _cached()[5]


_direct_channels_cache: tuple[tuple, dict | Exception] | None = None


def direct_channels() -> dict:
    """Sugestão de canais diretos (Etapa 16.1), calculada uma vez por pipeline em cache e reaproveitada pelas rotas."""
    global _direct_channels_cache
    built = pipeline()
    cached = _direct_channels_cache
    if cached is None or cached[0] is not built:
        try:
            result = build_direct_channels(built[0], load_direct_channel_settings(DIRECT_CHANNEL_FILE))
        except (OSError, ValueError, KeyError) as error:
            result = error if isinstance(error, (ValueError, KeyError)) else ValueError(str(error))
        cached = _direct_channels_cache = (built, result)
    if isinstance(cached[1], Exception):
        raise cached[1]
    return cached[1]


_revenue_cache: tuple[tuple, dict] | None = None


def revenue_forecast() -> dict:
    """Estimativa de faturamento derivada da previsão em unidades; reaproveita o cache do pipeline."""
    global _revenue_cache
    built = pipeline()
    cached = _revenue_cache
    if cached is not None and cached[0] is built:
        return cached[1]
    dataset, forecasts = built[0], built[5]
    result = build_revenue_forecasts(
        forecasts, dataset["Produtos"], dataset["Vendas_24m"], dataset.get("Precos_Produtos"), dataset.get("Forecast_Comercial"),
    )
    _revenue_cache = (built, result)
    return result


_production_cache: tuple[tuple, dict] | None = None


def production_plan() -> dict:
    """Ordens planejadas somadas por mês de liberação; reaproveita o plano de suprimento em cache."""
    global _production_cache
    cached_pipeline = _cached()
    cached = _production_cache
    if cached is not None and cached[0] is cached_pipeline:
        return cached[1]
    built, plans = cached_pipeline[1], cached_pipeline[2]
    result = build_production_plan(plans, built[2], built[5])
    _production_cache = (cached_pipeline, result)
    return result


_projected_stock_cache: tuple[tuple, dict] | None = None


def projected_stock() -> dict:
    """Falta e segurança projetadas no horizonte, agregadas do plano de suprimento em cache (fase 2)."""
    global _projected_stock_cache
    cached_pipeline = _cached()
    cached = _projected_stock_cache
    if cached is not None and cached[0] is cached_pipeline:
        return cached[1]
    built, plans = cached_pipeline[1], cached_pipeline[2]
    result = build_projected_stock(plans, built[2], built[5], production_plan())
    _projected_stock_cache = (cached_pipeline, result)
    return result


def _projected_stock_summary() -> dict | None:
    """Camada aditiva: uma falha na agregação não pode derrubar os indicadores do Início."""
    try:
        return projected_stock()
    except Exception:  # noqa: BLE001
        logger.exception("projected_stock_failed")
        return None


def _revenue_item(sku: str) -> dict | None:
    """Camada aditiva: uma falha na estimativa não pode derrubar o detalhe operacional do SKU."""
    try:
        return next((item for item in revenue_forecast()["items"] if item["sku"] == sku), None)
    except Exception:  # noqa: BLE001
        logger.exception("revenue_forecast_failed sku=%s", sku)
        return None


_events_cache: tuple[object, tuple[int, int], dict] | None = None


def event_analysis() -> dict:
    """Alertas e cenário de eventos derivados da previsão base; invalida com o pipeline e com config/event_factors.json."""
    global _events_cache
    built = pipeline()
    signature = _file_signature(EVENT_FACTORS_FILE)
    cached = _events_cache
    if cached is not None and cached[0] is built and cached[1] == signature:
        return cached[2]
    dataset, _, indicators, issues, _, forecasts = built
    prices = {item["sku"]: item["unit_price"] for item in revenue_forecast()["items"] if item["status"] == "ok"}
    result = build_event_analysis(
        forecasts, dataset["Produtos"], dataset["Vendas_24m"], dataset["Calendario_Eventos"], load_event_settings(EVENT_FACTORS_FILE), prices,
    )
    indicator_by_sku = {row["SKU"]: row for row in _records(indicators)}
    codes_by_sku: dict[str, list[str]] = {}
    for row in issues.to_dict("records"):
        codes_by_sku.setdefault(row["sku"], []).append(row["code"])
    for item in result["items"]:
        scenario, indicator = item["scenario"], indicator_by_sku.get(item["sku"])
        if scenario is None or indicator is None:
            continue
        forecast = _forecast_record(forecasts, item["sku"])
        codes = [{"code": code} for code in codes_by_sku.get(item["sku"], [])]
        official = _recommendation_for(indicator, forecast, codes)["suggested_quantity"]
        with_event = _recommendation_for(indicator, {**forecast, "forecast_next_month": scenario["scenario_units"][0]}, codes, use_plan=False)["suggested_quantity"]
        scenario["quantity"] = {
            "official": official, "with_event": with_event, "differs": official != with_event,
            "note": "A quantidade oficial cobre só o próximo mês; o evento fora dele não altera a quantidade, e sim a data de decisão.",
        }
    _events_cache = (built, signature, result)
    return result


def _event_item(sku: str) -> dict | None:
    """Camada aditiva: falha em eventos não pode derrubar o detalhe operacional do SKU."""
    try:
        return next((item for item in event_analysis()["items"] if item["sku"] == sku), None)
    except Exception:  # noqa: BLE001
        logger.exception("event_analysis_failed sku=%s", sku)
        return None


def _event_context() -> tuple[dict[str, list[dict]] | None, date | None]:
    """Alertas por SKU e data de referência; (None, None) se a análise de eventos falhar, sem derrubar os rótulos."""
    try:
        analysis = event_analysis()
        return {item["sku"]: item["alerts"] for item in analysis["items"]}, date.fromisoformat(analysis["reference_date"])
    except Exception:  # noqa: BLE001
        logger.exception("event_context_failed")
        return None, None


def _tier_info(sku: str, ranked: dict | None, plan: dict, allocation_sku: dict | None) -> dict | None:
    """Faixa de urgência da linha do ranking; fora do ranking (ou ranking sem faixa) calculada pelo mesmo núcleo."""
    if ranked and ranked.get("urgency_tier") is not None:
        return {"tier": ranked["urgency_tier"], "label": ranked.get("urgency_label")}
    impact = _impact()
    if impact is None:
        return None
    issues = pipeline()[3]
    codes = set(issues.loc[issues["sku"] == sku, "code"]) if not issues.empty else set()
    return urgency_tier(plan, allocation_sku, codes, impact["settings"])


def _sku_challenge(sku: str, recommendation: dict, ranked: dict | None, forecast_status: str | None, alerts_by_sku, reference_date, settings: dict) -> dict:
    """Rótulo do SKU pela tabela de alavancas (Etapa 16.4): contexto do plano, da alocação e da faixa da linha do ranking."""
    alerts = None if alerts_by_sku is None else alerts_by_sku.get(sku, [])
    plan, context, allocation_result = supply_plans().get(sku), None, _allocation_or_none()
    if plan is not None and allocation_result is not None:  # alocação indisponível: rótulo sem contexto de alavancas
        allocation_sku = allocation_result["skus"].get(sku)
        capacity_status = (plan.get("capacity") or {}).get("status")
        context = build_lever_context(plan, allocation_sku, _tier_info(sku, ranked, plan, allocation_sku), capacity_status, plan.get("reference_date") or reference_date)
    priority = ranked["priority"] if ranked else None
    return label_operational(recommendation["action"], priority, forecast_status, alerts, recommendation.get("capacity_status"), reference_date, settings, context=context)


def _enrich_challenge(result: dict) -> dict:
    """Rótulos do desafio nas linhas parceiro–SKU e no resumo de cada parceiro; os campos existentes não mudam."""
    settings = load_action_settings(CHALLENGE_ACTIONS_FILE)
    priority_by_sku = {row["sku"]: row["priority"] for row in _records(pipeline()[4])}
    # Etapa 16.2: o parceiro atendido primeiro em SKU disputado também é rotulado (sinal ALLOCATION_FIRST).
    allocation_result = _allocation_or_none()
    allocation_by_partner = {entry["partner"]: entry for entry in allocation_result["partners"]} if allocation_result else {}
    by_partner: dict[str, list[dict]] = {}
    channel_rows = None
    for row in result["items"]:
        if row.get("row_kind") == "direct":
            # Etapa 16.1: no canal direto o rótulo vem da sugestão de canais diretos para o mesmo canal e SKU.
            if channel_rows is None:
                channel_rows = direct_channels()["rows"]
            match = next((item for item in channel_rows.get(row["partner"], []) if item["sku"] == row["sku"]), None)
            row["challenge_action"] = label_channel_row(match) if match is not None else label_commercial_row(row, settings)
        else:
            row["challenge_action"] = label_commercial_row(row, settings)
        by_partner.setdefault(row["partner"], []).append(row)
    for summary in result["partners"]:
        summary["challenge_action"] = label_partner(summary, by_partner.get(summary["code"], []), priority_by_sku, settings,
                                                    allocation_partner=allocation_by_partner.get(summary["code"]))
    return result


def data():
    _, quality, indicators, issues, ranking, _ = pipeline()
    return quality, indicators, issues, ranking


def _records(frame):
    """Convert a DataFrame to JSON-safe records, preserving absent values as null."""
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def _forecast_record(forecasts, sku: str):
    rows = forecasts[forecasts.sku == sku]
    if not rows.empty:
        return _records(rows)[0]
    return {
        "sku": sku,
        "status": "insufficient_data",
        "forecast_confidence": "baixa",
        "forecast_months": [],
        "forecast_values": [],
        "forecast_next_month": None,
        "forecast_total_3m": None,
        "limitation": "Não há histórico mensal disponível para este SKU.",
    }


def _recommendation_for(indicator, forecast, item_issues, use_plan: bool = True):
    """Recomendação do SKU; com o plano datado (Etapa 15.3) sempre que a previsão é a oficial."""
    return build_operational_recommendation(
        indicator,
        forecast,
        (item["code"] for item in item_issues),
        supply_plans().get(indicator["SKU"]) if use_plan else None,
    )


def _rupture_summary(issues):
    """Summarize rupture rules without counting the same SKU twice."""
    rupture_codes = ("RUP_LEAD_TIME", "RUP_SAFETY_STOCK")
    rupture_issues = issues[issues["code"].isin(rupture_codes)]
    return {
        "rupture_sku_count": int(rupture_issues["sku"].nunique()),
        "below_lead_time_count": int(
            rupture_issues.loc[rupture_issues["code"] == "RUP_LEAD_TIME", "sku"].nunique()
        ),
        "below_safety_stock_count": int(
            rupture_issues.loc[rupture_issues["code"] == "RUP_SAFETY_STOCK", "sku"].nunique()
        ),
        "rupture_signal_count": int(len(rupture_issues)),
    }


@app.get("/api/health")
def health():
    persistence = _persistence()
    try:
        database_status = "ok" if persistence.health() else "unavailable"
    except Exception:
        logger.warning("database_health_failed persistence=%s", persistence.kind)
        database_status = "unavailable"
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "source_available": SOURCE.exists(),
        "data_source": data_source(),
        "database": database_status,
        "persistence": persistence.kind,
        "cache": {"loaded": _pipeline_cache is not None, "hits": _cache_hits},
    }


@app.get("/api/system")
def system():
    """Additive, lightweight runtime information for the interface; never exposes secrets or connection details."""
    current = settings()
    return {
        "environment": current.environment,
        "demo_mode": current.demo_mode,
        "write_enabled": current.write_enabled,
        "data_source": data_source(),
        "auth_enabled": auth_secret(current.production) is not None,
        "auth_required": auth_required(),
        "text_limits": {
            "note": TEXT_LIMITS["note"],
            "user_name": TEXT_LIMITS["user_name"],
            "owner": TEXT_LIMITS["owner"],
            "case_action": TEXT_LIMITS["case_action"],
            "analysis_minutes": MAX_ANALYSIS_MINUTES,
        },
        "notice": (
            "Publicação de demonstração: os dados são fictícios e os registros podem ser apagados sem aviso."
            if current.demo_mode else None
        ),
    }


@app.get("/api/overview")
def overview():
    _, indicators, issues, ranking = data()
    rupture = _rupture_summary(issues)
    decisions = _persistence().feedback_summary()
    return {
        "total_skus": len(indicators),
        "prioritized": len(ranking),
        # Compatibilidade temporária: risk_count agora possui a mesma semântica
        # corrigida de rupture_sku_count. rupture_signal_count preserva o total
        # anterior de ocorrências para consumidores que precisem dessa informação.
        "risk_count": rupture["rupture_sku_count"],
        **rupture,
        "order_without_production": int((issues.code == "ORDER_WITHOUT_PRODUCTION").sum()),
        "excess_count": int((issues.code == "EXCESS_COVERAGE").sum()),
        "low_confidence": int((ranking.confidence == "baixa").sum()),
        "risk_distribution": issues.code.value_counts().to_dict(),
        "confidence_distribution": ranking.confidence.value_counts().to_dict(),
        "projected_stock": _projected_stock_summary(),
        "decisions_today": _decisions_today_summary(),
        **decisions,
    }


def _decisions_today_summary() -> dict | None:
    """Etapa 16.4: decisões com prazo até a referência + 7 dias. Camada aditiva: falha não derruba o Início."""
    try:
        reference = date.fromisoformat(allocation()["reference_date"])
        return decisions_today(forecast_summaries(), reference, 7)
    except Exception:  # noqa: BLE001
        logger.exception("decisions_today_failed")
        return None


@app.get("/api/priorities")
def priorities(
    family: str | None = Query(None, max_length=TEXT_LIMITS["search"]),
    confidence: str | None = Query(None, max_length=TEXT_LIMITS["search"]),
    search: str | None = Query(None, max_length=TEXT_LIMITS["search"]),
):
    *_, ranking = data()
    result = ranking
    if family:
        result = result[result.family == family]
    if confidence:
        result = result[result.confidence == confidence]
    if search:
        result = result[
            result.sku.str.contains(search, case=False, na=False)
            | result.product.str.contains(search, case=False, na=False)
        ]
    return _records(result)


@app.get("/api/revenue-forecast")
def revenue_forecast_summary():
    """Faturamento estimado (previsão em unidades × preço vigente), rotulado como estimativa; não altera previsão nem ranking."""
    return revenue_forecast()


@app.get("/api/production-plan")
def production_plan_summary():
    """Produção planejada por mês de liberação (urgente × depois), no total e por família. Plano sugerido, não ordem liberada."""
    return production_plan()


@app.get("/api/events")
def event_summary():
    """Calendário de eventos como alerta e cenário explícito; não altera previsão, ranking nem quantidade oficial."""
    try:
        return event_analysis()
    except (ValueError, KeyError) as error:
        raise HTTPException(422, _describe_error("Análise de eventos bloqueada por dados/configuração inválidos", error)) from error


IMPACT_FIELDS = ("urgency_tier", "urgency_label", "value_at_risk", "abc_registry", "abc_measured", "priority_reason")


@app.get("/api/forecasts")
def forecast_summaries():
    """Consolidate cached forecasts and recommendations without changing the official ranking."""
    _, _, indicators, issues, ranking, forecasts = pipeline()
    ranking_by_sku = {item["sku"]: item for item in _records(ranking)}
    forecast_by_sku = {item["sku"]: item for item in _records(forecasts)}
    issues_by_sku: dict[str, list[dict]] = {}
    for item in issues.to_dict("records"):
        issues_by_sku.setdefault(item["sku"], []).append(item)

    result = []
    alerts_by_sku, reference_date = _event_context()
    challenge_settings = load_action_settings(CHALLENGE_ACTIONS_FILE)
    for indicator in _records(indicators):
        sku = indicator["SKU"]
        ranked = ranking_by_sku.get(sku)
        forecast = forecast_by_sku.get(sku) or _forecast_record(forecasts, sku)
        recommendation = _recommendation_for(
            indicator,
            forecast,
            issues_by_sku.get(sku, []),
        )
        result.append(
            {
                "sku": sku,
                "product": indicator["Produto"],
                "family": indicator["family"],
                "priority": ranked["priority"] if ranked else None,
                "attention_score": ranked["attention_score"] if ranked else None,
                "confidence": ranked["confidence"] if ranked else forecast["forecast_confidence"],
                "confidence_reason": ranked["confidence_reason"] if ranked else (
                    "SKU fora do ranking oficial; a confiança exibida vem do backtest da previsão."
                ),
                # Etapa 16.3: faixa, valor em risco e ABC vêm da linha do ranking (None fora dele).
                **{key: ranked.get(key) if ranked else None for key in IMPACT_FIELDS},
                "forecast": forecast,
                "challenge_action": _sku_challenge(sku, recommendation, ranked, forecast.get("status"), alerts_by_sku, reference_date, challenge_settings),
                "operational_recommendation": {
                    key: recommendation[key]
                    for key in (
                        "action",
                        "action_label",
                        "suggested_quantity",
                        "minimum_lot",
                        "capacity_status",
                        "confidence",
                        "confidence_reason",
                        "requires_human_review",
                    )
                } | {key: recommendation[key] for key in ("secondary_actions", "planned_quantity_horizon", "first_shortfall_date") if key in recommendation},
            }
        )

    return sorted(
        result,
        key=lambda item: (
            item["priority"] is None,
            item["priority"] if item["priority"] is not None else math.inf,
            item["sku"],
        ),
    )


@app.get("/api/priorities/{sku}")
def detail(sku: str):
    _, _, indicators, issues, ranking, forecasts = pipeline()
    row = indicators[indicators.SKU == sku]
    if row.empty:
        raise HTTPException(404, "SKU não encontrado")
    weights = load_weights()
    item_issues = issues[issues.sku == sku].to_dict("records")
    contributions = [
        {
            "code": item["code"],
            "weight": weights[item["code"]],
            "description": item["description"],
        }
        for item in item_issues
    ]
    indicator = _records(row)[0]
    forecast = _forecast_record(forecasts, sku)
    recommendation = _recommendation_for(indicator, forecast, item_issues)
    event_item = _event_item(sku)
    alerts_by_sku, reference_date = _event_context()
    ranked = _records(ranking[ranking.sku == sku])
    challenge = _sku_challenge(sku, recommendation, ranked[0] if ranked else None, forecast.get("status"), alerts_by_sku, reference_date, load_action_settings(CHALLENGE_ACTIONS_FILE))
    return {
        "indicator": indicator,
        "issues": item_issues,
        "priority": ranked,
        **{key: ranked[0].get(key) if ranked else None for key in IMPACT_FIELDS},
        # Etapa 16.2: bloco da alocação do SKU (ordem de atendimento e motivo), ou null sem pedido aberto.
        "allocation": (_allocation_or_none() or {"skus": {}})["skus"].get(sku),
        "score_contributions": contributions,
        "forecast": forecast,
        "revenue_forecast": _revenue_item(sku),
        "challenge_action": challenge,
        "event_alerts": None if event_item is None else event_item["alerts"],
        "event_scenario": None if event_item is None else {"applicable": event_item["scenario_applicable"], "note": event_item["scenario_note"], "scenario": event_item["scenario"]},
        "operational_recommendation": recommendation,
        "limitation": "A base não vincula pedidos a OPs por semana; a capacidade é agregada por linha e semana e o encaixe das ordens planejadas é uma simulação, não reserva nem viabilidade individual garantida.",
    }


SCENARIO_THRESHOLD_BOUNDS = {"excess_coverage_days": (1, 3650)}


class Scenario(BaseModel):
    weights: dict[str, int] | None = None
    thresholds: dict[str, float] | None = None

    @field_validator("weights")
    @classmethod
    def _known_weights(cls, value):
        if value is None:
            return value
        unknown = sorted(set(value) - set(load_weights(WEIGHTS_FILE)))
        if unknown:
            raise ValueError(f"Regras desconhecidas: {', '.join(unknown)}")
        if any(weight < 0 or weight > 100 for weight in value.values()):
            raise ValueError("Pesos devem estar entre 0 e 100")
        return value

    @field_validator("thresholds")
    @classmethod
    def _known_thresholds(cls, value):
        if value is None:
            return value
        unknown = sorted(set(value) - set(SCENARIO_THRESHOLD_BOUNDS))
        if unknown:
            raise ValueError(f"Limiares desconhecidos: {', '.join(unknown)}")
        for key, number in value.items():
            low, high = SCENARIO_THRESHOLD_BOUNDS[key]
            if not low <= number <= high:
                raise ValueError(f"{key} deve estar entre {low} e {high}")
        return value


@app.post("/api/scenarios")
def scenario(item: Scenario):
    dataset, _, indicators, _, _, _ = pipeline()
    thresholds = {**load_rule_thresholds(), **(item.thresholds or {})}
    weights = {**load_weights(), **(item.weights or {})}
    scenario_issues = evaluate_rules(indicators, thresholds, supply_plans())
    ranking = prioritize(scenario_issues, weights, indicators, impact=_impact())
    return {
        "is_simulation": True,
        "warning": "Cenário hipotético: não altera pesos, limiares ou ranking oficial.",
        "weights": weights,
        "thresholds": thresholds,
        "ranking": _records(ranking),
        "source_sheets": len(dataset),
    }


def _partner_level(coverage: float) -> str:
    if coverage <= 0:
        return "Sem visibilidade"
    if coverage < 0.40:
        return "Essencial"
    if coverage < 0.80:
        return "Conectado"
    return "Estratégico"


def _partner_maturity(coverage: float, observed_skus: int, total_skus: int) -> dict:
    level = _partner_level(coverage)
    if level == "Sem visibilidade":
        next_level = "Essencial"
        required_skus = 1 if total_skus else 0
        requirement = "Receber sell-out de pelo menos 1 SKU."
    elif level == "Essencial":
        next_level = "Conectado"
        required_skus = max(0, math.ceil(total_skus * 0.40) - observed_skus)
        requirement = f"Observar sell-out de mais {required_skus} SKU(s) para atingir 40% de cobertura."
    elif level == "Conectado":
        next_level = "Estratégico"
        required_skus = max(0, math.ceil(total_skus * 0.80) - observed_skus)
        requirement = f"Observar sell-out de mais {required_skus} SKU(s) para atingir 80% de cobertura."
    else:
        next_level = None
        required_skus = 0
        requirement = "Manter cobertura igual ou superior a 80% e dados atualizados."
    return {
        "level": level,
        "next_level": next_level,
        "next_level_required_skus": required_skus,
        "next_level_requirement": requirement,
    }


@app.get("/api/b2b2c/visibility")
def b2b_visibility():
    dataset, *_ = pipeline()
    partners = dataset["Parceiros_Canais"]
    sell_out = dataset["Sell_Out"]
    total_skus = int(dataset["Produtos"]["SKU"].nunique())
    latest = sell_out["Mês"].max()
    # Etapa 16.1: canal direto é observado pelo faturamento (Vendas_24m) nos meses recentes da janela comercial.
    sales = dataset["Vendas_24m"]
    billed = sales[pd.to_numeric(sales["Quantidade faturada"], errors="coerce") > 0]
    recent_months = load_commercial_thresholds(ROOT / "config/commercial_thresholds.json")["recent_months"]
    recent_start = (pd.Timestamp(latest).to_period("M") - (recent_months - 1)).start_time
    rows = []
    for _, partner in partners.iterrows():
        is_direct = partner["Tipo"] == "Canal direto"
        if is_direct:
            subset = billed[billed["Cliente/Canal"] == partner["Código"]]
            observed = int(subset.loc[(subset["Mês"] >= recent_start) & (subset["Mês"] <= latest), "SKU"].nunique())
        else:
            subset = sell_out[sell_out["Cliente"] == partner["Código"]]
            observed = int(subset["SKU"].nunique())
        coverage = observed / total_skus if total_skus else 0
        rows.append(
            {
                "partner": partner["Código"],
                "name": partner["Nome fictício"],
                "type": partner["Tipo"],
                "visibility_source": "faturamento_direto" if is_direct else "sell_out_parceiro",
                "observed_skus": observed,
                "total_skus": total_skus,
                "coverage": coverage,
                "latest_sell_out_month": None if subset.empty else subset["Mês"].max().date().isoformat(),
                "months_observed": int(subset["Mês"].nunique()),
                **_partner_maturity(coverage, observed, total_skus),
            }
        )
    return {
        "reference_month": latest.date().isoformat(),
        "partners": rows,
        "journey": build_visibility_journey(dataset),
        "note": "Cobertura representa observação disponível; ausência não equivale a venda zero.",
        "classification_disclaimer": "O nível é uma classificação demonstrativa baseada em cobertura e atualidade. Não representa acordo comercial firmado.",
    }


@app.get("/api/capacity-plan")
def capacity_plan_summary():
    """Capacidade semanal finita (Etapa 15.4): famílias, semanas, faltas e premissas. Nada é reservado nem liberado."""
    plan = capacity_plan()
    return {
        "reference_date": plan["reference_date"],
        "families": plan["families"],
        "skus": {sku: {key: value[key] for key in ("family", "status", "status_now", "status_label", "unscheduled_quantity", "executable_quantity_now")}
                 for sku, value in plan["skus"].items()},
        "status_labels": plan["status_labels"],
        "assumptions": plan["assumptions"],
        "field_nature": plan["field_nature"],
        "extension": plan.get("extension"),
        "requires_human_review": True,
    }


@app.get("/api/capacity/{family}")
def capacity_timeline(family: str):
    dataset, *_ = pipeline()
    frame = dataset["Capacidade_Semanal"]
    result = frame[frame["Família"] == family].sort_values("Semana inicial")
    if result.empty:
        raise HTTPException(404, "Família não encontrada")
    allocation = {week["week_start"]: week for item in capacity_plan()["families"] if item["family"] == family for week in item["weeks"]}
    weeks = result[["Semana inicial", "Linha", "Capacidade máxima", "Capacidade comprometida", "Capacidade disponível", "Ocupação"]].to_dict("records")
    for week in weeks:
        planned = allocation.get(pd.Timestamp(week["Semana inicial"]).date().isoformat(), {})
        week["allocated"], week["remaining"] = planned.get("allocated"), planned.get("remaining")
    return {
        "family": family,
        "limitation": "Capacidade é agregada por família; não há vínculo pedido–OP por semana. 'allocated' são as ordens planejadas encaixadas (Etapa 15.4).",
        "weeks": weeks,
    }


@app.get("/api/data-quality")
def quality():
    return data()[0]


@app.post("/api/runs", dependencies=[require_write_access])
def create_snapshot():
    quality_report, _, _, ranking = data()
    run_id = _persistence().create_run(
        SOURCE, load_weights(), load_rule_thresholds(), quality_report, _records(ranking), _comparison_payload()
    )
    return {"id": run_id}


_clean_text = clean_text


def _require_known_sku(sku: str) -> None:
    if sku not in set(data()[1]["SKU"]):
        raise HTTPException(422, "SKU não encontrado na base de dados atual.")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Case(StrictModel):
    sku: str = Field(min_length=1, max_length=TEXT_LIMITS["sku"])
    run_id: int | None = Field(default=None, ge=1)
    status: str = Field(default="novo", max_length=40)
    owner: str = Field(default="", max_length=TEXT_LIMITS["owner"])
    due_date: str = Field(default="", max_length=10)
    action: str = Field(default="", max_length=TEXT_LIMITS["case_action"])
    note: str = Field(default="", max_length=TEXT_LIMITS["note"])

    @field_validator("sku", "owner", "action", "note")
    @classmethod
    def _clean(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("due_date")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        value = value.strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("Prazo deve estar no formato AAAA-MM-DD") from error
            if len(value) != 10:
                raise ValueError("Prazo deve estar no formato AAAA-MM-DD")
        return value


@app.get("/api/cases")
def cases():
    return _persistence().list_cases()


@app.post("/api/cases", dependencies=[require_write_access])
def case_create(item: Case):
    _require_known_sku(item.sku)
    try:
        return {"id": _persistence().create_case(**item.model_dump())}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.put("/api/cases/{case_id}", dependencies=[require_write_access])
def case_update(case_id: int, item: Case):
    persistence = _persistence()
    if not any(case["id"] == case_id for case in persistence.list_cases()):
        raise HTTPException(404, "Caso não encontrado")
    try:
        persistence.update_case(case_id, **item.model_dump(exclude={"sku", "run_id"}))
        return {"status": "updated", "history": persistence.case_history(case_id)}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/cases/{case_id}/history")
def case_history(case_id: int):
    return _persistence().case_history(case_id)


@app.get("/api/runs")
def runs():
    return _persistence().list_runs()


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int):
    result = _persistence().get_run(run_id)
    if not result:
        raise HTTPException(404, "Execução não encontrada")
    return result


@app.get("/api/config")
def config():
    return {
        "weights": load_weights(),
        "thresholds": load_rule_thresholds(),
        "actions": ACTIONS,
        "partner_data_effects": PARTNER_DATA_EFFECTS,
        "case_statuses": STATUSES,
    }


class Feedback(StrictModel):
    sku: str = Field(min_length=1, max_length=TEXT_LIMITS["sku"])
    action: str = Field(max_length=40)
    note: str = Field(default="", max_length=TEXT_LIMITS["note"])
    user_name: str = Field(default="", max_length=TEXT_LIMITS["user_name"])
    partner_data_effect: str = Field(default="nao_utilizado", max_length=40)
    analysis_minutes: int | None = Field(default=None, ge=0, le=MAX_ANALYSIS_MINUTES)
    challenge_action: str | None = Field(default=None, max_length=40)

    @field_validator("sku", "note", "user_name")
    @classmethod
    def _clean(cls, value: str) -> str:
        return _clean_text(value)


@app.get("/api/feedback")
def feedback():
    return _persistence().list_feedback_records()


@app.post("/api/feedback", dependencies=[require_write_access])
def feedback_post(item: Feedback):
    _require_known_sku(item.sku)
    try:
        _persistence().save_feedback(
            item.sku,
            item.action,
            item.note,
            item.user_name,
            item.partner_data_effect,
            item.analysis_minutes,
            item.challenge_action,
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"status": "created"}


# Additive commercial view: separate configuration; no change to pipeline/ranking.
from backend.partners import create_partner_router  # noqa: E402

def _describe_error(message: str, error: Exception) -> str:
    return public_message(settings(), message, error)


app.include_router(create_partner_router(lambda: pipeline()[0], ROOT / "config/commercial_thresholds.json", _describe_error, _enrich_challenge))
from backend.direct_channels import create_direct_channel_router  # noqa: E402

app.include_router(create_direct_channel_router(lambda: pipeline()[0], ROOT / "config/direct_channel_thresholds.json", _describe_error))
# Etapa 16.2: alocação sugerida do estoque escasso por pedido, parceiro e região (leitura do cache do pipeline).
from backend.allocation import create_allocation_router  # noqa: E402

app.include_router(create_allocation_router(allocation, _describe_error))

# Additive Week 4 validation view: read-only, reuses the cached pipeline and existing recommendations.
from backend.validation import create_validation_router  # noqa: E402


def _all_operational_recommendations():
    return [{**item["operational_recommendation"], "sku": item["sku"]} for item in forecast_summaries()]


app.include_router(create_validation_router(
    pipeline=pipeline,
    persistence=_persistence,
    recommendations=_all_operational_recommendations,
    supply_plans=supply_plans,
    capacity_plan=capacity_plan,
    allocation=_allocation_or_none,
    direct_channels=direct_channels,
    sku_detail=detail,
    source=SOURCE,
    config_file=ROOT / "config/validation_center.json",
    thresholds_file=THRESHOLDS_FILE,
    commercial_thresholds_file=ROOT / "config/commercial_thresholds.json",
    challenge_actions_file=CHALLENGE_ACTIONS_FILE,
    describe_error=_describe_error,
))

# Additive Etapa 14.3 forecast lab: challenger engine side by side with the official one; official outputs are untouched.
from backend.forecast_lab import create_forecast_lab_router  # noqa: E402

app.include_router(create_forecast_lab_router(
    pipeline=pipeline,
    source=SOURCE,
    engine_config_file=ENGINE_CONFIG_FILE,
    describe_error=_describe_error,
))

# Additive model card and benchmark history: evidence only; the official forecast is untouched.
from backend.model_benchmark import create_model_benchmark_router  # noqa: E402

app.include_router(create_model_benchmark_router(
    pipeline=pipeline,
    source=SOURCE,
    engine_config_file=ENGINE_CONFIG_FILE,
    benchmark_db=BENCHMARK_DB,
    describe_error=_describe_error,
))

# Additive partner stock projection: backend only until the group validates it; nothing official reads it.
from backend.partner_stock_projection import create_partner_stock_projection_router  # noqa: E402

app.include_router(create_partner_stock_projection_router(
    dataset_loader=lambda: pipeline()[0],
    settings_file=ROOT / "config/partner_projection.json",
    describe_error=_describe_error,
))

# Additive run comparison: snapshots preserve forecast, recommendation and partner coverage as computed.
from backend.run_comparisons import create_run_comparison_router  # noqa: E402
from caderno_inteligente.run_comparison import build_comparison_payload  # noqa: E402

def _comparison_payload():
    partner_result, partner_error, commercial = None, None, None
    try:
        commercial = load_commercial_thresholds(COMMERCIAL_THRESHOLDS_FILE)
        partner_result = build_partner_insights(pipeline()[0], commercial)
    except (OSError, ValueError, KeyError) as error:
        partner_error = f"Análise comercial indisponível no registro: {error}"
    return build_comparison_payload(forecast_summaries(), partner_result, commercial, partner_error)


app.include_router(create_run_comparison_router(_persistence))

# Etapa 16.6: cobertura de regras (quanto cada regra e rótulo dispara nas saídas atuais e, se zero, por quê).
from backend.rules_coverage import create_rules_coverage_router  # noqa: E402

app.include_router(create_rules_coverage_router(
    pipeline=pipeline,
    forecast_items=forecast_summaries,
    commercial=lambda: _enrich_challenge(build_partner_insights(pipeline()[0], load_commercial_thresholds(COMMERCIAL_THRESHOLDS_FILE))),
    direct_channels=direct_channels,
    describe_error=_describe_error,
))

# Fase 3: login e cadastro de SKU; só grava com DATA_SOURCE=banco.
app.include_router(create_registry_router(
    production=lambda: settings().production,
    data_source=data_source,
    store=dataset_store,
    users=user_store,
    write_access=require_write_access,
    on_change=invalidate_dataset_version,
))
