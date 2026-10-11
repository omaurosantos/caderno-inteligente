import hashlib
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import SOURCE, app, pipeline
from backend.partners import create_partner_router


@pytest.fixture(scope='module')
def client():
    return TestClient(app)


def test_registry_and_real_partner_sku_keys(client):
    response = client.get('/api/partners')
    assert response.status_code == 200
    assert response.json()['total'] == 8
    # Etapa 16.1: KAs observam 10 SKUs pelo sell-out; os 3 canais diretos observam os 50 pelo faturamento.
    assert sum(p['observed_skus'] for p in response.json()['items']) == 50 + 3 * 50
    data = pipeline()[0]
    expected = set(zip(data['Sell_Out']['Cliente'], data['Sell_Out']['SKU'])) | set(zip(data['Sell_In']['Cliente'], data['Sell_In']['SKU'])) | set(zip(data['Carteira_Pedidos']['Cliente/Canal'], data['Carteira_Pedidos']['SKU']))
    result = client.get('/api/commercial-recommendations').json()
    assert {(r['partner'], r['sku']) for r in result['items']} == expected
    assert sum(len(r['periods']) for r in result['items'] if r['row_kind'] == 'partner') == 600
    assert sum(r['backlog_order_count'] for r in result['items']) == 53
    assert all('current_stock' not in r and 'attention_score' not in r for r in result['items'])


def test_partner_detail_decisions_are_unattributable_not_fabricated(client):
    result = client.get('/api/partners/KA-01').json()
    assert result['partner']['code'] == 'KA-01'
    assert result['decisions']['attribution_available'] is False
    assert result['decisions']['items'] is None
    assert client.get('/api/partners/not-real').status_code == 404
    assert client.get('/api/partners/not-real/skus').status_code == 404
    direct = client.get('/api/partners/' + quote('Loja própria', safe='')).json()
    assert direct['partner']['code'] == 'Loja própria'
    assert direct['partner']['observed_skus'] == 50
    assert direct['partner']['visibility_source'] == 'faturamento_direto' and direct['partner']['coverage'] == 1.0


@pytest.mark.parametrize(('key', 'value', 'field'), [('partner', 'KA-01', 'partner'), ('sku', 'CI-0002', 'sku'), ('region', 'Sul', 'region'), ('channel', 'Lojas físicas', 'channel'), ('action', 'avaliar_reposicao', 'action'), ('data_quality', 'insufficient', 'data_quality')])
def test_commercial_filters(client, key, value, field):
    response = client.get('/api/commercial-recommendations', params={key: value})
    assert response.status_code == 200
    assert response.json()['total'] > 0
    assert all(row[field] == value for row in response.json()['items'])


def test_pagination_and_validation(client):
    whole = client.get('/api/commercial-recommendations', params={'partner': 'KA-01'}).json()['items']
    page = client.get('/api/partners/KA-01/skus', params={'limit': 2, 'offset': 1}).json()
    assert page['items'] == whole[1:3]
    assert page['total'] == len(whole)
    for params in [{'limit': 0}, {'limit': 501}, {'offset': -1}, {'action': 'produzir'}, {'data_quality': 'fake'}]:
        assert client.get('/api/commercial-recommendations', params=params).status_code == 422


def test_new_reads_do_not_change_old_contracts_or_source(client):
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    paths = ['/api/priorities', '/api/forecasts', '/api/config', '/api/b2b2c/visibility', '/api/priorities/CI-0041']
    before = {p: client.get(p).json() for p in paths}
    assert client.get('/api/partners/KA-01/skus').status_code == 200
    assert client.get('/api/commercial-recommendations').status_code == 200
    assert {p: client.get(p).json() for p in paths} == before
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == digest


def test_invalid_commercial_configuration_blocks_only_additive_router(tmp_path):
    config = tmp_path / 'thresholds.json'
    config.write_text('{"recent_months": 0}', encoding='utf-8')
    isolated = FastAPI()
    isolated.include_router(create_partner_router(lambda: pipeline()[0], config))
    assert TestClient(isolated).get('/api/partners').status_code == 422


def test_direct_channels_are_observed_by_billing_not_insufficient(client):
    """Etapa 16.1 (P1): canal direto vende ao consumidor; a lacuna real (KA sem sell-out) continua aparecendo."""
    items = client.get('/api/commercial-recommendations', params={'limit': 500}).json()['items']
    assert len(items) == 95
    direct = [r for r in items if r['row_kind'] == 'direct']
    assert len(direct) == 22
    assert all(r['action'] == 'canal_direto' and r['data_quality'] == 'sufficient' and r['estimated_stock'] is None for r in direct)
    assert all(r['visibility_source'] == 'faturamento_direto' and r['stock_reason'] and r['requires_human_review'] for r in direct)
    assert all(r['challenge_action']['source'] == 'channel' for r in direct)
    assert sum(r['row_kind'] == 'partner' and r['action'] == 'dados_insuficientes' for r in items) == 23
    partners = {p['code']: p for p in client.get('/api/partners').json()['items']}
    assert all(p['coverage'] == (1.0 if p['visibility_source'] == 'faturamento_direto' else 0.2) for p in partners.values())
    assert client.get('/api/commercial-recommendations', params={'action': 'canal_direto'}).json()['total'] == 22
