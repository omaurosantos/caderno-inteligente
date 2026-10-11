import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { CommercialMatrix } from '../components/CommercialMatrix';
import { RegionRisk } from '../components/RegionRisk';
import { VisibilityJourney } from '../components/VisibilityJourney';
import { PARTNER, allocationRegions, b2b, commercialRowDirect, commercialRowRepor, commercialRowsEtapa16, partnersPage, partnerSummary } from './fixtures';
import { setViewport } from './setup';
import { mockApi, renderApp } from './utils';

const directSummary = { ...partnerSummary, code: 'E-commerce', name: 'E-commerce sintético', channel: 'Venda direta', visibility_source: 'faturamento_direto' as const, coverage: 0,
  action_counts: { ...partnerSummary.action_counts, avaliar_reposicao: 0, dados_insuficientes: 0, canal_direto: 4 }, quality_counts: { sufficient: 4, stale: 0, insufficient: 0 } };
const matrix = (items: typeof commercialRowsEtapa16.items) => render(<MemoryRouter><CommercialMatrix response={{ ...commercialRowsEtapa16, items, total: items.length }} /></MemoryRouter>);

describe('carteira: fonte da visibilidade', () => {
  it('canal direto mostra "venda direta" em vez de 0% e parceiro mostra a cobertura do sell-out', async () => {
    mockApi({ partners: { ...partnersPage, items: [partnerSummary, directSummary], total: 2 } });
    renderApp('/carteira');
    const table = await screen.findByRole('region', { name: /Parceiros; role horizontalmente/ });
    const direct = within(table).getByText('E-commerce sintético').closest('tr')!;
    expect(within(direct).getByText('Venda direta')).toBeInTheDocument();
    expect(within(direct).getByText('observada no faturamento')).toBeInTheDocument();
    expect(direct.textContent).not.toMatch(/0%/);
    const partner = within(table).getByText('Parceiro sintético').closest('tr')!;
    expect(within(partner).getByText('25%')).toBeInTheDocument();
    expect(within(partner).getByText('sell-out do parceiro')).toBeInTheDocument();
  });

  it('mostra o mapa da jornada com o observado e o sem visibilidade', async () => {
    mockApi();
    renderApp('/carteira');
    expect(await screen.findByText(/Últimos 3 meses/)).toHaveTextContent('70,0% do faturado tem venda ao consumidor observada; 30,0% está sem visibilidade');
    expect(screen.getByRole('img', { name: 'Observado 70,0%, sem visibilidade 30,0%' })).toBeInTheDocument();
  });

  it('a página do canal direto explica a fonte, sem cobertura de sell-out', async () => {
    mockApi({ partnerDetail: { partner: directSummary, decisions: { attribution_available: false, items: null, reason: '' }, reference_month: '2026-08', limitation: '', thresholds: {}, field_nature: {} } });
    renderApp('/parceiros/E-commerce');
    expect(await screen.findByText(/observada pelo faturamento/)).toBeInTheDocument();
    expect(screen.queryByText(/Cobertura de dados de sell-out/)).not.toBeInTheDocument();
  });
});

