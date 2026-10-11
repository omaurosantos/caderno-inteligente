import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from caderno_inteligente.persistence import SqlitePersistence

ROOT = Path(__file__).resolve().parents[1]
GUARDED = [ROOT / "config/prioritization_weights.json", ROOT / "config/rule_thresholds.json", ROOT / "data/source/Base de Dados - Caderno Inteligente.xlsm"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolated SQLite so tests never write to the local runtime databases."""
    monkeypatch.setattr(main, "RUNS_DB", tmp_path / "runs.db")
    monkeypatch.setattr(main, "CASES_DB", tmp_path / "cases.db")
    monkeypatch.setattr(main, "FEEDBACK_DB", tmp_path / "feedback.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(main.app)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_contract_is_preserved_and_extended(client):
    response = client.post("/api/runs")
    assert response.status_code == 200 and set(response.json()) == {"id"}
    run_id = response.json()["id"]
    listed = client.get("/api/runs").json()[0]
    assert {"id", "created_at", "source_hash", "prioritized_skus"} <= set(listed)
    assert listed["comparison_schema_version"] == 1
    detail = client.get(f"/api/runs/{run_id}").json()
    assert {"weights", "thresholds", "quality", "ranking"} <= set(detail)
    comparison = detail["comparison"]
    assert set(comparison["forecasts"]) == {item["sku"] for item in client.get("/api/forecasts").json()}
    # Partner coverage is stored per registered partner, never as SKU-level allocations.
    for partner in comparison["b2b_coverage"]["partners"].values():
        assert set(partner) == {"name", "coverage", "observed_skus", "total_catalog_skus", "latest_sell_out_month", "action_counts"}


def test_identical_runs_compare_without_changes_and_keep_audit_context(client):
    before = {path: _digest(path) for path in GUARDED}
    priorities = client.get("/api/priorities").json()
    first, second = client.post("/api/runs").json()["id"], client.post("/api/runs").json()["id"]
    result = client.get(f"/api/run-comparisons?base={first}&target={second}").json()
    assert result["base"]["source_hash"] == result["target"]["source_hash"]
    assert result["base"]["created_at"] and result["target"]["created_at"]
    assert result["context"]["weights_changes"] == [] and result["context"]["thresholds_changes"] == []
    assert result["ranking"]["summary"]["changed"] == 0 and result["ranking"]["summary"]["unchanged"] == len(priorities)
    assert result["forecasts"]["summary"]["changed_skus"] == 0
    assert result["b2b_coverage"]["summary"]["changed_partners"] == 0
    assert client.get("/api/priorities").json() == priorities
    assert {path: _digest(path) for path in GUARDED} == before


def test_real_weight_change_is_fully_explained(client, tmp_path):
    official = client.post("/api/runs").json()["id"]
    weights = {**main.load_weights(), "LOW_SELLOUT_VISIBILITY": 12}
    scenario = client.post("/api/scenarios", json={"weights": weights}).json()
    persistence = SqlitePersistence(tmp_path / "cases.db", tmp_path / "feedback.db", tmp_path / "runs.db")
    simulated = persistence.create_run(main.SOURCE, scenario["weights"], scenario["thresholds"], {}, scenario["ranking"])
    result = client.get(f"/api/run-comparisons?base={official}&target={simulated}").json()
    ranking = result["ranking"]
    assert result["context"]["weights_changes"] == [{"key": "LOW_SELLOUT_VISIBILITY", "base": 2, "target": 12}]
    assert ranking["summary"]["changed"] > 0 and ranking["summary"]["unexplained"] == 0
    for item in ranking["changed"]:
        if item["score_delta"]:
            assert item["score_breakdown"] == [{"code": "LOW_SELLOUT_VISIBILITY", "change": "peso alterado", "base_weight": 2, "target_weight": 12, "delta": 10}]
    # The simulated snapshot has no extended payload: forecast and partner sections are refused with a reason.
    assert result["forecasts"]["available"] is False and f"#{simulated}" in result["forecasts"]["reason"]


def test_comparison_errors(client):
    run_id = client.post("/api/runs").json()["id"]
    assert client.get(f"/api/run-comparisons?base={run_id}&target={run_id}").status_code == 422
    assert client.get(f"/api/run-comparisons?base={run_id}&target=99999").status_code == 404
    assert client.get("/api/run-comparisons?base=0&target=1").status_code == 422
    assert client.get(f"/api/runs/{run_id}").status_code == 200


def test_snapshot_keeps_tier_and_value_and_weight_change_never_moves_tier(client, tmp_path):
    """Etapa 16.3: o snapshot guarda faixa e valor em risco; mudar só um peso altera sinais, nunca faixa ou valor."""
    official = client.post("/api/runs").json()["id"]
    ranking = client.get(f"/api/runs/{official}").json()["ranking"]
    assert ranking and all(item["urgency_tier"] in (1, 2, 3, 4) and isinstance(item["value_at_risk"], dict) for item in ranking)
    weights = {**main.load_weights(), "LOW_SELLOUT_VISIBILITY": 40}
    scenario = client.post("/api/scenarios", json={"weights": weights}).json()
    persistence = SqlitePersistence(tmp_path / "cases.db", tmp_path / "feedback.db", tmp_path / "runs.db")
    simulated = persistence.create_run(main.SOURCE, scenario["weights"], scenario["thresholds"], {}, scenario["ranking"])
    result = client.get(f"/api/run-comparisons?base={official}&target={simulated}").json()["ranking"]
    assert result["summary"]["by_driver"]["faixa"] == 0 and result["summary"]["by_driver"]["valor"] == 0
    for item in result["changed"]:
        assert item["ranking_basis"] == "faixa_e_valor" and item["tier_change"] is None and item["value_change"] is None
        if item["position_delta"]:
            # só desempate dentro da mesma faixa e valor (do próprio SKU ou de um vizinho empatado)
            assert item["position_driver"] in ("sinais", "outros_skus"), item["sku"]
    # um snapshot antigo (sem faixa) contra o atual: a troca de posição é atribuída à mudança de critério
    legacy_ranking = [{key: value for key, value in item.items() if key not in ("urgency_tier", "value_at_risk")} for item in ranking]
    legacy_ranking.sort(key=lambda item: (-item["attention_score"], item["sku"]))
    for position, item in enumerate(legacy_ranking, start=1):
        item["priority"] = position
    legacy = persistence.create_run(main.SOURCE, main.load_weights(), main.load_rule_thresholds(), {}, legacy_ranking)
    mixed = client.get(f"/api/run-comparisons?base={legacy}&target={official}").json()["ranking"]
    assert mixed["available"] and mixed["summary"]["by_driver"]["criterio"] == sum(bool(item["position_delta"]) for item in mixed["changed"]) > 0
