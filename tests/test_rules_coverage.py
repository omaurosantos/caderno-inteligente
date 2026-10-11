from collections import Counter

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.main as main
from backend.rules_coverage import create_rules_coverage_router
from caderno_inteligente.action_labels import LABELS, PRECEDENCE
from caderno_inteligente.direct_channels import build_direct_channels, load_direct_channel_settings
from caderno_inteligente.partner_insights import build_partner_insights, load_commercial_thresholds
from caderno_inteligente.rules_coverage import build_rules_coverage, sell_out_requests


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(create_rules_coverage_router(
        pipeline=main.pipeline, forecast_items=main.forecast_summaries,
        commercial=lambda: main._enrich_challenge(build_partner_insights(main.pipeline()[0], load_commercial_thresholds(main.COMMERCIAL_THRESHOLDS_FILE))),
        direct_channels=lambda: build_direct_channels(main.pipeline()[0], load_direct_channel_settings(main.ROOT / "config/direct_channel_thresholds.json")),
        describe_error=main._describe_error))
    return TestClient(app)


@pytest.fixture(scope="module")
def payload(client):
    response = client.get("/api/rules/coverage")
    assert response.status_code == 200
    return response.json()


def test_lists_eleven_operational_rules_and_every_label(payload):
    operational = [rule for rule in payload["rules"] if rule["kind"] == "operational"]
    labels = [rule for rule in payload["rules"] if rule["kind"] == "label"]
    assert len(operational) == 11
    assert [rule["rule"] for rule in labels] == list(LABELS)
    assert payload["requires_human_review"] is True
    assert len(payload["precedence"]) == sum(len(lines) for lines in PRECEDENCE.values())
    assert all(item["code"] in LABELS for item in payload["precedence"])


def test_operational_fires_match_distinct_skus_in_issues(payload):
    issues = main.pipeline()[3]
    expected = issues.groupby("code")["sku"].nunique().to_dict()
    for rule in payload["rules"]:
        if rule["kind"] == "operational":
            assert rule["fires"] == expected.get(rule["rule"], 0), rule["rule"]


def test_label_fires_match_real_outputs(payload):
    skus = Counter(item["challenge_action"]["code"] for item in main.forecast_summaries())
    commercial = main._enrich_challenge(build_partner_insights(main.pipeline()[0], load_commercial_thresholds(main.COMMERCIAL_THRESHOLDS_FILE)))
    rows = Counter(row["challenge_action"]["code"] for row in commercial["items"])
    partners = Counter(partner["challenge_action"]["code"] for partner in commercial["partners"] if partner.get("challenge_action"))
    channels = Counter(row["suggestion"]["code"] for rows_ in build_direct_channels(main.pipeline()[0], load_direct_channel_settings(main.ROOT / "config/direct_channel_thresholds.json"))["rows"].values() for row in rows_)
    mapped = Counter()
    for code, count in channels.items():
        mapped[{"avaliar_ampliacao_mix": "ampliar_mix", "avaliar_reativacao": "reativar", "investigar_queda": "investigar",
                "monitorar_saida_de_linha": "monitorar", "acompanhar_crescimento": "monitorar", "sem_acao_necessaria": "sem_acao_necessaria"}[code]] += count
    for rule in payload["rules"]:
        if rule["kind"] != "label":
            continue
        code = rule["rule"]
        assert rule["fires_by_level"] == {"sku": skus[code], "commercial": rows[code], "partner": partners[code], "channel": mapped[code]}, code
        assert rule["fires"] == skus[code] + rows[code] + partners[code] + mapped[code]


def test_zero_fire_rules_have_numbered_reason_and_reference_case(payload):
    zero = [rule for rule in payload["rules"] if rule["fires"] == 0]
    assert {"ampliar_mix", "recomendar_recompra", "reativar"} <= {rule["rule"] for rule in zero}
    for rule in zero:
        assert rule["zero_reason"] and rule["data_needed"], rule["rule"]
    by_code = {rule["rule"]: rule for rule in zero}
    for code, case in (("ampliar_mix", "VC-14"), ("recomendar_recompra", "VC-15"), ("reativar", "VC-16")):
        assert by_code[code]["reference_case"]["case"] == case
        assert by_code[code]["evidence_number"] is not None and by_code[code]["evidence_number"] > 0
        assert any(char.isdigit() for char in by_code[code]["zero_reason"])
    assert "sem lacunas" in by_code["ampliar_mix"]["zero_reason"]
    assert "contínuo" in by_code["recomendar_recompra"]["zero_reason"]
    for rule in payload["rules"]:
        if rule["fires"]:
            assert rule["zero_reason"] is None and rule["reference_case"] is None


