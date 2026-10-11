import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from caderno_inteligente.action_labels import (
    CHALLENGE_PDF_CODES, DEFAULT_SETTINGS, DEFINITIONS, LABELS, PRECEDENCE, label_channel_row, label_commercial_row, label_operational,
    label_partner, load_action_settings, recompra_signal,
)
from caderno_inteligente.feedback import init_feedback_db, list_feedback, list_feedback_records, save_feedback

ROOT = Path(__file__).resolve().parents[1]
S = dict(DEFAULT_SETTINGS)
REF = date(2026, 8, 31)


def _op(action, priority=None, status="ok", alerts=(), capacity="family_context_available"):
    return label_operational(action, priority, status, None if alerts is None else list(alerts), capacity, REF, S)


def _alert(decision, in_horizon=True, event_id="bf"):
    return {"event_id": event_id, "event": "Black Friday", "decision_date": decision, "in_horizon": in_horizon}


def _row(action="monitorar_estoque", **extra):
    base = {"partner": "KA", "sku": "A", "action": action, "data_quality": "sufficient", "coverage_days": 60, "average_monthly_sell_out": 50, "estimated_stock": 100,
            "reference_month": "2026-08", "signals": [], "periods": [{"month": f"2026-{m:02d}", "sell_in_quantity": 10} for m in range(1, 6)]}
    return {**base, **extra}


# --- configuração e vocabulário ----------------------------------------------

