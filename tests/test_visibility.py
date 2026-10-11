"""Etapa 16.1: mapa da jornada (até onde vemos o consumidor) e avisos de fontes comerciais que não fecham (P7c)."""
import copy

import pandas as pd
import pytest

from caderno_inteligente.visibility import (
    SELLIN_BILLING_RATIO_LIMIT, billing_uniform_split_warning, build_visibility_journey, sellin_billing_divergence_warning,
)

MONTHS = pd.date_range('2025-09-01', '2026-08-01', freq='MS')


def source(billed=None, sell_in_ka2=69, sell_out_ka1=30):
    """KA1 e KA2 (parceiros) e D1 (canal direto); por padrão cada cliente fatura 10 un./mês de cada SKU."""
    billed = billed or {'KA1': {'S1': 10, 'S2': 10}, 'KA2': {'S1': 10, 'S2': 10}, 'D1': {'S1': 20, 'S2': 20}}
    sales = [{'Mês': m, 'SKU': sku, 'Cliente/Canal': client, 'Quantidade faturada': qty, 'Valor faturado (R$)': qty * 10.0}
             for m in MONTHS for client, by_sku in billed.items() for sku, qty in by_sku.items()]
    return {
        'Parceiros_Canais': pd.DataFrame([{'Código': 'KA1', 'Tipo': 'Parceiro varejista'}, {'Código': 'KA2', 'Tipo': 'Distribuidor'}, {'Código': 'D1', 'Tipo': 'Canal direto'}]),
        'Vendas_24m': pd.DataFrame(sales),
        'Sell_In': pd.DataFrame([{'Mês': m, 'Cliente': c, 'SKU': 'S1', 'Quantidade enviada': q} for m in MONTHS for c, q in (('KA1', 11), ('KA2', sell_in_ka2))]),
        'Sell_Out': pd.DataFrame([{'Mês': m, 'Cliente': 'KA1', 'SKU': 'S1', 'Quantidade vendida': sell_out_ka1, 'Estoque estimado cliente': 5,
                                   'Natureza do dado': 'Observado pelo parceiro'} for m in MONTHS[-6:]]),
    }


def test_journey_parts_add_up_and_partner_sell_out_is_capped_by_billing():
    data = source()
    before = copy.deepcopy(data)
    journey = build_visibility_journey(data)
    assert len(journey['window_months']) == 12 and journey['window_months'][-1] == '2026-08'
    assert journey['total_units'] == 12 * (20 + 20 + 40)
    by_type = {item['type']: item for item in journey['by_channel_type']}
    direct, retail, distributor = by_type['Canal direto'], by_type['Parceiro varejista'], by_type['Distribuidor']
    assert direct['observed_consumer_units'] == direct['billed_units'] == 480 and direct['share_observed'] == 1.0
    # KA1 informou 6 × 30 = 180 un. de S1, mas só foram faturadas 120 un. do par: o observado fica limitado a 120.
    assert retail['observed_consumer_units_raw'] == 180 and retail['observed_consumer_units'] == 120 and retail['exceeds_billing'] is True
    assert distributor['observed_consumer_units'] == 0 and distributor['without_visibility_units'] == 240 and distributor['exceeds_billing'] is False
    for item in journey['by_channel_type']:
        assert item['observed_consumer_units'] + item['without_visibility_units'] == item['billed_units']
    assert journey['observed_consumer_units'] + journey['without_visibility_units'] == journey['total_units']
    assert journey['observed_share'] == pytest.approx(600 / 960, abs=1e-4)
    assert journey['nature'] and journey['note']
    for key in data:
        pd.testing.assert_frame_equal(data[key], before[key])


def test_journey_window_is_configurable():
    assert build_visibility_journey(source(), window_months=3)['total_units'] == 3 * 80


def test_sellin_billing_divergence_flags_partner_above_limit():
    warning = sellin_billing_divergence_warning(source())
    assert SELLIN_BILLING_RATIO_LIMIT == 1.25
    assert warning['code'] == 'SELLIN_BILLING_DIVERGENCE' and warning['count'] == 1
    assert warning['items'] == [{'partner': 'KA2', 'sell_in_units': 69 * 12, 'billed_units': 10 * 12, 'ratio': 6.9}]
    assert 'Vendas_24m para o total do SKU' in warning['message']
    assert sellin_billing_divergence_warning(source(sell_in_ka2=12)) is None  # 1,2× fica abaixo do limite


def test_uniform_billing_split_detected_and_real_pattern_is_not():
    warning = billing_uniform_split_warning(source())
    assert warning['code'] == 'BILLING_UNIFORM_SPLIT' and warning['min_ratio'] == warning['max_ratio'] == 1.0 and warning['count'] == 6
    assert 'não é usado para padrões por parceiro' in warning['message']
    skewed = source(billed={'KA1': {'S1': 30, 'S2': 2}, 'KA2': {'S1': 10, 'S2': 10}, 'D1': {'S1': 20, 'S2': 20}})
    assert billing_uniform_split_warning(skewed) is None