def test_sell_out_requests_are_the_23_ka_pairs_ordered_by_value(payload):
    requests = payload["sell_out_requests"]
    assert len(requests) == 23
    assert len({(item["partner"], item["sku"]) for item in requests}) == 23
    assert all(item["partner"].startswith("KA-") and item["backlog_quantity"] > 0 and item["orders"] for item in requests)
    values = [item["backlog_value"] for item in requests]
    assert None not in values and values == sorted(values, reverse=True)


def test_sell_out_requests_ignore_sufficient_direct_and_no_backlog_rows():
    rows = [
        {"row_kind": "partner", "action": "dados_insuficientes", "partner": "KA-1", "sku": "A", "backlog_quantity": 10, "orders": [{"order": "P1"}]},
        {"row_kind": "partner", "action": "dados_insuficientes", "partner": "KA-2", "sku": "A", "backlog_quantity": None, "orders": []},
        {"row_kind": "partner", "action": "avaliar_reposicao", "partner": "KA-3", "sku": "A", "backlog_quantity": 5, "orders": []},
        {"row_kind": "direct", "action": "dados_insuficientes", "partner": "E-commerce", "sku": "A", "backlog_quantity": 5, "orders": []},
    ]
    result = sell_out_requests(rows, {})
    assert [(item["partner"], item["backlog_value"]) for item in result] == [("KA-1", None)]


def test_missing_price_keeps_value_null_and_sorts_last():
    rows = [{"row_kind": "partner", "action": "dados_insuficientes", "partner": "KA-1", "sku": "SEM", "backlog_quantity": 10, "orders": []},
            {"row_kind": "partner", "action": "dados_insuficientes", "partner": "KA-2", "sku": "A", "backlog_quantity": 1, "orders": []}]
    prices = pd.DataFrame({"SKU": ["A"], "Preço unitário (R$)": [3.0], "Vigência fictícia": ["2026-01-01"]})
    result = sell_out_requests(rows, {"Precos_Produtos": prices})
    assert [(item["partner"], item["backlog_value"]) for item in result] == [("KA-2", 3.0), ("KA-1", None)]


def test_empty_inputs_do_not_turn_into_numbers():
    result = build_rules_coverage([], [], {"items": [], "partners": []}, {"rows": {}}, {})
    zero = {rule["rule"]: rule for rule in result["rules"] if rule["kind"] == "label"}
    assert zero["ampliar_mix"]["evidence_number"] is None and "sem base" in zero["ampliar_mix"]["zero_reason"]
    assert result["sell_out_requests"] == []


def test_recompra_zero_reason_reads_sell_in_by_column_name():
    from caderno_inteligente.rules_coverage import _zero_reason
    # colunas fora da ordem da planilha: o motivo precisa ler Mês, Cliente e SKU pelo nome
    sell_in = pd.DataFrame({"Quantidade enviada": [5, 5, 5], "SKU": ["A", "A", "B"], "Cliente": ["KA-1", "KA-1", "KA-1"],
                            "Mês": ["2026-01-01", "2026-02-01", "2026-02-01"]})
    text, number = _zero_reason("recomendar_recompra", [], {"Sell_In": sell_in})
    assert number == 1.0 and "1 de 2 pares" in text and "2 de 2 meses" in text
    text, number = _zero_reason("recomendar_recompra", [], {"Sell_In": sell_in.drop(columns=["Cliente"])})
    assert number is None and "sem base" in text

def test_recompra_reason_reads_sell_in_by_column_name_not_position():
    from caderno_inteligente.rules_coverage import _zero_reason
    sell_in = pd.DataFrame({"Mês": ["2026-01", "2026-02", "2026-01", "2026-02"], "Cliente": ["KA-1", "KA-1", "KA-2", "KA-2"],
                            "SKU": ["S1", "S1", "S1", "S1"], "Quantidade enviada": [1, 2, 3, 4]})
    shuffled = sell_in[["SKU", "Quantidade enviada", "Cliente", "Mês"]]
    assert _zero_reason("recomendar_recompra", [], {"Sell_In": sell_in}) == _zero_reason("recomendar_recompra", [], {"Sell_In": shuffled})
    assert _zero_reason("recomendar_recompra", [], {"Sell_In": shuffled})[1] == 2.0
