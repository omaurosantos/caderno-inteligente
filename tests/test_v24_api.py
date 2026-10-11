import pytest
from fastapi.testclient import TestClient
from backend.main import _partner_level, app

def test_scenario_is_explicit_and_does_not_change_official_config():
 c=TestClient(app); r=c.post('/api/scenarios',json={'weights':{'EXCESS_COVERAGE':99}}).json()
 assert r['is_simulation'] and r['weights']['EXCESS_COVERAGE']==99
 assert c.get('/api/config').json()['weights']['EXCESS_COVERAGE']==3

def test_b2b_visibility_has_partner_coverage():
 c=TestClient(app); r=c.get('/api/b2b2c/visibility').json()
 # Etapa 16.1: os canais diretos entram, observados pelo faturamento (cobertura 1,0); os KAs seguem com 0,2.
 assert len(r['partners'])==8
 ka=[x for x in r['partners'] if x['visibility_source']=='sell_out_parceiro']
 direct=[x for x in r['partners'] if x['visibility_source']=='faturamento_direto']
 assert len(ka)==5 and all(x['coverage']==.2 for x in ka)
 assert len(direct)==3 and all(x['coverage']==1.0 for x in direct)
 assert all(x['level']=='Essencial' and x['next_level']=='Conectado' for x in ka)
 assert all(x['next_level_required_skus']==10 for x in ka)
 j=r['journey']
 assert j['observed_consumer_units']+j['without_visibility_units']==j['total_units']
 assert all(t['observed_consumer_units']+t['without_visibility_units']==t['billed_units'] for t in j['by_channel_type'])
 assert next(t for t in j['by_channel_type'] if t['type']=='Canal direto')['share_observed']==1.0
 assert len(j['window_months'])==12
 assert 'Não representa acordo comercial firmado' in r['classification_disclaimer']

@pytest.mark.parametrize(('coverage','expected'),[(0,'Sem visibilidade'),(.2,'Essencial'),(.4,'Conectado'),(.8,'Estratégico')])
def test_b2b_level_boundaries(coverage,expected):
 assert _partner_level(coverage)==expected


def test_data_quality_lists_commercial_source_warnings():
 w={x['code']:x for x in TestClient(app).get('/api/data-quality').json()['warnings'] if 'code' in x}
 items={i['partner']:i['ratio'] for i in w['SELLIN_BILLING_DIVERGENCE']['items']}
 assert items['KA-05']==pytest.approx(6.9,abs=.05) and items['KA-01']==pytest.approx(1.47,abs=.01)
 split=w['BILLING_UNIFORM_SPLIT']
 assert .9<=split['min_ratio']<=split['max_ratio']<=1.1