def test_shipped_settings_load_and_invalid_values_are_rejected(tmp_path):
    assert load_action_settings(ROOT / "config/challenge_actions.json") == DEFAULT_SETTINGS
    for bad in ({"x": 1}, {"priority_top_n": 0}, {"priority_top_n": 2.5}, {"recompra_min_sell_in_months": 1}, {"event_decision_window_days": -1}, {"partner_min_opportunities": True}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            load_action_settings(path)


def test_every_label_is_defined_and_the_nine_pdf_actions_exist():
    assert set(CHALLENGE_PDF_CODES) <= set(LABELS) and len(CHALLENGE_PDF_CODES) == 9
    assert set(DEFINITIONS) == set(LABELS) and all(PRECEDENCE.values())
    assert {LABELS[c] for c in CHALLENGE_PDF_CODES} == {"Produzir", "Repor", "Priorizar produção", "Priorizar parceiro", "Ampliar mix", "Recomendar recompra", "Monitorar", "Investigar", "Sem ação necessária"}


# --- SKU (operacional) -------------------------------------------------------

def test_operational_mapping_and_priority_rule():
    assert _op("investigar_dados", status="insufficient_data")["code"] == "investigar"
    assert _op("monitorar_excesso")["code"] == "monitorar" and _op("sem_acao_necessaria")["code"] == "sem_acao_necessaria"
    assert _op("produzir", priority=25, alerts=[])["code"] == "produzir"
    top = _op("produzir", priority=10, alerts=[])
    assert top["code"] == "priorizar_producao" and "priority_top_10" in top["signals_used"] and top["evidence"][0]["value"] == 10
    assert _op("produzir", priority=11, alerts=[])["code"] == "produzir"
    assert _op("produzir", priority=None, alerts=[])["code"] == "produzir"  # fora do ranking nunca vira prioridade


def test_event_decision_window_and_horizon_drive_priorizar_producao():
    inside = _op("produzir", priority=30, alerts=[_alert("2026-09-30")])
    assert inside["code"] == "priorizar_producao" and "event_decision:bf" in inside["signals_used"]
    assert _op("produzir", priority=30, alerts=[_alert("2026-10-01")])["code"] == "produzir"          # 31 dias: fora da janela
    assert _op("produzir", priority=30, alerts=[_alert("2026-09-10", in_horizon=False)])["code"] == "produzir"
    assert _op("produzir", priority=30, alerts=[{"event_id": "x", "event": "X", "decision_date": None, "in_horizon": True}])["code"] == "produzir"


def test_unavailable_event_analysis_is_declared_and_does_not_invent_urgency():
    result = _op("produzir", priority=30, alerts=None)
    assert result["code"] == "produzir" and any("indisponível" in text for text in result["limitations"])


def test_capacity_pressure_keeps_the_label_but_adds_the_warning_and_review_flag():
    result = _op("produzir_validar_capacidade", priority=2, alerts=[], capacity="requires_review")
    assert result["code"] == "priorizar_producao" and result["requires_human_review"] is True
    assert any("capacidade" in text.lower() for text in result["limitations"])
    assert result["origin_action"] == "produzir_validar_capacidade"


def test_insufficient_forecast_beats_everything_even_with_a_producing_action():
    assert _op("produzir", priority=1, status="insufficient_data", alerts=[_alert("2026-09-01")])["code"] == "investigar"


# --- parceiro–SKU (comercial) ------------------------------------------------

def test_dirty_or_divergent_data_is_investigar_and_never_an_opportunity():
    for action in ("solicitar_atualizacao", "dados_insuficientes", "investigar_divergencia"):
        result = label_commercial_row(_row(action, coverage_days=5, signals=[{"code": "REPOSITION_OPPORTUNITY"}]), S)
        assert result["code"] == "investigar" and result["origin_action"] == action and result["evidence"]
    assert label_commercial_row(_row("avaliar_reposicao", signals=[{"code": "REPOSITION_OPPORTUNITY"}], coverage_days=20), S)["code"] == "repor"


def test_direct_channel_row_is_monitored_from_observed_billing_and_never_insufficient_data():
    row = _row("canal_direto", partner="E-commerce", estimated_stock=None, coverage_days=None, data_quality="sufficient")
    result = label_commercial_row(row, S)
    assert result["code"] == "monitorar" and result["source"] == "commercial" and result["origin_action"] == "canal_direto"
    assert "estoque intermediário" in result["reason"] and "faturamento" in result["reason"]
    assert result["evidence"][0]["origin"].startswith("Vendas_24m") and result["requires_human_review"] is True


def test_recompra_needs_a_gap_longer_than_the_pairs_own_rhythm_and_positive_sell_out():
    assert label_commercial_row(_row(), S)["code"] == "recomendar_recompra"
    result = label_commercial_row(_row(), S)
    assert result["signals_used"] == ["RECOMPRA_GAP"] and {item["label"] for item in result["evidence"]} >= {"Último sell-in", "Meses sem sell-in"}
    assert recompra_signal(_row(), S)["last_sell_in_month"] == "2026-05" and recompra_signal(_row(), S)["months_without_sell_in"] == 3
    assert label_commercial_row(_row(periods=[{"month": f"2026-{m:02d}", "sell_in_quantity": 10} for m in range(1, 9)]), S)["code"] == "monitorar"   # enviado até agosto
    assert label_commercial_row(_row(average_monthly_sell_out=None), S)["code"] == "monitorar"
    assert label_commercial_row(_row(average_monthly_sell_out=0), S)["code"] == "monitorar"
    assert label_commercial_row(_row(periods=[{"month": "2026-01", "sell_in_quantity": 10}, {"month": "2026-02", "sell_in_quantity": 10}]), S)["code"] == "monitorar"  # pouca história
    quarterly = [{"month": m, "sell_in_quantity": 10} for m in ("2025-09", "2025-12", "2026-03")]
    assert label_commercial_row(_row(periods=quarterly), S)["code"] == "monitorar"  # ritmo trimestral: 5 meses < 2 × 3 = 6
    assert label_commercial_row(_row("avaliar_reposicao", signals=[{"code": "REPOSITION_OPPORTUNITY"}]), S)["code"] == "repor"  # reposição vence recompra


# --- parceiro ---------------------------------------------------------------

def _partner_rows(*skus):
    return [{**_row("avaliar_reposicao", sku=sku, signals=[{"code": "REPOSITION_OPPORTUNITY"}]), "challenge_action": {"code": "repor"}} for sku in skus]


def test_priorizar_parceiro_requires_several_reposicoes_with_a_top_priority_sku():
    summary = {"code": "KA", "name": "Parceiro"}
    ok = label_partner(summary, _partner_rows("A", "B"), {"A": 4, "B": 30}, S)
    assert ok["code"] == "priorizar_parceiro" and ok["evidence"][0]["value"] == 2 and ok["evidence"][1]["value"] == 4
    assert label_partner(summary, _partner_rows("A"), {"A": 1}, S) is None                    # só uma reposição
    assert label_partner(summary, _partner_rows("A", "B"), {"A": 15, "B": 30}, S) is None    # nenhuma no topo
    assert label_partner(summary, _partner_rows("A", "B"), {"A": None, "B": 30}, S) is None  # fora do ranking não conta
    rows = _partner_rows("A", "B") + [{**_row(sku="C"), "challenge_action": {"code": "investigar"}}]
    assert label_partner(summary, rows[:1] + rows[2:], {"A": 1, "C": 2}, S) is None           # dado ruim não conta como oportunidade


# --- canais diretos ----------------------------------------------------------

@pytest.mark.parametrize("suggestion,expected", [
    ("avaliar_ampliacao_mix", "ampliar_mix"), ("avaliar_reativacao", "reativar"), ("investigar_queda", "investigar"),
    ("monitorar_saida_de_linha", "monitorar"), ("acompanhar_crescimento", "monitorar"), ("sem_acao_necessaria", "sem_acao_necessaria"),
])
def test_channel_suggestions_map_to_challenge_labels(suggestion, expected):
    row = {"signals": ["X"], "revenue_24m": 1.0, "trend": "estável", "last_month": "2026-08-01", "suggestion": {"code": suggestion, "reason": "Motivo."}}
    result = label_channel_row(row)
    assert result["code"] == expected and result["origin_action"] == suggestion and result["reason"] == "Motivo."
    assert any("estoque por canal" in text.lower() for text in result["limitations"])


# --- casos congelados --------------------------------------------------------

def test_every_label_has_at_least_one_frozen_case():
    cases = json.loads((ROOT / "config/validation_center.json").read_text(encoding="utf-8"))["cases"]
    covered = {case["expected"]["code"] for case in cases if case["kind"] == "challenge_action"}
    assert covered == set(LABELS)


# --- API sobre a base real ---------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("labels")
    patch = pytest.MonkeyPatch()
    patch.setattr(main, "RUNS_DB", tmp / "runs.db")
    patch.setattr(main, "CASES_DB", tmp / "cases.db")
    patch.setattr(main, "FEEDBACK_DB", tmp / "feedback.db")
    patch.delenv("DATABASE_URL", raising=False)
    yield TestClient(main.app)
    patch.undo()


def test_api_forecasts_carry_the_label_without_changing_existing_fields(client):
    items = client.get("/api/forecasts").json()
    for item in items:
        label = item["challenge_action"]
        assert label["requires_human_review"] is True and label["code"] in LABELS and label["evidence"] is not None
        action = item["operational_recommendation"]["action"]
        if action == "investigar_dados":
            assert label["code"] == "investigar"
        elif action in ("produzir", "produzir_validar_capacidade"):
            assert label["code"] in ("produzir", "priorizar_producao", "monitorar")
            if label["code"] == "monitorar":   # Etapa 16.4: próxima liberação depois da janela de decisão
                assert label["lever"] == "produzir_futuro" and "PLANNED_RELEASE_AFTER_WINDOW" in label["signals_used"] and label["decide_by"]
            if item["priority"] is not None and item["priority"] <= 10:
                assert label["code"] == "priorizar_producao"
        elif action == "monitorar_excesso":
            assert label["code"] == "monitorar"
    assert {"sku", "product", "family", "priority", "attention_score", "confidence", "forecast", "operational_recommendation"} <= set(items[0])
    assert any(item["challenge_action"]["code"] == "priorizar_producao" for item in items)


def test_api_sku_detail_label_matches_the_list(client):
    listed = next(item for item in client.get("/api/forecasts").json() if item["sku"] == "CI-0049")
    detail = client.get("/api/priorities/CI-0049").json()
    # Etapa 16.4: CI-0049 tem pedidos sem cobertura disputados por 2 ou mais clientes → a decisão é quem atender (linha 2)
    assert detail["challenge_action"] == listed["challenge_action"] and detail["challenge_action"]["code"] == "priorizar_parceiro"
    assert detail["challenge_action"]["lever"] == "alocar"


def test_api_commercial_rows_partners_and_filters(client):
    body = client.get("/api/commercial-recommendations?limit=500").json()
    assert body["challenge_labels"]["repor"] == "Repor"
    for row in body["items"]:
        label = row["challenge_action"]
        if row["action"] == "avaliar_reposicao":
            assert label["code"] == "repor"
        if row["action"] in ("dados_insuficientes", "solicitar_atualizacao", "investigar_divergencia"):
            assert label["code"] == "investigar"
    repor = client.get("/api/commercial-recommendations?challenge_action=repor&limit=500").json()
    assert repor["total"] == sum(1 for row in body["items"] if row["challenge_action"]["code"] == "repor") > 0
    partners = client.get("/api/partners").json()["items"]
    labeled = [p for p in partners if p["challenge_action"]]
    assert labeled and all(p["challenge_action"]["code"] == "priorizar_parceiro" for p in labeled)
    for p in labeled:   # Etapa 16.2: primeiro atendido em SKU disputado (ALLOCATION_FIRST) ou várias reposições
        label = p["challenge_action"]
        if "ALLOCATION_FIRST" in label["signals_used"]:
            assert label["evidence"][0]["label"] == "SKUs disputados em que é o primeiro atendido" and label["evidence"][0]["value"]
        else:
            assert label["evidence"][0]["value"] >= 2
    assert any("ALLOCATION_FIRST" in p["challenge_action"]["signals_used"] for p in labeled)
    only = client.get("/api/partners?challenge_action=priorizar_parceiro").json()["items"]
    assert {p["code"] for p in only} == {p["code"] for p in labeled}
    assert client.get("/api/partners?challenge_action=repor").json()["total"] > 0
    assert client.get("/api/partners/KA-01/skus?challenge_action=repor").json()["total"] > 0
    assert client.get("/api/commercial-recommendations?challenge_action=xyz").status_code == 422
    assert client.get("/api/partners?challenge_action=xyz").status_code == 422


def test_api_commercial_fields_other_than_the_label_are_unchanged(client):
    row = client.get("/api/commercial-recommendations?limit=1").json()["items"][0]
    assert {"action", "action_label", "signals", "recommendation_reason", "requires_human_review", "periods"} <= set(row)


def test_api_direct_channel_rows_carry_labels_and_filter(client):
    detail = client.get("/api/direct-channels/E-commerce").json()
    assert detail["challenge_labels"]["ampliar_mix"] == "Ampliar mix" and all(row["challenge_action"]["code"] in LABELS for row in detail["items"])
    assert {row["challenge_action"]["code"] for row in detail["items"]} <= {"ampliar_mix", "reativar", "investigar", "monitorar", "sem_acao_necessaria"}
    filtered = client.get("/api/direct-channels/E-commerce?challenge_action=investigar").json()
    assert 0 < filtered["total"] < 50 and all(row["challenge_action"]["code"] == "investigar" for row in filtered["items"])
    assert client.get("/api/direct-channels/E-commerce?challenge_action=xyz").status_code == 422


def test_api_validation_summary_runs_the_frozen_label_cases(client):
    body = client.get("/api/validation/summary").json()["frozen_cases"]
    challenge = [item for item in body["items"] if item["kind"] == "challenge_action"]
    assert len(challenge) == 11 and all(item["result"] == "passou" for item in challenge)
    assert {item["obtained"]["code"] for item in challenge} == set(LABELS)


# --- registro da decisão -----------------------------------------------------

def test_feedback_records_the_label_and_old_decisions_stay_null(client):
    assert client.post("/api/feedback", json={"sku": "CI-0049", "action": "aceita", "note": "ok"}).status_code == 200
    assert client.post("/api/feedback", json={"sku": "CI-0049", "action": "aceita", "note": "com rótulo", "challenge_action": "priorizar_producao"}).status_code == 200
    rows = client.get("/api/feedback").json()
    assert rows[0]["challenge_action"] == "priorizar_producao" and rows[1]["challenge_action"] is None
    assert client.post("/api/feedback", json={"sku": "CI-0049", "action": "aceita", "challenge_action": "inventado"}).status_code == 422


def test_sqlite_feedback_migrates_an_old_database_without_losing_rows(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE feedback (id INTEGER PRIMARY KEY, sku TEXT NOT NULL, action TEXT NOT NULL, note TEXT, user_name TEXT, created_at TEXT NOT NULL, partner_data_effect TEXT NOT NULL DEFAULT 'nao_utilizado', analysis_minutes INTEGER)")
        conn.execute("INSERT INTO feedback(sku, action, note, user_name, created_at) VALUES('CI-1','aceita','n','u','2026-01-01T00:00:00+00:00')")
    init_feedback_db(path)
    save_feedback(path, "CI-2", "alterada", "n2", "u2", challenge_action="repor")
    records = list_feedback_records(path)
    assert [r["challenge_action"] for r in records] == ["repor", None] and [r["sku"] for r in records] == ["CI-2", "CI-1"]
    assert len(list_feedback(path)) == 2 and len(list_feedback(path)[0]) == 7   # formato histórico da tupla preservado
    with pytest.raises(ValueError):
        save_feedback(path, "CI-3", "aceita", "", "", challenge_action="xyz")


def test_postgres_migration_is_additive_and_documented():
    sql = (ROOT / "supabase/migrations/003_challenge_action.sql").read_text(encoding="utf-8").lower()
    assert "add column if not exists challenge_action text" in sql and "drop" not in sql and "not null" not in sql


def test_frontend_names_and_definitions_match_the_backend_vocabulary():
    """O frontend repete os textos (Guia, filtros); um texto diferente do backend seria uma segunda fonte de verdade."""
    source = (ROOT / "frontend/src/pages/shared.ts").read_text(encoding="utf-8")

    def block(name: str) -> dict[str, str]:
        body = source[source.index(f"export const {name}"):]
        body = body[body.index("{\n") + 1: body.index("\n};")]
        return dict(re.findall(r"(\w+): '([^']*)'", body))  # os textos não usam apóstrofo

    assert block("CHALLENGE_NAMES") == LABELS
    assert block("CHALLENGE_DEFINITIONS") == DEFINITIONS


# --- P3: tabela de decisão por alavanca (Etapa 16.4) --------------------------

from caderno_inteligente.action_labels import LEVERS, build_lever_context, decisions_today  # noqa: E402


def _ctx(**extra):
    base = {"urgency_tier": 4, "discontinued": False, "uncovered_orders": [], "contested": False, "decision_text": None, "first_client": None, "last_client": None,
            "urgent_planned_quantity": 0, "next_urgent_release_date": None, "first_planned_release_date": None, "anticipable_ops": [],
            "forecast_only_shortfall": False, "first_shortfall_date": None, "decision_window_end": "2026-09-28", "capacity_status": None, "reference_date": "2026-08-31"}
    return {**base, **extra}


def _order(name="PED-1", client="KA-01", promised="2026-09-10", quantity=100, uncovered=40):
    return {"order": name, "client": client, "quantity": quantity, "uncovered_at_promise": uncovered, "promised_date": promised}


def _lv(action, ctx, priority=3, status="ok", alerts=(), capacity="family_context_available"):
    return label_operational(action, priority, status, None if alerts is None else list(alerts), capacity, REF, S, ctx)


def test_without_context_output_is_legacy_plus_empty_lever_fields():
    new, old = _op("atraso_inevitavel", 3), label_operational("atraso_inevitavel", 3, "ok", [], "family_context_available", REF, S, None)
    assert new == old and new["code"] == "priorizar_producao" and new["lever"] is None and new["decide_by"] is None
    assert LEVERS == ("alocar", "antecipar_op", "produzir_agora", "renegociar", "produzir_futuro", "rever_op", "nenhuma")


def test_row2_never_says_serve_a_client_before_itself():
    ctx = _ctx(uncovered_orders=[_order()], contested=True, first_client="KA-01", last_client="KA-01", decision_text="KA-01 recebe 10 un. agora")
    out = _lv("atraso_inevitavel", ctx)
    assert "antes de KA-01" not in out["reason"] and out["reason"].startswith("Decidir a ordem de atendimento")
    assert out["reason"].endswith("KA-01 recebe 10 un. agora.") and ".." not in out["reason"]  # decision_text vem sem ponto final


def test_row1_insufficient_data_wins_over_everything():
    out = _lv("atraso_inevitavel", _ctx(uncovered_orders=[_order()], contested=True), status="insufficient_data")
    assert (out["code"], out["lever"], out["decide_by"]) == ("investigar", "nenhuma", None)
    assert _lv("investigar_dados", _ctx())["code"] == "investigar"


def test_row2_contested_uncovered_orders_become_priorizar_parceiro():
    ctx = _ctx(uncovered_orders=[_order("P1", "KA-02", "2026-09-10"), _order("P2", "KA-05", "2026-09-05")], contested=True, first_client="KA-02", last_client="KA-05",
               decision_text="Atender KA-02 (534 un.) integralmente; KA-05 recebe 10 un. agora", urgent_planned_quantity=50, next_urgent_release_date="2026-09-03")
    out = _lv("atraso_inevitavel", ctx)
    assert (out["code"], out["lever"], out["decide_by"]) == ("priorizar_parceiro", "alocar", "2026-09-05")
    assert "Atender KA-02 antes de KA-05" in out["reason"] and "534 un." in out["reason"] and out["requires_human_review"]
    overdue = _lv("atraso_inevitavel", _ctx(uncovered_orders=[_order(promised="2026-08-20")], contested=True, first_client="A", last_client="B"))
    assert overdue["decide_by"] == "2026-08-31" and "vencido" in overdue["decide_by_reason"]


def test_row3_anticipable_op_has_decide_by_reference():
    out = _lv("antecipar_op", _ctx(anticipable_ops=["OP-0007"]))
    assert (out["code"], out["lever"], out["decide_by"]) == ("priorizar_producao", "antecipar_op", "2026-08-31") and "Antecipar OP-0007" in out["reason"]
    assert _lv("atraso_inevitavel", _ctx(anticipable_ops=["OP-0009"]))["lever"] == "antecipar_op"


def test_row4_single_client_with_urgent_order_guarantees_and_renegotiates():
    out = _lv("atraso_inevitavel", _ctx(uncovered_orders=[_order("PED-9")], urgent_planned_quantity=120, next_urgent_release_date="2026-09-02"))
    assert (out["code"], out["lever"], out["decide_by"]) == ("priorizar_producao", "produzir_agora", "2026-09-02")
    assert "Garantir 120 un. e renegociar PED-9" in out["reason"]


def test_row5_no_production_lever_means_monitor_and_renegotiate():
    zero = _lv("atraso_inevitavel", _ctx(uncovered_orders=[_order("PED-3", promised="2026-09-12")]))
    assert (zero["code"], zero["lever"], zero["decide_by"]) == ("monitorar", "renegociar", "2026-09-12")
    assert zero["reason"].startswith("Renegociar PED-3: o estoque e a OP existentes não cobrem a data; sem nova produção")


def test_discontinued_never_becomes_priorizar_producao_or_produzir():
    cases = [
        ("atraso_inevitavel", _ctx(discontinued=True, uncovered_orders=[_order()], urgent_planned_quantity=80, next_urgent_release_date="2026-09-01")),
        ("atraso_inevitavel", _ctx(discontinued=True, forecast_only_shortfall=True, urgent_planned_quantity=80, first_shortfall_date="2026-09-20")),
        ("antecipar_op", _ctx(discontinued=True, anticipable_ops=["OP-1"], uncovered_orders=[_order()])),
        ("produzir", _ctx(discontinued=True, urgency_tier=1, urgent_planned_quantity=80, first_planned_release_date="2026-09-01")),
        ("produzir_validar_capacidade", _ctx(discontinued=True, urgency_tier=1)),
    ]
    for action, ctx in cases:
        assert _lv(action, ctx)["code"] not in ("priorizar_producao", "produzir"), (action, ctx)
    assert _lv("atraso_inevitavel", cases[0][1])["lever"] == "renegociar"


def test_row6_forecast_only_shortfall_says_estimated():
    with_order = _lv("atraso_inevitavel", _ctx(forecast_only_shortfall=True, urgent_planned_quantity=60, next_urgent_release_date="2026-09-04", first_shortfall_date="2026-09-20"))
    assert (with_order["code"], with_order["lever"], with_order["decide_by"]) == ("produzir", "produzir_agora", "2026-09-04")
    assert "estimada pela previsão" in with_order["reason"]
    without = _lv("atraso_inevitavel", _ctx(forecast_only_shortfall=True, first_shortfall_date="2026-09-20"))
    assert (without["code"], without["lever"], without["decide_by"]) == ("monitorar", "nenhuma", "2026-09-20") and "estimada pela previsão" in without["reason"]
    assert _lv("atraso_inevitavel", _ctx())["code"] == "monitorar"   # atraso sem pedido descoberto é falta só na previsão


def test_row7_rever_op_points_to_decision_window_end():
    out = _lv("rever_op", _ctx())
    assert (out["code"], out["lever"], out["decide_by"]) == ("investigar", "rever_op", "2026-09-28")


def test_row8_urgent_production_is_priorizar_producao_only_for_tier_1_or_event():
    tier1 = _lv("produzir", _ctx(urgency_tier=1, urgent_planned_quantity=50, next_urgent_release_date="2026-09-03"))
    assert (tier1["code"], tier1["lever"], tier1["decide_by"]) == ("priorizar_producao", "produzir_agora", "2026-09-03") and "urgency_tier_1" in tier1["signals_used"]
    tier2 = _lv("produzir", _ctx(urgency_tier=2, urgent_planned_quantity=50, next_urgent_release_date="2026-09-03", first_planned_release_date="2026-09-03"), priority=1)
    assert tier2["code"] == "produzir" and tier2["lever"] == "produzir_futuro"       # a posição na fila não promove mais
    event = _lv("produzir", _ctx(urgency_tier=3, first_planned_release_date="2026-10-01"), alerts=[_alert("2026-09-15")])
    assert (event["code"], event["lever"], event["decide_by"]) == ("priorizar_producao", "produzir_agora", "2026-09-15")
    assert any(s.startswith("event_decision:") for s in event["signals_used"]) and "Black Friday" in event["reason"]
    out_of_window = _lv("produzir", _ctx(urgency_tier=3, first_planned_release_date="2026-09-20"), alerts=[_alert("2026-12-15")])
    assert out_of_window["code"] == "produzir"


def test_row9_horizon_production_uses_first_planned_release():
    out = _lv("produzir_validar_capacidade", _ctx(first_planned_release_date="2026-09-21"))
    assert (out["code"], out["lever"], out["decide_by"]) == ("produzir", "produzir_futuro", "2026-09-21")
    assert _lv("produzir", _ctx(first_planned_release_date="2026-09-21"), alerts=None)["limitations"][-1].startswith("A análise de eventos")
    edge = _lv("produzir", _ctx(first_planned_release_date="2026-09-28"))   # liberação no último dia da janela ainda é decisão de agora
    assert edge["code"] == "produzir"


def test_row9_release_after_decision_window_is_monitorar_with_future_lever():
    out = _lv("produzir_validar_capacidade", _ctx(first_planned_release_date="2026-10-05"))
    assert (out["code"], out["lever"], out["decide_by"]) == ("monitorar", "produzir_futuro", "2026-10-05")
    assert out["decide_by_reason"] == "próxima ordem planejada a liberar em 05/10" and "próxima ordem planejada a liberar em 05/10" in out["reason"].lower()
    assert "PLANNED_RELEASE_AFTER_WINDOW" in out["signals_used"] and out["requires_human_review"]
    assert any(e["label"] == "Próxima liberação planejada" and e["value"] == "2026-10-05" for e in out["evidence"])
    assert _lv("produzir", _ctx(first_planned_release_date="2026-10-05", decision_window_end=None))["code"] == "produzir"   # sem janela: comportamento anterior


def test_rows10_and_11_have_no_lever():
    exc = _lv("monitorar_excesso", _ctx())
    assert (exc["code"], exc["lever"], exc["decide_by"]) == ("monitorar", "nenhuma", None)
    none = _lv("sem_acao_necessaria", _ctx())
    assert (none["code"], none["lever"], none["decide_by"]) == ("sem_acao_necessaria", "nenhuma", None)


def test_estimated_capacity_shortfall_adds_limitation_and_evidence_to_production_labels_only():
    ctx = _ctx(urgency_tier=1, next_urgent_release_date="2026-09-03", urgent_planned_quantity=10, capacity_status="insuficiente_estimado")
    prod = _lv("produzir", ctx)   # o status da recomendação (argumento) é outro; vale o da família no contexto
    assert "Não cabe nem na capacidade estimada" in prod["limitations"] and any(e["label"] == "Capacidade da família" for e in prod["evidence"])
    other = _lv("monitorar_excesso", _ctx(capacity_status="insuficiente_estimado"))
    assert "Não cabe nem na capacidade estimada" not in other["limitations"]
    only_argument = _lv("produzir", {**ctx, "capacity_status": "ok"}, capacity="insuficiente_estimado")
    assert "Não cabe nem na capacidade estimada" not in only_argument["limitations"]


def test_decide_by_present_whenever_lever_is_not_nenhuma():
    contexts = [
        ("atraso_inevitavel", _ctx(uncovered_orders=[_order()], contested=True, first_client="A", last_client="B")),
        ("antecipar_op", _ctx(anticipable_ops=["OP-1"])),
        ("atraso_inevitavel", _ctx(uncovered_orders=[_order()], urgent_planned_quantity=5, next_urgent_release_date="2026-09-02")),
        ("atraso_inevitavel", _ctx(uncovered_orders=[_order()])),
        ("atraso_inevitavel", _ctx(forecast_only_shortfall=True, urgent_planned_quantity=5, next_urgent_release_date="2026-09-02")),
        ("rever_op", _ctx()), ("produzir", _ctx(urgency_tier=1, next_urgent_release_date="2026-09-03")), ("produzir", _ctx(first_planned_release_date="2026-10-01")),
    ]
    for action, ctx in contexts:
        out = _lv(action, ctx)
        assert out["lever"] in LEVERS and out["lever"] != "nenhuma" and out["decide_by"], (action, out["lever"])
        assert out["requires_human_review"] and out["code"] in LABELS


def test_build_lever_context_reads_plan_and_allocation_without_recomputing():
    plan = {"discontinued": False, "affected_orders": [{"order": "P1", "client": "KA-01", "quantity": 100, "promised_date": "2026-09-10"}], "early_shortfall": True,
            "planned_orders": [{"quantity": 30, "release_date": "2026-09-08", "urgent": False}, {"quantity": 50, "release_date": "2026-09-02", "urgent": True}],
            "op_adjustments": [{"order": "OP-1", "adjustment": "antecipar"}, {"order": "OP-2", "adjustment": "reduzir"}],
            "first_shortfall_date": "2026-09-09", "decision_window_end": "2026-09-28"}
    alloc = {"contested": True, "decision_text": "texto", "first_client": "KA-01", "last_client": "KA-02",
             "orders": [_order("P1", "KA-01", "2026-09-10", 100, 40), _order("P2", "KA-02", "2026-09-11", 20, 0)]}
    ctx = build_lever_context(plan, alloc, {"tier": 1}, "ok", REF)
    assert [o["order"] for o in ctx["uncovered_orders"]] == ["P1"] and ctx["contested"] and ctx["urgency_tier"] == 1
    assert ctx["urgent_planned_quantity"] == 50 and ctx["next_urgent_release_date"] == "2026-09-02" and ctx["first_planned_release_date"] == "2026-09-02"
    assert ctx["anticipable_ops"] == ["OP-1"] and ctx["forecast_only_shortfall"] is False and ctx["reference_date"] == "2026-08-31"
    no_alloc = build_lever_context(plan, None, None, None, "2026-08-31")
    assert no_alloc["uncovered_orders"][0]["uncovered_at_promise"] is None and not no_alloc["contested"] and no_alloc["urgency_tier"] is None
    only_forecast = build_lever_context({**plan, "affected_orders": []}, {"orders": []}, None, None, REF)
    assert only_forecast["forecast_only_shortfall"] is True


def test_label_partner_allocation_first_labels_even_without_reposition_pairs():
    summary = {"code": "KA-02", "name": "Parceiro 02"}
    out = label_partner(summary, _partner_rows("A"), {"A": 40}, S, {"partner": "KA-02", "first_in_contested": ["CI-0041"]})
    assert out["code"] == "priorizar_parceiro" and "ALLOCATION_FIRST" in out["signals_used"] and "CI-0041" in out["reason"] and out["requires_human_review"]
    assert label_partner(summary, _partner_rows("A"), {"A": 40}, S, {"partner": "KA-02", "first_in_contested": []}) is None
    assert label_partner(summary, _partner_rows("A"), {"A": 40}, S) is None   # sem alocação: comportamento atual


def test_decisions_today_filters_by_decide_by_and_skips_no_lever():
    def item(sku, lever, decide_by):
        return {"sku": sku, "product": f"P-{sku}", "challenge_action": {"label": "L", "lever": lever, "decide_by": decide_by, "reason": "r"}}
    items = [item("B", "alocar", "2026-09-07"), item("A", "produzir_agora", "2026-08-31"), item("C", "renegociar", "2026-09-08"),
             item("D", "nenhuma", "2026-09-01"), item("E", None, None), item("F", "produzir_futuro", None), {"sku": "G", "product": "x", "challenge_action": None}]
    out = decisions_today(items, REF)
    assert out["window_end"] == "2026-09-07" and out["count"] == 2 and [i["sku"] for i in out["items"]] == ["A", "B"]
    assert out["items"][0] == {"sku": "A", "product": "P-A", "label": "L", "lever": "produzir_agora", "decide_by": "2026-08-31", "reason": "r"}
    assert decisions_today(items, REF, window_days=8)["count"] == 3
    assert out["requires_human_review"] is True and out["limitations"]


def test_repor_row_carries_forward_projection_as_estimated_evidence():
    forward = {"status": "ok", "days_until_stockout_without_replenishment": 22.3, "replenishment_to_target": 172.3, "sell_out_wape": 0.2642, "nature": "estimado"}
    label = label_commercial_row(_row("avaliar_reposicao", coverage_days=20, forward_projection=forward), DEFAULT_SETTINGS)
    values = {e["label"]: e["value"] for e in label["evidence"]}
    assert label["code"] == "repor"
    assert values["Dias até acabar sem reposição"] == 22.3
    assert values["Quantidade para 30 dias (estimada)"] == 172.3
    assert values["Erro medido do sell-out (WAPE)"] == "26%"
    bare = label_commercial_row(_row("avaliar_reposicao", coverage_days=20, forward_projection=None), DEFAULT_SETTINGS)
    assert "Dias até acabar sem reposição" not in {e["label"] for e in bare["evidence"]}


def test_ka_pair_with_backlog_and_no_sell_out_asks_for_sell_out():
    row = _row("dados_insuficientes", data_quality="insufficient", row_kind="partner", backlog_quantity=40, backlog_order_count=1,
               signals=[{"code": "INSUFFICIENT_PARTNER_DATA"}])
    label = label_commercial_row(row, DEFAULT_SETTINGS)
    assert label["code"] == "investigar" and "SELL_OUT_REQUEST" in label["signals_used"]
    assert "pedir ao parceiro o sell-out deste SKU" in label["reason"]
    no_backlog = label_commercial_row({**row, "backlog_quantity": 0}, DEFAULT_SETTINGS)
    assert "SELL_OUT_REQUEST" not in no_backlog["signals_used"]
