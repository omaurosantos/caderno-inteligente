"""Etapa 15.4: capacidade semanal finita por linha."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.main as main
from caderno_inteligente.capacity_plan import build_capacity_plan


def _capacity(available: dict[str, float], family: str = "Escolar") -> pd.DataFrame:
    return pd.DataFrame([{"Semana inicial": pd.Timestamp(week), "Linha": f"Linha {family}", "Família": family, "Capacidade máxima": 1000.0,
                          "Capacidade disponível": value, "Ocupação": 0.9} for week, value in available.items()])


def _plans(*orders, sku="X"):
    return {sku: {"planned_orders": [{"due_date": due, "release_date": release, "quantity": float(quantity), "urgent": urgent}
                                     for due, release, quantity, urgent in orders]}}


INDICATORS = pd.DataFrame([{"SKU": "X", "family": "Escolar", "abc_curve": "A"}, {"SKU": "Y", "family": "Escolar", "abc_curve": "B"}])
WEEKS = {"2026-09-14": 300.0, "2026-09-21": 300.0, "2026-09-28": 300.0}


def _run(plans, available=WEEKS, orders=None):
    return build_capacity_plan(plans, INDICATORS, _capacity(available), orders, "2026-09-14", [1])


def test_order_that_fits_in_its_release_week_is_ok():
    result = _run(_plans(("2026-10-10", "2026-09-28", 200, False)))
    order = result["skus"]["X"]["orders"][0]
    assert order["status"] == "ok" and order["allocations"] == [{"week_start": "2026-09-28", "quantity": 200.0}]
    week = next(item for item in result["families"][0]["weeks"] if item["week_start"] == "2026-09-28")
    assert week["allocated"] == 200 and week["remaining"] == 100


def test_order_larger_than_its_week_uses_earlier_weeks_as_pre_production():
    order = _run(_plans(("2026-10-10", "2026-09-28", 500, False)))["skus"]["X"]["orders"][0]
    assert order["status"] == "pre_producao" and [item["week_start"] for item in order["allocations"]] == ["2026-09-28", "2026-09-21"]


def test_what_does_not_fit_before_the_need_is_unscheduled_and_never_moved_later():
    result = _run(_plans(("2026-09-30", "2026-09-21", 800, True)))
    order = result["skus"]["X"]["orders"][0]
    assert order["status"] == "insuficiente" and order["unscheduled"] == 200  # só 14/09 e 21/09 servem
    assert all(item["week_start"] <= "2026-09-21" for item in order["allocations"])
    assert result["skus"]["X"]["status_now"] == "insuficiente" and result["families"][0]["first_shortfall_due"] == "2026-09-30"


def test_release_after_the_calendar_is_to_be_confirmed_not_ok_nor_short():
    order = _run(_plans(("2026-11-20", "2026-11-02", 100, False)))["skus"]["X"]["orders"][0]
    assert order["status"] == "a_confirmar" and order["allocations"] == []


def test_earlier_need_is_served_first_and_allocated_never_exceeds_available():
    plans = {**_plans(("2026-10-20", "2026-09-28", 600, False), sku="Y"), **_plans(("2026-10-05", "2026-09-21", 600, True), sku="X")}
    result = _run(plans)
    assert result["skus"]["X"]["orders"][0]["status"] == "pre_producao"
    assert result["skus"]["Y"]["orders"][0]["status"] == "insuficiente"
    for week in result["families"][0]["weeks"]:
        assert 0 <= week["allocated"] <= week["available"] and week["remaining"] >= 0


def test_family_summary_lists_short_skus_affected_orders_and_peak():
    orders = pd.DataFrame([{"Pedido": "PED-1", "SKU": "X", "Cliente/Canal": "KA-01", "Quantidade": 50.0}])
    result = _run(_plans(("2027-01-10", "2026-09-28", 2000, False)), orders=orders)
    family = result["families"][0]
    assert family["status"] == "insuficiente" and family["skus_short"] == ["X"]
    assert family["affected_orders"] == [{"order": "PED-1", "sku": "X", "client": "KA-01", "quantity": 50.0}]
    assert family["peak_need_units"] == 2000 and family["peak_status"] == "insuficiente"
    assert family["available_until_calendar_end"] == 900


# ------------------------------------------------------------------------------------ Etapa 16.5: capacidade estimada

OFF = {"enabled": False, "method": "media_compromissos_8_semanas", "scenario": "central", "lookback_weeks": 8, "conservative_method": "minimo_disponivel_observado"}
ON = {**OFF, "enabled": True}


def _capacity_with_base(available: dict[str, float], base: float = 700.0) -> pd.DataFrame:
    frame = _capacity(available)
    frame["Compromissos base"] = base
    return frame


def _run_extension(plans, extension, capacity=None):
    return build_capacity_plan(plans, INDICATORS, _capacity_with_base(WEEKS) if capacity is None else capacity, None, "2026-09-14", [1], extension)


def test_extension_off_reproduces_the_previous_output_exactly():
    plans = _plans(("2026-10-10", "2026-09-28", 500, False), ("2026-11-20", "2026-11-02", 100, False))
    result = _run_extension(plans, OFF)
    assert result["assumptions"][3].startswith("Não há capacidade informada depois da última semana")
    assert set(result["status_labels"]) == {"ok", "pre_producao", "a_confirmar", "insuficiente"}
    assert result["skus"] == {"X": {
        "executable_quantity_now": 0, "family": "Escolar", "status": "a_confirmar", "status_label": "Capacidade a confirmar (fora do calendário)",
        "status_now": "sem_ordens", "unscheduled_quantity": 0.0,
        "orders": [{"allocations": [{"quantity": 300.0, "week_start": "2026-09-28"}, {"quantity": 200.0, "week_start": "2026-09-21"}], "due_date": "2026-10-10",
                    "family": "Escolar", "index": 0, "quantity": 500.0, "release_date": "2026-09-28", "status": "pre_producao", "unscheduled": 0.0},
                   {"allocations": [], "due_date": "2026-11-20", "family": "Escolar", "index": 1, "quantity": 100.0, "release_date": "2026-11-02",
                    "status": "a_confirmar", "unscheduled": 0.0}]}}
    family = result["families"][0]
    assert family["weeks"] == [
        {"allocated": 0.0, "available": 300.0, "maximum": 1000.0, "occupation_base": 0.9, "remaining": 300.0, "week_start": "2026-09-14"},
        {"allocated": 200.0, "available": 300.0, "maximum": 1000.0, "occupation_base": 0.9, "remaining": 100.0, "week_start": "2026-09-21"},
        {"allocated": 300.0, "available": 300.0, "maximum": 1000.0, "occupation_base": 0.9, "remaining": 0.0, "week_start": "2026-09-28"}]
    assert {"estimated_from", "scenarios", "planned_in_estimated"}.isdisjoint(family) and family["planned_after_calendar"] == 100.0


def test_estimated_weeks_carry_nature_and_method_and_nothing_stays_to_be_confirmed():
    result = _run_extension(_plans(("2026-11-20", "2026-11-02", 100, False)), ON)
    order = result["skus"]["X"]["orders"][0]
    assert order["status"] == "ok_estimado" and order["allocations"] == [{"week_start": "2026-11-02", "quantity": 100.0, "nature": "estimada"}]
    family = result["families"][0]
    assert family["estimated_from"] == "2026-10-05" and family["planned_after_calendar"] == 0
    observed = [week for week in family["weeks"] if week["nature"] == "observada"]
    estimated = [week for week in family["weeks"] if week["nature"] == "estimada"]
    assert len(observed) == 3 and all(week["method"] is None for week in observed)
    assert estimated[0]["week_start"] == "2026-10-05" and estimated[-1]["week_start"] == "2026-11-02"
    assert all(week["method"] == "media_compromissos_8_semanas" and week["occupation_base"] is None for week in estimated)
    assert all(week["available"] == 300.0 for week in estimated)  # máxima 1000 − média dos compromissos base 700
    assert result["status_labels"]["ok_estimado"] == "Cabe na capacidade estimada" and "estimadas" in result["assumptions"][3]


def test_extension_block_and_assumption_follow_lookback_weeks():
    result = _run_extension(_plans(("2026-11-20", "2026-11-02", 100, False)), {**ON, "lookback_weeks": 2})
    assert result["extension"] == {"enabled": True, "method": "media_compromissos_8_semanas", "lookback_weeks": 2, "scenario": "central"}
    assert "últimas 2 semanas" in result["assumptions"][3] and "últimas 2 semanas" in result["field_nature"]["estimated_available"]["origin"]
    assert _run_extension(_plans(("2026-11-20", "2026-11-02", 100, False)), OFF)["extension"]["enabled"] is False


def test_capacity_module_defines_each_constant_once():
    import inspect

    from caderno_inteligente import capacity_plan
    source = inspect.getsource(capacity_plan)
    for name in ("ESTIMATED_LABELS =", "EXTENSION_PATH =", "EXTENSION_KEYS =", "CENTRAL_METHODS =", "CONSERVATIVE_METHODS =", "SCENARIOS =",
                 "ESTIMATED_ASSUMPTION =", "def load_capacity_extension(", "def _validate_extension("):
        assert source.count("\n" + name) == 1, name


def test_peak_after_the_calendar_that_does_not_fit_is_insufficient_even_when_estimated():
    result = _run_extension(_plans(("2027-01-20", "2027-01-04", 20000, False)), ON)
    order = result["skus"]["X"]["orders"][0]
    assert order["status"] == "insuficiente_estimado" and order["unscheduled"] > 0
    family = result["families"][0]
    assert family["peak_status"] == "insuficiente_estimado" and family["unscheduled_quantity"] > 0 and family["skus_short"] == ["X"]
    assert family["scenarios"]["central"]["peak_status"] == family["scenarios"]["conservador"]["peak_status"] == "insuficiente_estimado"
    assert family["scenarios"]["conservador"]["unscheduled_quantity"] >= family["scenarios"]["central"]["unscheduled_quantity"] > 0
    assert result["skus"]["X"]["status"] != "insuficiente"  # só o sinal observado gera CAPACITY_SHORTFALL


def test_conservative_scenario_uses_the_lowest_observed_availability():
    result = _run_extension(_plans(("2026-11-20", "2026-11-02", 100, False)), {**ON, "scenario": "conservador"},
                            _capacity_with_base({"2026-09-14": 300.0, "2026-09-21": 200.0, "2026-09-28": 300.0}))
    estimated = [week for week in result["families"][0]["weeks"] if week["nature"] == "estimada"]
    assert all(week["available"] == 200.0 and week["method"] == "minimo_disponivel_observado" for week in estimated)


def test_without_commitments_column_the_estimate_is_unavailable_and_behaviour_is_kept():
    result = _run(_plans(("2026-11-20", "2026-11-02", 100, False)))  # fixture sem "Compromissos base", extensão padrão ligada
    assert result["skus"]["X"]["orders"][0]["status"] == "a_confirmar" and "scenarios" not in result["families"][0]
    assert any("Capacidade estimada indisponível" in item for item in result["assumptions"])


def test_extension_config_is_strict():
    from caderno_inteligente.capacity_plan import load_capacity_extension
    assert load_capacity_extension()["scenario"] in {"central", "conservador"}
    for bad in ({**OFF, "extra": 1}, {key: value for key, value in OFF.items() if key != "method"}, {**OFF, "lookback_weeks": 0},
                {**OFF, "enabled": "sim"}, {**OFF, "scenario": "otimista"}, {**OFF, "method": "inventado"}):
        with pytest.raises(ValueError):
            build_capacity_plan({}, INDICATORS, _capacity(WEEKS), None, "2026-09-14", [1], bad)


# ------------------------------------------------------------------------------------------ base real


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def test_escolar_line_cannot_absorb_back_to_school(client):
    body = client.get("/api/capacity-plan").json()
    escolar = next(family for family in body["families"] if family["family"] == "Escolar")
    assert escolar["available_until_calendar_end"] == 12960 and escolar["status"] == "insuficiente"
    assert escolar["peak_status"] == "insuficiente" and escolar["unscheduled_quantity"] > 0
    assert {"CI-0014", "CI-0041"} <= set(escolar["skus_short"])
    for family in body["families"]:
        for week in family["weeks"]:
            assert week["allocated"] <= week["available"] + 1e-6
    assert body["requires_human_review"] is True and body["assumptions"]


def test_capacity_rule_replaces_the_average_occupation_rule(client):
    detail = client.get("/api/priorities/CI-0014").json()
    codes = {item["code"] for item in detail["issues"]}
    assert "CAPACITY_SHORTFALL" in codes and "CAPACITY_CONFLICT" not in codes
    recommendation = detail["operational_recommendation"]
    assert recommendation["capacity_status"] == "requires_review" and recommendation["capacity"]["status"] == "insuficiente"
    assert any(line.startswith("Capacidade:") for line in recommendation["rationale"])
    weeks = client.get("/api/capacity/Escolar").json()["weeks"]
    assert all("allocated" in week and "remaining" in week for week in weeks)


def test_estimated_capacity_removes_every_to_be_confirmed_sku(client):
    body = client.get("/api/capacity-plan").json()
    assert not [sku for sku, value in body["skus"].items() if value["status"] == "a_confirmar"]
    families = {family["family"]: family for family in body["families"]}
    escolar = families["Escolar"]
    assert escolar["scenarios"]["central"]["unscheduled_quantity"] > 0 and escolar["scenarios"]["conservador"]["unscheduled_quantity"] > 0
    estimated = [week for week in escolar["weeks"] if week["nature"] == "estimada"]
    assert estimated and all(week["method"] and week["week_start"] >= escolar["estimated_from"] for week in estimated)
    assert all(week["allocated"] <= week["available"] + 1e-6 for family in body["families"] for week in family["weeks"])
    for name in ("Acessórios", "Executivo", "Refis"):
        assert families[name]["status"] != "a_confirmar"
        assert "a_confirmar" not in {value["status"] for value in body["skus"].values() if value["family"] == name}
