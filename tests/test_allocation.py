"""Etapa 16.2: alocação sugerida do produto escasso entre pedidos confirmados."""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

import pandas as pd
import pytest

import backend.main as main
from caderno_inteligente.allocation import (
    DEFAULT_SETTINGS,
    LIMITATION,
    _validate_settings,
    allocate_sku,
    build_allocation,
    load_allocation_settings,
    score_order,
)
from caderno_inteligente.partner_insights import build_partner_insights, load_commercial_thresholds

REFERENCE = date(2026, 9, 14)
SETTINGS = _validate_settings(json.loads(json.dumps(DEFAULT_SETTINGS)))
PARTNERS = pd.DataFrame([
    {"Código": "KA-01", "Tipo": "Parceiro varejista", "Região": "Sudeste"},
    {"Código": "KA-02", "Tipo": "Parceiro varejista", "Região": "Sul"},
    {"Código": "KA-T1", "Tipo": "Parceiro varejista", "Região": "Sul"},
    {"Código": "KA-T2", "Tipo": "Parceiro varejista", "Região": "Nordeste"},
    {"Código": "E-commerce", "Tipo": "Canal direto", "Região": "Nacional"},
])


def _iso(offset: int) -> str:
    return (REFERENCE + timedelta(days=offset)).isoformat()


def _plan(events, orders, affected=None):
    plan = {"reference_date": REFERENCE.isoformat(),
            "supply_events": [{"date": _iso(day), "quantity": float(qty), "source": source, "ref": ref} for day, qty, source, ref in events],
            "open_orders": [{"order": name, "client": client, "quantity": float(qty), "promised_date": None if day is None else _iso(day)}
                            for name, client, qty, day in orders]}
    if affected is not None:
        plan["affected_orders"] = affected
    return plan


def _settings(**weights):
    values = json.loads(json.dumps(DEFAULT_SETTINGS))
    values["weights"].update(weights)
    return _validate_settings(values)


def _partner(partner, sku, quality="sufficient", coverage=None, signals=()):
    return {"partner": partner, "sku": sku, "data_quality": quality, "coverage_days": coverage, "signals": [{"code": code} for code in signals]}


# ------------------------------------------------------------------------------------------ configuração


def test_settings_come_from_the_config_with_strict_keys(tmp_path):
    loaded = load_allocation_settings()
    assert loaded["weights"]["partner_buildup_or_high_coverage"] == -3 and loaded["allow_partial"] is True
    for bad in ({"unknown": 1}, {"weights": {"revenue": 1}}, {"allow_partial": "sim"}, {"low_coverage_days": 90, "high_coverage_days": 30}):
        path = tmp_path / "allocation.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            load_allocation_settings(path)


# ------------------------------------------------------------------------------------------ pontuação


def test_pair_without_sell_out_never_gets_coverage_points():
    order = {"order": "P1", "client": "KA-01", "quantity": 100.0, "promised_date": _iso(10), "max_quantity": 100.0}
    meta = {"Tipo": "Parceiro varejista"}
    for row in (None, _partner("KA-01", "X", "insufficient", 5.0, ["PARTNER_STOCK_BUILDUP"]), _partner("KA-01", "X", "stale", 200.0),
                _partner("KA-01", "X", "sufficient", None)):
        _, components = score_order(order, meta, row, SETTINGS, REFERENCE)
        names = {item["component"] for item in components}
        assert not names & {"cobertura_baixa_parceiro", "estoque_acumulando_parceiro"}
        missing = next(item for item in components if item["component"] == "sem_sell_out")
        assert missing["points"] == 0 and missing["nature"] == "ausente" and "sem dado do parceiro" in missing["reason"].lower()


