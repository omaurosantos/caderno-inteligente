import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SKU_OK, SKU_SHORT, directChannels, revenueForecast, revenueOk } from './fixtures';
import { fail, mockApi, renderApp } from './utils';

const cards = async () => within(await screen.findByRole('list', { name: 'Indicadores principais' }));
const card = (list: ReturnType<typeof within>, label: string) => list.getByText(label).closest('a') as HTMLElement;

describe('Início: cartões de indicadores', () => {
  it('mostra os quatro indicadores com valores da API e o link de cada um', async () => {
    mockApi();
    renderApp('/');
    const list = await cards();
    const revenue = card(list, 'Faturamento previsto');
    expect(await within(revenue).findByText(/\+37,5%/)).toBeInTheDocument();
    expect(revenue).toHaveAttribute('href', '/faturamento');
    const rupture = card(list, 'SKUs com risco de ruptura');
    expect(within(rupture).getByText('2 abaixo do prazo · 1 abaixo da segurança')).toBeInTheDocument();
    expect(rupture).toHaveAttribute('href', '/fila?sinal=ruptura');
    const production = card(list, 'Produção para liberar agora');
    expect(await within(production).findByText('200 un.')).toBeInTheDocument();
    expect(within(production).getByText('600 un. no horizonte')).toBeInTheDocument();
    expect(card(list, 'Pedidos sem ordem de produção')).toHaveAttribute('href', '/fila');
  });

  it('faturamento que falha diz indisponível no cartão, sem virar R$ 0, e o restante segue', async () => {
    mockApi({ revenueForecast: fail(500, 'Erro interno.') });
    renderApp('/');
    const list = await cards();
    expect(await list.findByText('Estimativa indisponível agora')).toBeInTheDocument();
    expect(list.queryByText(/R\$\s0/)).not.toBeInTheDocument();
    expect(await list.findByText('200 un.')).toBeInTheDocument();
  });
});

describe('Início: SKUs com maior faturamento previsto', () => {
  it('ordena pelo faturamento previsto e deixa de fora o SKU sem previsão, nunca como zero', async () => {
    mockApi({ revenueForecast: { ...revenueForecast, items: [...revenueForecast.items, { ...revenueOk, sku: 'TEST-BIG', product: 'Produto grande', revenue_total_3m: 9000 }] } });
    renderApp('/');
    const image = await screen.findByRole('img', { name: /SKUs com maior faturamento previsto nos próximos três meses/ });
    const label = image.getAttribute('aria-label') ?? '';
    expect(label.indexOf('TEST-BIG')).toBeLessThan(label.indexOf(SKU_OK));
    expect(label).not.toMatch(new RegExp(SKU_SHORT));
    expect(within(image.closest('section') as HTMLElement).getByRole('link', { name: 'Ver o financeiro' })).toHaveAttribute('href', '/faturamento');
  });

  it('o faturamento é lido uma vez para cartões, pizza e ranking', async () => {
    const api = mockApi();
    renderApp('/');
    await screen.findByRole('img', { name: /SKUs com maior faturamento previsto/ });
    expect(api.gets().filter((path) => path === '/api/revenue-forecast')).toHaveLength(1);
  });
});

describe('Início: faturamento por canal direto', () => {
  it('ordena os canais pelo faturamento observado, com a parte de cada um e o link para os canais', async () => {
    mockApi();
    renderApp('/');
    const image = await screen.findByRole('img', { name: /Faturamento observado dos canais diretos nos últimos 24 meses/ });
    const label = image.getAttribute('aria-label') ?? '';
    expect(label.indexOf('E-commerce próprio')).toBeLessThan(label.indexOf('Loja própria'));
    expect(label).toMatch(/E-commerce próprio: R\$\s11\.606\.120 em 24 meses · 28% do faturamento total/);
    expect(within(image.closest('section') as HTMLElement).getByRole('link', { name: 'Ver os canais' })).toHaveAttribute('href', '/canais');
  });

  it('canal sem faturamento observado fica de fora e é avisado', async () => {
    mockApi({ directChannels: { ...directChannels, channels: [directChannels.channels[0], { ...directChannels.channels[1], revenue_24m: null, share_of_revenue: null }] } });
    renderApp('/');
    expect(await screen.findByText('1 canal sem faturamento observado fica de fora.')).toBeInTheDocument();
    const label = (await screen.findByRole('img', { name: /Faturamento observado dos canais diretos/ })).getAttribute('aria-label') ?? '';
    expect(label).not.toMatch(/Loja própria/);
  });
});

describe('Início: pizza do faturamento previsto por família', () => {
  it('mostra a pizza com a tabela de valores; família sem estimativa fica de fora, nunca como zero', async () => {
    mockApi();
    renderApp('/');
    expect(await screen.findByRole('img', { name: /Faturamento previsto por família nos próximos três meses\. Família A/ })).toBeInTheDocument();
    const table = screen.getByRole('region', { name: 'Faturamento previsto por família, valores' });
    expect(within(table).getByText('Família A')).toBeInTheDocument();
    expect(within(table).getByText('100%')).toBeInTheDocument();
    expect(within(table).queryByText('Família B')).not.toBeInTheDocument();
    expect(screen.getByText(/1 família sem estimativa fica de fora/)).toBeInTheDocument();
  });

  it('sem nenhuma família com estimativa, explica em vez de desenhar', async () => {
    mockApi({ revenueForecast: { ...revenueForecast, families: revenueForecast.families.map((group) => ({ ...group, revenue_total_3m: null })) } });
    renderApp('/');
    expect(await screen.findByText('Nenhuma família com estimativa')).toBeInTheDocument();
  });
});
