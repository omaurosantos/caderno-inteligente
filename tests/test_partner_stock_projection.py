from pathlib import Path

import pandas as pd
import pytest

from caderno_inteligente.ingestion import load_workbook
from caderno_inteligente.partner_stock_projection import build_partner_stock_projection, load_partner_projection_settings
from caderno_inteligente.transformations import normalise_dataset

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = load_partner_projection_settings(ROOT / "config/partner_projection.json")


def _dataset(sell_out, sell_in, stock, start="2025-09"):
    months = pd.period_range(start, periods=len(sell_out), freq="M").to_timestamp()
    out = pd.DataFrame({"Mês": months, "Cliente": "KA-T1", "SKU": "TEST-001", "Quantidade vendida": sell_out, "Estoque estimado cliente": stock})
    inn = pd.DataFrame({"Mês": months, "Cliente": "KA-T1", "SKU": "TEST-001", "Quantidade enviada": sell_in})
    return {"Sell_Out": out, "Sell_In": inn}


def test_projection_follows_stock_identity_in_both_scenarios():
    result = build_partner_stock_projection(_dataset([30.0] * 12, [20.0] * 12, [100.0] * 12), SETTINGS)
    item = result["items"][0]
    assert item["status"] == "ok"
    assert item["forecast_monthly_sell_out"] == 30.0
    assert item["months"] == ["2026-09", "2026-10", "2026-11"]
    assert item["scenarios"]["with_replenishment"]["projected_stock"] == [90.0, 80.0, 70.0]
    assert item["scenarios"]["without_replenishment"]["projected_stock"] == [70.0, 40.0, 10.0]
    assert item["scenarios"]["without_replenishment"]["stockout_month"] is None
    assert item["coverage_days_now"] == 100.0  # 100 un. ÷ 1 un./dia
    assert item["replenishment_to_target"] == 0.0  # sobram 70 un. depois do mês, acima das 30 da cobertura-alvo


def test_stockout_month_and_replenishment_to_target():
    item = build_partner_stock_projection(_dataset([60.0] * 12, [0.0] * 12, [50.0] * 12), SETTINGS)["items"][0]
    assert item["scenarios"]["without_replenishment"]["stockout_month"] == "2026-09"
    assert item["scenarios"]["without_replenishment"]["coverage_days_end"] == 0.0
    assert item["replenishment_to_target"] == 70.0  # alvo 60 un. (30 dias × 2/dia) − (50 − 60)


def test_missing_month_in_window_is_insufficient_never_zero():
    sell_out = [30.0] * 12
    sell_out[-2] = float("nan")
    item = build_partner_stock_projection(_dataset(sell_out, [20.0] * 12, [100.0] * 12), SETTINGS)["items"][0]
    assert item["status"] == "insufficient_data"
    assert item["current_stock"] is None and item["forecast_monthly_sell_out"] is None and item["scenarios"] is None
    assert "6 meses" in item["reason"]


def test_constant_series_has_zero_error_and_errors_are_always_reported():
    result = build_partner_stock_projection(_dataset([30.0] * 12, [20.0] * 12, [100.0] * 12), SETTINGS)
    assert result["errors"]["sell_out"] == {"wape": 0.0, "bias": 0.0, "points": 12}
    assert result["errors"]["sell_in"]["wape"] == 0.0
    assert result["items"][0]["errors"]["sell_in"]["points"] == 12
    assert result["requires_human_review"] is True and result["nature"] == "estimado"


def test_invalid_settings_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"window_months": 0, "horizon_months": 3, "days_per_month": 30, "target_coverage_days": 30, "evaluation": {"first_origin": "2026-02", "last_origin": "2026-05"}}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_partner_projection_settings(path)


def test_real_data_projection_and_measured_errors():
    dataset = normalise_dataset(load_workbook(ROOT / "data/source/Base de Dados - Caderno Inteligente.xlsm"))
    result = build_partner_stock_projection(dataset, SETTINGS)
    assert result["pairs"] == result["pairs_with_projection"] == 50
    # Erros medidos com a média de 6 meses nas origens de fev a mai/2026 (análise de 09/10/2026).
    assert result["errors"]["sell_out"]["wape"] == pytest.approx(0.264, abs=0.002)
    assert result["errors"]["sell_in"]["wape"] == pytest.approx(0.282, abs=0.002)
    for item in result["items"]:
        stock = item["current_stock"]
        expected = stock + item["scenarios"]["with_replenishment"]["monthly_sell_in"] - item["forecast_monthly_sell_out"]
        assert item["scenarios"]["with_replenishment"]["projected_stock"][0] == pytest.approx(expected, abs=0.2)
