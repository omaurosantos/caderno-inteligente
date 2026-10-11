import pandas as pd

from caderno_inteligente.impact_metrics import addressed_value, sop_divergence


def test_addressed_value_without_decisions_is_missing_not_zero():
    result = addressed_value([], [{"sku": "A", "value_at_risk": {"observed": 100.0}}])
    assert result["observed_total"] is None and result["sku_count"] == 0 and result["decided_skus"] == []
    assert result["nature"] == "observado" and "Nenhuma decisão registrada" in result["missing_reason"]


def test_addressed_value_with_unavailable_persistence_is_missing_with_reason():
    result = addressed_value([{"sku": "A"}], [{"sku": "A", "value_at_risk": {"observed": 100.0}}], missing_reason="Persistência indisponível.")
    assert result["observed_total"] is None and result["missing_reason"] == "Persistência indisponível."


def test_addressed_value_with_decisions_but_no_computed_value_is_missing():
    result = addressed_value([{"sku": "B"}], [{"sku": "B", "value_at_risk": {"observed": None}}])
    assert result["observed_total"] is None and result["missing_reason"] and result["skus_without_value"] == ["B"]


def test_addressed_value_sums_decided_skus_once_and_counts_missing_apart():
    ranking = [{"sku": "A", "value_at_risk": {"observed": 100.5}}, {"sku": "B", "value_at_risk": {"observed": None}},
               {"sku": "C", "value_at_risk": {"observed": 900.0}}]
    feedback = [{"sku": "A"}, {"sku": "A"}, {"sku": "B"}, {"sku": "Z"}]
    result = addressed_value(feedback, ranking)
    assert result["observed_total"] == 100.5 and result["sku_count"] == 1
    assert result["decided_skus"] == ["A", "B", "Z"] and result["skus_without_value"] == ["B", "Z"]
    assert result["missing_reason"] is None


def _forecasts():
    return pd.DataFrame([
        {"sku": "A", "status": "ok", "forecast_months": ["2026-10-01", "2026-11-01", "2027-01-01"], "forecast_values": [130.0, 100.0, 50.0]},
        {"sku": "B", "status": "ok", "forecast_months": ["2026-10-01"], "forecast_values": [10.0]},
        {"sku": "C", "status": "insuficiente", "forecast_months": ["2026-10-01"], "forecast_values": [999.0]},
    ])


def test_sop_divergence_only_common_months_and_threshold():
    sop = pd.DataFrame({"SKU": ["A", "A", "B", "C"], "Mês": pd.to_datetime(["2026-10-01", "2026-11-01", "2026-10-01", "2026-10-01"]),
                        "Previsão unidades": [100, 100, 0, 1]})
    result = sop_divergence(_forecasts(), sop)
    assert result["months"] == ["2026-10", "2026-11"] and result["compared_pairs"] == 2  # B sem S&OP>0, C sem modelo ok, jan/27 fora
    assert [(i["sku"], i["month"], i["ratio"]) for i in result["items"]] == [("A", "2026-10", 0.3)]
    assert "não é mensurável" in result["note"] and result["count"] == 1
    assert result["requires_human_review"] is True  # pauta de revisão


def test_sop_divergence_without_commercial_forecast():
    result = sop_divergence(_forecasts(), None)
    assert result["count"] == 0 and result["items"] == [] and "indisponível" in result["note"]
