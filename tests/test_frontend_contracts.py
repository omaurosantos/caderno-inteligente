"""Smoke test: the real API still provides every field the frontend fixtures (and pages) rely on.

The key list lives in frontend/src/test/contract-keys.json and is shared with the Vitest contract test.
"""
import hashlib
import json
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from caderno_inteligente.ingestion import load_workbook

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "frontend/src/test/contract-keys.json").read_text(encoding="utf-8"))
DYNAMIC = set(CONTRACT["dynamic_keys"])
SKU, PARTNER = "CI-0014", "KA-01"
# POST: conferidos no teste com DATA_SOURCE=banco, fora do laço GET.
POST_ENDPOINTS = {name for name, endpoint in CONTRACT["endpoints"].items() if endpoint.get("method") == "POST"}
GET_ENDPOINTS = sorted(set(CONTRACT["endpoints"]) - POST_ENDPOINTS)
EXAMPLE = ROOT / "docs/exemplos/atualizacao-2026-10.xlsx"


def key_paths(value, prefix="", paths=None, empty=None):
    """Return (paths, empty): empty holds paths whose value is null or an empty list/map, so children are unobservable."""
    paths = set() if paths is None else paths
    empty = set() if empty is None else empty
    if isinstance(value, list):
        if not value and prefix:
            empty.add(prefix)
        for item in value:
            key_paths(item, f"{prefix}[]", paths, empty)
    elif isinstance(value, dict):
        if not value and prefix:
            empty.add(prefix)
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            if child is None:
                empty.add(path)
            elif key not in DYNAMIC:
                key_paths(child, path, paths, empty)
    return paths, empty


def missing_keys(required: list[str], value) -> list[str]:
    paths, empty = key_paths(value)

    def observable_ancestor_is_empty(key: str) -> bool:
        candidate = key
        while "." in candidate or candidate.endswith("[]"):
            candidate = candidate[:-2] if candidate.endswith("[]") else candidate.rsplit(".", 1)[0]
            if candidate in empty:
                return True
        return False

    return [key for key in required if key not in paths and not observable_ancestor_is_empty(key)]


def test_missing_field_is_detected_even_when_parent_exists():
    assert missing_keys(["a.b", "a.c"], {"a": {"b": 1}}) == ["a.c"]
    assert missing_keys(["items[].x"], {"items": []}) == []
    assert missing_keys(["items[].x"], {"items": [{"y": 1}]}) == ["items[].x"]
    assert missing_keys(["target.value"], {"target": None}) == []