describe('VisibilityJourney', () => {
  it('separa a fonte de cada tipo de canal e rotula o sem visibilidade como calculado', () => {
    render(<VisibilityJourney journey={b2b.journey!} />);
    const table = screen.getByRole('region', { name: /Visibilidade por tipo de canal/ });
    const direct = within(table).getByText('Canal direto').closest('tr')!;
    expect(within(direct).getByText('Venda direta (faturamento)')).toBeInTheDocument();
    expect(within(direct).getByText('100,0%')).toBeInTheDocument();
    expect(within(table).getByText('Sell-out do parceiro')).toBeInTheDocument();
    expect(screen.getByText(/calculado: faturado − venda ao consumidor observada/)).toBeInTheDocument();
  });

  it('avisa quando o sell-out informado passou do faturado e não inventa percentual sem faturamento', () => {
    const journey = { ...b2b.journey!, by_channel_type: [{ ...b2b.journey!.by_channel_type[1], exceeds_billing: true, observed_consumer_units_raw: 450 }] };
    const { rerender } = render(<VisibilityJourney journey={journey} />);
    expect(screen.getByText(/450 un., acima do faturado/)).toBeInTheDocument();
    rerender(<VisibilityJourney journey={{ ...journey, total_units: 0, observed_consumer_units: 0, without_visibility_units: 0 }} />);
    expect(screen.getByText('Sem faturamento na janela.')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});

describe('RegionRisk', () => {
  it('lista as regiões e não transforma preço ausente em R$ 0', () => {
    render(<RegionRisk data={allocationRegions} />);
    const row = screen.getByText('Sul').closest('tr')!;
    expect(within(row).getByText('300 un.')).toBeInTheDocument();
    expect(within(row).getByText('Não disponível')).toBeInTheDocument();
    expect(row.textContent).not.toMatch(/R\$\s?0/);
  });

  it('aparece na página de oportunidades', async () => {
    mockApi();
    renderApp('/parceiros');
    expect(await screen.findByRole('region', { name: /Risco por região/ })).toBeInTheDocument();
  });
});

describe('matriz: projeção, canal direto e pedido de sell-out', () => {
  it('linha Repor mostra a quantidade estimada e a evidência rotula a projeção como estimada', async () => {
    const user = userEvent.setup();
    matrix([commercialRowRepor, { ...commercialRowRepor, partner: 'OUTRO', sku: 'TEST-009' }]);
    expect(screen.getAllByText('Repor 85 un. · estimado')).toHaveLength(2);
    await user.click(screen.getAllByRole('button', { name: /Evidências de .* TEST-003/ })[0]);
    const evidence = document.querySelector('.evidence-body')!;
    expect(evidence).toHaveTextContent('Projeção (estimada)');
    expect(evidence).toHaveTextContent(/acaba em cerca de 12 dias/);
    expect(evidence).toHaveTextContent(/erro do sell-out 26%/);
    expect(evidence).toHaveTextContent('não autoriza envio');
  });

  it('linha sem projeção não mostra quantidade', () => {
    matrix([{ ...commercialRowRepor, forward_projection: null }, { ...commercialRowRepor, sku: 'TEST-009', forward_projection: { ...commercialRowRepor.forward_projection!, status: 'insufficient_data', replenishment_to_target: null } }]);
    expect(screen.queryByText(/Repor \d/)).not.toBeInTheDocument();
  });

  it('canal direto não mostra estoque nem cobertura como dado ausente', async () => {
    const user = userEvent.setup();
    matrix([commercialRowDirect, { ...commercialRowDirect, partner: 'Marketplace', partner_name: 'Marketplace sintético' }]);
    expect(screen.getAllByText('Sem estoque no canal')).toHaveLength(2);
    expect(screen.getAllByText('Não se aplica')).toHaveLength(2);
    expect(screen.queryByText('Não disponível')).not.toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: /Evidências de E-commerce/ })[0]);
    const evidence = document.querySelector('.evidence-body')!;
    expect(evidence).toHaveTextContent('Vendido ao consumidor (faturamento)');
    expect(evidence).not.toHaveTextContent('Enviado (sell-in)');
  });

  it('linha com pedido de sell-out mostra a marca e o motivo na evidência', async () => {
    const user = userEvent.setup();
    const base = commercialRowsEtapa16.items[0];
    const request = { ...base, challenge_action: { ...base.challenge_action!, code: 'investigar' as const, signals_used: ['SELL_OUT_REQUEST'] } };
    matrix([request, { ...request, sku: 'TEST-009' }]);
    expect(screen.getAllByText('Pedir sell-out')).toHaveLength(2);
    await user.click(screen.getAllByRole('button', { name: /Evidências de/ })[0]);
    expect(document.querySelector('.evidence-body')).toHaveTextContent('Pedir sell-out ao parceiro: 120 un. em pedidos sem cobertura');
  });

  it('no celular o cartão traz a quantidade estimada', () => {
    setViewport('mobile');
    matrix([commercialRowRepor]);
    expect(screen.getByText('Repor 85 un. · estimado')).toBeInTheDocument();
  });
});

describe('detalhe do parceiro', () => {
  it('mostra a ação "Venda direta observada" nas linhas de canal direto', async () => {
    mockApi({ partnerSkus: commercialRowsEtapa16 });
    renderApp(`/parceiros/${encodeURIComponent(PARTNER)}`);
    expect(await screen.findByText('Venda direta observada', { selector: '.commercial-action' })).toBeInTheDocument();
  });
});