def test_components_follow_the_documented_weights():
    order = {"order": "P1", "client": "KA-01", "quantity": 50.0, "promised_date": _iso(15), "max_quantity": 200.0}
    score, components = score_order(order, {"Tipo": "Parceiro varejista"}, _partner("KA-01", "X", coverage=20.0), SETTINGS, REFERENCE)
    points = {item["component"]: item["points"] for item in components}
    assert points == {"urgencia": 1.5, "canal_direto": 0.0, "cobertura_baixa_parceiro": 2.0, "estoque_acumulando_parceiro": 0.0, "pedido_pequeno": 0.75}
    assert score == pytest.approx(4.25)
    direct, _ = score_order({**order, "promised_date": _iso(-3)}, {"Tipo": "Canal direto"}, None, SETTINGS, REFERENCE)
    assert direct == pytest.approx(3 + 2 + 0.75)  # vencido pontua a urgência inteira; canal direto não tem par de sell-out


# ------------------------------------------------------------------------------------------ alocação


def _scored(plan, settings=SETTINGS, partner_rows=None):
    registry = {row["Código"]: row for row in PARTNERS.to_dict("records")}
    largest = max(order["quantity"] for order in plan["open_orders"])
    result = []
    for order in plan["open_orders"]:
        score, components = score_order({**order, "max_quantity": largest}, registry.get(order["client"]), (partner_rows or {}).get(order["client"]), settings, REFERENCE)
        result.append({**order, "allocation_score": score, "score_components": components})
    return result


def test_allocated_quantity_never_exceeds_cumulative_supply_on_any_date():
    rng = random.Random(16)
    for case in range(300):
        events = [(rng.randint(0, 60), rng.randint(1, 400), "op", f"OP-{i}") for i in range(rng.randint(0, 5))]
        if rng.random() < .8:
            events.append((0, rng.randint(1, 500), "estoque", None))
        events.sort()
        orders = [(f"P{i}", rng.choice(["KA-01", "KA-02", "E-commerce"]), rng.randint(1, 500), rng.choice([None, *range(-10, 70)])) for i in range(rng.randint(1, 6))]
        plan = _plan(events, orders)
        allow_partial = case % 2 == 0
        rows = allocate_sku(plan, _scored(plan), allow_partial)
        assert {row["order"] for row in rows} == {name for name, _, _, day in orders if day is not None}  # sem data: fora
        supply_dates = sorted({day for day, *_ in events} | {day for *_, day in orders if day is not None} | {0, 90})
        for offset in supply_dates:
            limit = REFERENCE + timedelta(days=offset)
            supply = sum(qty for day, qty, *_ in events if REFERENCE + timedelta(days=day) <= limit)
            allocated = 0.0
            for row in rows:
                if max(date.fromisoformat(row["promised_date"]), REFERENCE) <= limit:
                    allocated += row["allocated_now"]
                allocated += sum(part["quantity"] for part in row["allocated_later"] if date.fromisoformat(part["expected_date"]) <= limit)
            assert allocated <= supply + 1e-6, (case, offset)
        for row in rows:
            delivered = row["allocated_now"] + sum(part["quantity"] for part in row["allocated_later"])
            assert delivered <= row["quantity"] + 1e-6
            assert row["uncovered_at_promise"] == pytest.approx(row["quantity"] - row["allocated_now"])
            assert (row["expected_date"] is None) == (delivered < row["quantity"] - 1e-6)
            if not allow_partial:
                assert row["allocated_now"] in (0.0, row["quantity"])


def test_order_with_later_date_takes_the_latest_arrival_and_keeps_early_stock_for_the_others():
    plan = _plan([(0, 100, "estoque", None), (10, 100, "op", "OP-1")], [("A", "E-commerce", 100, 10), ("B", "KA-01", 100, 0)])
    rows = {row["order"]: row for row in allocate_sku(plan, _scored(plan), True)}
    assert rows["A"]["rank"] == 1 and rows["A"]["uncovered_at_promise"] == 0 and rows["B"]["uncovered_at_promise"] == 0