@pytest.fixture(scope="module")
def responses(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("contracts")
    patch = pytest.MonkeyPatch()
    patch.setattr(main, "RUNS_DB", tmp / "runs.db")
    patch.setattr(main, "CASES_DB", tmp / "cases.db")
    patch.setattr(main, "FEEDBACK_DB", tmp / "feedback.db")
    patch.delenv("DATABASE_URL", raising=False)
    patch.setenv("DATA_SOURCE", "planilha")
    client = TestClient(main.app)
    # A legacy snapshot (no extended payload) and a current one, mirroring the comparison fixture.
    persistence = main._persistence()
    legacy = persistence.create_run(main.SOURCE, main.load_weights(), main.load_rule_thresholds(), {}, main._records(main.data()[3]))
    current = client.post("/api/runs").json()["id"]
    paths = {
        "overview": "/api/overview", "priorities": "/api/priorities", "quality": "/api/data-quality", "config": "/api/config",
        "runs": "/api/runs", "b2b": "/api/b2b2c/visibility", "forecasts": "/api/forecasts", "revenueForecast": "/api/revenue-forecast", "capacityPlan": "/api/capacity-plan", "productionPlan": "/api/production-plan", "events": "/api/events",
        "collaboration": "/api/collaboration", "directChannels": "/api/direct-channels", "directChannel": "/api/direct-channels/E-commerce", "channelFindings": "/api/data-quality/channels", "skuDetail": f"/api/priorities/{SKU}",
        "partners": "/api/partners", "partnerDetail": f"/api/partners/{PARTNER}", "partnerSkus": f"/api/partners/{PARTNER}/skus?limit=50",
        "commercial": "/api/commercial-recommendations?limit=50", "validation": "/api/validation/summary", "forecastLab": "/api/forecast-lab", "modelBenchmark": "/api/model-benchmark",
        "runComparison": f"/api/run-comparisons?base={legacy}&target={current}", "system": "/api/system",
        "allocation": "/api/allocation", "allocationRegions": "/api/allocation/regions", "rulesCoverage": "/api/rules/coverage",
        "dataset": "/api/dataset", "datasetVersions": "/api/dataset/versions",
    }
    result = {}
    for name, path in paths.items():
        response = client.get(path)
        assert response.status_code == 200, (name, response.text)
        result[name] = response.json()
    yield result
    patch.undo()


def test_contract_covers_the_same_endpoints(responses):
    assert set(responses) == set(GET_ENDPOINTS)
    assert POST_ENDPOINTS == {"datasetPreview"}


@pytest.mark.parametrize("name", GET_ENDPOINTS)
def test_real_api_provides_every_frontend_field(responses, name):
    assert missing_keys(CONTRACT["endpoints"][name]["keys"], responses[name]) == []


def missing_item_keys(field: str, response) -> list[str]:
    """list_items: campos de cada item de uma lista cuja chave é dinâmica em outro endpoint (ex.: datasetPreview.sheets)."""
    items = response
    for key in field.split(".")[1:]:
        items = items[key]
    assert items, field
    return sorted({key for item in items for key in CONTRACT["list_items"][field] if key not in item})


def test_upload_endpoints_in_database_mode(tmp_path, monkeypatch):
    """DATA_SOURCE=banco com SQLite temporário: prévia real do pacote de exemplo, aplicação, versões e casos da base anterior."""
    for name in ("RUNS_DB", "CASES_DB", "FEEDBACK_DB", "DATASET_DB", "BENCHMARK_DB"):
        monkeypatch.setattr(main, name, tmp_path / f"{name.lower()}.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_SOURCE", "banco")
    monkeypatch.setenv("AUTH_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setattr(main, "_pipeline_cache", None)
    monkeypatch.setattr(main, "_version_seen", None)
    password = secrets.token_urlsafe(18)  # gerada no teste e nunca registrada
    main.user_store().create_user("contrato@exemplo.com", "Contrato", password)
    main.dataset_store().import_dataset(load_workbook(main.SOURCE))
    client = TestClient(main.app)
    token = client.post("/api/auth/login", json={"email": "contrato@exemplo.com", "password": password}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"

    content = EXAMPLE.read_bytes()
    headers = {"Content-Type": "application/octet-stream", "X-Filename": EXAMPLE.name}
    preview = client.post("/api/dataset/preview", content=content, headers=headers)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert missing_keys(CONTRACT["endpoints"]["datasetPreview"]["keys"], body) == []
    for field in (field for field in CONTRACT["list_items"] if field.startswith("datasetPreview.")):
        assert missing_item_keys(field, body) == [], field

    applied = client.post("/api/dataset/apply", content=content, headers={
        **headers, "X-Confirm-Sha256": hashlib.sha256(content).hexdigest(), "X-Expected-Version": str(body["expected_version"])})
    assert applied.status_code == 200, applied.text
    assert missing_keys(CONTRACT["endpoints"]["datasetPreview"]["keys"], applied.json()["preview"]) == []

    after = {"dataset": "/api/dataset", "datasetVersions": "/api/dataset/versions", "validation": "/api/validation/summary", "quality": "/api/data-quality"}
    for name, path in after.items():
        response = client.get(path)
        assert response.status_code == 200, (name, response.text)
        assert response.json() != {}, name
        assert missing_keys(CONTRACT["endpoints"][name]["keys"] + CONTRACT["after_upload"].get(name, []), response.json()) == [], name
    assert client.get("/api/dataset/versions").json()["items"], "a versão aplicada aparece no histórico"
