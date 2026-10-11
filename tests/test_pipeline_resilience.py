"""Camadas aditivas (alocação, impacto, capacidade estimada) não derrubam a API quando a configuração é inválida ou ausente."""
from fastapi.testclient import TestClient

import backend.main as main

SKU = "CI-0041"  # SKU disputado na alocação da base real


def _isolate(monkeypatch, tmp_path, **files):
    """Aponta as configurações indicadas para arquivos temporários e zera os caches; monkeypatch restaura tudo depois."""
    for name, content in files.items():
        path = tmp_path / f"{name.lower()}.json"
        if content is not None:
            path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(main, name, path)
    optional = (main.ALLOCATION_FILE, main.IMPACT_FILE, main.CAPACITY_EXTENSION_FILE, main.COMMERCIAL_THRESHOLDS_FILE,
                main.DIRECT_CHANNEL_FILE, main.PARTNER_PROJECTION_FILE)
    monkeypatch.setattr(main, "OPTIONAL_CONFIG_FILES", optional)
    monkeypatch.setattr(main, "_pipeline_cache", None)
    monkeypatch.setattr(main, "_direct_channels_cache", None)
    builds = []
    original = main._build_pipeline

    def counting_build():
        builds.append(1)
        return original()

    monkeypatch.setattr(main, "_build_pipeline", counting_build)
    return TestClient(main.app), builds


def _warning_codes(client) -> set[str]:
    return {item["code"] for item in client.get("/api/data-quality").json()["warnings"]}


def test_invalid_allocation_and_missing_capacity_extension_degrade_without_breaking_the_api(monkeypatch, tmp_path):
    client, builds = _isolate(monkeypatch, tmp_path, ALLOCATION_FILE='{"campo": "inválido"', CAPACITY_EXTENSION_FILE=None)

    for url in ("/api/allocation", "/api/allocation/regions"):
        response = client.get(url)
        assert response.status_code == 422 and response.json()["detail"].startswith("Alocação bloqueada por dados/configuração inválidos")

    ranking = client.get("/api/priorities").json()
    assert ranking and all("urgency_tier" not in row for row in ranking)  # impact=None: ordem pela pontuação de sinais
    assert [row["priority"] for row in ranking] == list(range(1, len(ranking) + 1))
    assert {"ALLOCATION_UNAVAILABLE", "CAPACITY_EXTENSION_UNAVAILABLE"} <= _warning_codes(client)

    detail = client.get(f"/api/priorities/{SKU}").json()
    assert detail["allocation"] is None and detail["challenge_action"]
    assert client.get("/api/forecasts").status_code == 200
    capacity = client.get("/api/capacity-plan")
    assert capacity.status_code == 200
    assert client.get("/api/partners").status_code == 200
    assert client.get("/api/validation/summary").status_code == 200
    assert len(builds) == 1  # o pipeline com a camada caída continua em cache


def test_invalid_impact_settings_fall_back_to_signal_order_with_warning(monkeypatch, tmp_path):
    client, builds = _isolate(monkeypatch, tmp_path, IMPACT_FILE="[]")
    ranking = client.get("/api/priorities").json()
    assert ranking and all("urgency_tier" not in row for row in ranking)
    assert client.get("/api/allocation").status_code == 200  # a alocação não depende do impacto
    assert "IMPACT_UNAVAILABLE" in _warning_codes(client)
    assert client.get(f"/api/priorities/{SKU}").status_code == 200
    assert len(builds) == 1


def test_pipeline_signature_covers_commercial_projection_and_direct_channel_configs(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "_optional_file_signature", lambda path: seen.append(path) or (0, 0))
    main._pipeline_signature()
    assert {main.COMMERCIAL_THRESHOLDS_FILE, main.PARTNER_PROJECTION_FILE, main.DIRECT_CHANNEL_FILE} <= set(seen)
    assert {path.name for path in seen} >= {"commercial_thresholds.json", "partner_projection.json", "direct_channel_thresholds.json"}


def test_missing_optional_config_enters_the_signature_as_none(tmp_path):
    assert main._optional_file_signature(tmp_path / "ausente.json") is None


def test_direct_channels_are_computed_once_per_pipeline_and_shared(monkeypatch):
    calls = []
    original = main.build_direct_channels

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(main, "build_direct_channels", counting)
    monkeypatch.setattr(main, "_direct_channels_cache", None)
    client = TestClient(main.app)
    assert client.get("/api/partners").status_code == 200
    assert client.get("/api/rules/coverage").status_code == 200
    assert client.get("/api/partners").status_code == 200
    first = main.direct_channels()
    assert main.direct_channels() is first
    assert len(calls) == 1


def test_invalid_direct_channel_config_answers_422_and_is_not_rebuilt_each_request(monkeypatch, tmp_path):
    path = tmp_path / "direct.json"
    path.write_text('{"desconhecido": 1}', encoding="utf-8")
    monkeypatch.setattr(main, "DIRECT_CHANNEL_FILE", path)
    monkeypatch.setattr(main, "_direct_channels_cache", None)
    calls = []
    original = main.load_direct_channel_settings
    monkeypatch.setattr(main, "load_direct_channel_settings", lambda file: calls.append(file) or original(file))
    client = TestClient(main.app)
    assert client.get("/api/rules/coverage").status_code == 422
    assert client.get("/api/rules/coverage").status_code == 422
    assert len(calls) == 1