def test_without_partial_an_order_that_does_not_fit_waits_for_the_next_arrival():
    plan = _plan([(0, 60, "estoque", None), (12, 200, "op", "OP-9")], [("A", "KA-01", 100, 0)])
    partial = allocate_sku(plan, _scored(plan), True)[0]
    whole = allocate_sku(plan, _scored(plan), False)[0]
    assert partial["allocated_now"] == 60 and partial["allocated_later"][0]["quantity"] == 40
    assert whole["allocated_now"] == 0 and whole["allocated_later"] == [{"quantity": 100.0, "expected_date": _iso(12), "source_ref": "OP-9", "source": "op"}]
    assert whole["expected_date"] == _iso(12) and whole["delay_days"] == 12


def test_raising_the_urgency_weight_moves_the_overdue_order_ahead():
    plan = _plan([(0, 100, "estoque", None)], [("ATRASADO", "KA-01", 100, -2), ("DIRETO", "E-commerce", 50, 20)])
    first = lambda settings: allocate_sku(plan, _scored(plan, settings), True)[0]["order"]  # noqa: E731
    assert first(_settings(urgency=3)) == "DIRETO"  # 3 contra 1 + 2 + 0,5
    assert first(_settings(urgency=6)) == "ATRASADO"  # 6 contra 2 + 2 + 0,5
    assert first(_settings(urgency=3, direct_channel=0)) == "ATRASADO"


def test_vc34_partner_with_stock_buildup_is_served_last():
    plan = _plan([(0, 100, "estoque", None)], [("PED-T1", "KA-T1", 100, 57), ("PED-T2", "KA-T2", 100, 57)])
    items = [_partner("KA-T1", "SINT-VC34", coverage=120.0, signals=["PARTNER_STOCK_BUILDUP"])]
    result = build_allocation({"SINT-VC34": plan}, PARTNERS, items, {"SINT-VC34": 10.0}, SETTINGS, REFERENCE.isoformat())
    sku = result["skus"]["SINT-VC34"]
    assert sku["first_client"] == "KA-T2" and sku["last_client"] == "KA-T1"
    assert sku["has_shortfall"] and sku["orders"][1]["uncovered_at_promise"] == 100
    assert "estoque acumulando" in sku["orders"][1]["reason"]
    assert result["requires_human_review"] is True and LIMITATION in result["limitations"]


def test_direct_channel_is_not_counted_as_partner_sell_out_in_the_data_note():
    plan = _plan([(0, 50, "estoque", None)], [("D1", "E-commerce", 40, 1), ("K1", "KA-01", 40, 2), ("K2", "KA-02", 40, 3)])
    # o par do canal direto vem "sufficient" (row_kind direct), mas não há cobertura no parceiro a pontuar
    items = [{**_partner("E-commerce", "S", coverage=None), "row_kind": "direct"}, _partner("KA-01", "S", coverage=60.0)]
    sku = build_allocation({"S": plan}, PARTNERS, items, {"S": 1.0}, SETTINGS, REFERENCE.isoformat())["skus"]["S"]
    assert sku["orders_with_partner_data"] == 1 and sku["data_note"].startswith("1 de 3 pedidos têm sell-out suficiente do parceiro")


def test_first_and_last_client_are_distinct_and_decision_text_has_no_final_period():
    # o mesmo cliente com dois pedidos no começo e no fim da fila: primeiro e último são clientes distintos
    plan = _plan([(0, 60, "estoque", None)], [("A1", "KA-01", 30, 0), ("B1", "KA-02", 30, 30), ("A2", "KA-01", 30, 60)])
    sku = build_allocation({"S": plan}, PARTNERS, [], {"S": 1.0}, SETTINGS, REFERENCE.isoformat())["skus"]["S"]
    assert [row["client"] for row in sku["orders"]][0] == "KA-01" and sku["first_client"] != sku["last_client"]
    assert {sku["first_client"], sku["last_client"]} == {"KA-01", "KA-02"} and sku["clients"] == [sku["first_client"], sku["last_client"]]
    single = _plan([(0, 10, "estoque", None)], [("A1", "KA-01", 30, 0), ("A2", "KA-01", 30, 5)])
    only = build_allocation({"S": single}, PARTNERS, [], {"S": 1.0}, SETTINGS, REFERENCE.isoformat())["skus"]["S"]
    assert only["first_client"] == "KA-01" and only["last_client"] is None
    covered = _plan([(0, 100, "estoque", None)], [("A1", "KA-01", 30, 0)], affected=[])
    texts = [sku["decision_text"], only["decision_text"],
             build_allocation({"S": covered}, PARTNERS, [], {"S": 1.0}, SETTINGS, REFERENCE.isoformat())["skus"]["S"]["decision_text"]]
    assert all(text and not text.endswith(".") for text in texts), texts


