import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from caderno_inteligente.collaboration import build_collaboration, load_collaboration_settings

CONFIG = Path(__file__).resolve().parents[1] / "config" / "collaboration.json"
SKUS = [f"S{i}" for i in range(10)]
OBS = "Observado pelo parceiro"


def dataset(months=12, skus_a=10, skus_b=2, gap_b=False):
    periods = pd.date_range("2025-09-01", periods=months, freq="MS")
    rows = []
    for cliente, n in (("KA-A", skus_a), ("KA-B", skus_b)):
        for sku in SKUS[:n]:
            for i, month in enumerate(periods):
                if cliente == "KA-B" and gap_b and i == months - 2:
                    continue
                rows.append({"Mês": month, "Cliente": cliente, "SKU": sku, "Quantidade vendida": 10, "Estoque estimado cliente": 50, "Natureza do dado": OBS})
    registry = pd.DataFrame([
        {"Código": "KA-A", "Nome fictício": "A", "Tipo": "Parceiro varejista", "Região": "Sul", "Porte": "Grande"},
        {"Código": "KA-B", "Nome fictício": "B", "Tipo": "Distribuidor", "Região": "Sul", "Porte": "Médio"},
        {"Código": "KA-C", "Nome fictício": "C", "Tipo": "Parceiro varejista", "Região": "Sul", "Porte": "Médio"},
        {"Código": "E-commerce", "Nome fictício": "E", "Tipo": "Canal direto", "Região": "—", "Porte": "—"},
    ])
    return {"Sell_Out": pd.DataFrame(rows), "Produtos": pd.DataFrame({"SKU": SKUS}), "Parceiros_Canais": registry}


def insights(*partners):
    items = [{"row_kind": "partner", "partner": p, "sku": s, "data_quality": "sufficient", "stock_identity_consistent": True, "divergence_ratio": 0.0} for p in partners for s in SKUS[:2]]
    items.append({"row_kind": "partner", "partner": "KA-B", "sku": "S9", "product": "Produto", "data_quality": "insufficient", "backlog_quantity": 100.0, "backlog_order_count": 1})
    return {"items": items}


@pytest.fixture
def cfg():
    return load_collaboration_settings(CONFIG)


def by_code(result):
    return {p["code"]: p for p in result["partners"]}


def test_real_config_is_valid_and_marked_as_proposal(cfg):
    assert cfg["status"] == "proposta_a_validar"
    assert sum(cfg["weights"].values()) == pytest.approx(1)


def test_invalid_weights_are_rejected(tmp_path, cfg):
    bad = copy.deepcopy(cfg)
    bad["weights"]["quality"] = 0.9
    path = tmp_path / "c.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_collaboration_settings(path)


def test_direct_channels_are_not_partners_of_the_program(cfg):
    result = build_collaboration(dataset(), insights("KA-A", "KA-B"), cfg)
    assert set(by_code(result)) == {"KA-A", "KA-B", "KA-C"}


def test_partner_without_sell_out_is_a_gap_not_zero_sales(cfg):
    partner = by_code(build_collaboration(dataset(), insights("KA-A"), cfg))["KA-C"]
    assert partner["level"] == 0 and partner["index"] is None and partner["dimensions"] is None
    assert partner["scenarios"][0]["level"] == 1


def test_complete_partner_without_observed_stock_stops_at_level_1(cfg):
    partner = by_code(build_collaboration(dataset(), insights("KA-A"), cfg))["KA-A"]
    assert partner["level"] == 1 and partner["index"] == pytest.approx(1.0)
    assert [g["criterion"] for g in partner["gaps"]] == ["stock_position"]


def test_observed_stock_position_unlocks_levels_2_and_3(cfg):
    informed = {**cfg, "stock_position_partners": ["KA-A"]}
    assert by_code(build_collaboration(dataset(), insights("KA-A"), informed))["KA-A"]["level"] == 3


def test_missing_month_lowers_frequency_and_continuity(cfg):
    dims = {d["key"]: d["value"] for d in by_code(build_collaboration(dataset(gap_b=True), insights("KA-B"), cfg))["KA-B"]["dimensions"]}
    assert dims["frequency"] < 1 and dims["continuity"] < dims["frequency"]
    assert dims["completeness"] == pytest.approx(0.2)


def test_simulation_lists_skus_with_backlog_and_never_promises(cfg):
    scenario = by_code(build_collaboration(dataset(), insights("KA-B"), cfg))["KA-B"]["scenarios"][0]
    assert scenario["level"] == 2 and scenario["additional_skus"] == 2
    assert scenario["unlocked"]["candidate_skus"][0]["sku"] == "S9"
    assert scenario["unlocked"]["covered_backlog_quantity"] == 100.0
    assert "não garantido" in scenario["nature"]


def test_program_baseline_has_no_invented_evolution(cfg):
    program = build_collaboration(dataset(), insights("KA-A", "KA-B"), cfg, 0.75)["program"]
    assert program["eligible_partners"] == 3 and program["participating_partners"] == 2
    assert program["matrix_pairs_observed"] == 12 and program["matrix_pairs_total"] == 30
    assert program["evolution"] is None and program["decisions"]["available"] is False
    assert "75,0%" in program["reconciliation"]
