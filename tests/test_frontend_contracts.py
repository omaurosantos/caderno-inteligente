"""Smoke test: the real API still provides every field the frontend fixtures (and pages) rely on.

The key list lives in frontend/src/test/contract-keys.json and is shared with the Vitest contract test.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "frontend/src/test/contract-keys.json").read_text(encoding="utf-8"))
DYNAMIC = set(CONTRACT["dynamic_keys"])
SKU, PARTNER = "CI-0014", "KA-01"


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
    client = TestClient(main.app)
    # A legacy snapshot (no extended payload) and a current one, mirroring the comparison fixture.
    persistence = main._persistence()
    legacy = persistence.create_run(main.SOURCE, main.load_weights(), main.load_rule_thresholds(), {}, main._records(main.data()[3]))
    current = client.post("/api/runs").json()["id"]
    paths = {
        "overview": "/api/overview", "priorities": "/api/priorities", "quality": "/api/data-quality", "config": "/api/config",
        "runs": "/api/runs", "b2b": "/api/b2b2c/visibility", "forecasts": "/api/forecasts", "revenueForecast": "/api/revenue-forecast", "capacityPlan": "/api/capacity-plan", "productionPlan": "/api/production-plan", "events": "/api/events",
        "directChannels": "/api/direct-channels", "directChannel": "/api/direct-channels/E-commerce", "channelFindings": "/api/data-quality/channels", "skuDetail": f"/api/priorities/{SKU}",
        "partners": "/api/partners", "partnerDetail": f"/api/partners/{PARTNER}", "partnerSkus": f"/api/partners/{PARTNER}/skus?limit=50",
        "commercial": "/api/commercial-recommendations?limit=50", "validation": "/api/validation/summary", "forecastLab": "/api/forecast-lab", "modelBenchmark": "/api/model-benchmark",
        "runComparison": f"/api/run-comparisons?base={legacy}&target={current}", "system": "/api/system",
    }
    result = {}
    for name, path in paths.items():
        response = client.get(path)
        assert response.status_code == 200, (name, response.text)
        result[name] = response.json()
    yield result
    patch.undo()


def test_contract_covers_the_same_endpoints(responses):
    assert set(responses) == set(CONTRACT["endpoints"])


@pytest.mark.parametrize("name", sorted(CONTRACT["endpoints"]))
def test_real_api_provides_every_frontend_field(responses, name):
    assert missing_keys(CONTRACT["endpoints"][name]["keys"], responses[name]) == []