def test_regions_and_partners_add_up_to_the_total_uncovered():
    plans = {
        "A": _plan([(0, 100, "estoque", None)], [("A1", "KA-01", 80, 1), ("A2", "KA-02", 80, 2), ("A3", "E-commerce", 40, 3)]),
        "B": _plan([(5, 50, "op", "OP-1")], [("B1", "KA-02", 120, 0)]),
        "C": _plan([], [("C1", "KA-01", 30, 4)]),
    }
    result = build_allocation(plans, PARTNERS, [], {"A": 10.0, "B": 20.0, "C": None}, SETTINGS, REFERENCE.isoformat())
    totals = result["totals"]
    assert totals["uncovered_units"] == pytest.approx(100 + 120 + 30)
    assert sum(row["uncovered_units"] for row in result["regions"]) == pytest.approx(totals["uncovered_units"])
    assert sum(row["uncovered_units"] for row in result["partners"]) == pytest.approx(totals["uncovered_units"])
    assert totals["uncovered_value"] is None  # C sem preço: valor indisponível, não zero
    assert result["skus"]["C"]["uncovered_value_at_promise"] is None and result["skus"]["B"]["uncovered_value_at_promise"] == pytest.approx(2400)
    assert any("Sem preço vigente para C" in text for text in result["limitations"])
    assert {row["region"] for row in result["regions"]} == {"Sudeste", "Sul"}  # o canal direto foi atendido primeiro


# ------------------------------------------------------------------------------------------ base real


@pytest.fixture(scope="module")
def real():
    (dataset, *_), plans = main._cached()[1], main._cached()[2]
    items = build_partner_insights(dataset, load_commercial_thresholds(main.ROOT / "config/commercial_thresholds.json"))["items"]
    prices = dataset["Precos_Produtos"].sort_values("Vigência fictícia").groupby("SKU")["Preço unitário (R$)"].last().to_dict()
    return plans, build_allocation(plans, dataset["Parceiros_Canais"], items, prices, load_allocation_settings(), "2026-09-14")


def test_real_base_contested_skus_have_an_ordered_answer_with_reasons(real):
    plans, result = real
    assert result["totals"]["contested_skus"] == ["CI-0004", "CI-0005", "CI-0027", "CI-0041", "CI-0049"]
    assert sorted(result["totals"]["shortfall_skus"]) == sorted(sku for sku, plan in plans.items() if plan["affected_orders"])
    for sku in result["totals"]["contested_skus"]:
        item = result["skus"][sku]
        assert len(set(item["clients"])) >= 2 and item["decision_text"] and item["data_note"]
        assert [row["rank"] for row in item["orders"]] == list(range(1, len(item["orders"]) + 1))
        assert all(row["reason"] and row["score_components"] for row in item["orders"])
    assert {"KA-02", "KA-05"} <= set(result["skus"]["CI-0041"]["clients"])  # VC-33


def test_real_base_regions_match_the_total_and_missing_sell_out_never_scores(real):
    _, result = real
    assert sum(row["uncovered_units"] for row in result["regions"]) == pytest.approx(result["totals"]["uncovered_units"])
    if result["totals"]["uncovered_value"] is not None:
        assert sum(row["uncovered_value"] for row in result["regions"]) == pytest.approx(result["totals"]["uncovered_value"])
    for item in result["skus"].values():
        for row in item["orders"]:
            names = {part["component"] for part in row["score_components"]}
            assert not ("sem_sell_out" in names and names & {"cobertura_baixa_parceiro", "estoque_acumulando_parceiro"})
    assert result["requires_human_review"] is True and LIMITATION in result["limitations"]
