import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { opportunityOrders, sortOpportunities, sortPartnerRows } from '../components/CommercialMatrix';
import type { CommercialRow } from '../types-commercial';
import { PARTNER, commercialRow, partnerRows } from './fixtures';
import { setViewport } from './setup';
import { currentLocation, mockApi, renderApp } from './utils';

const row = (partner: string, sku: string, over: Partial<CommercialRow> = {}): CommercialRow => ({
  ...commercialRow, partner, partner_name: `Parceiro ${partner}`, sku, product: `Produto ${sku}`, action: 'avaliar_reposicao', action_label: 'Avaliar reposição',
  data_quality: 'sufficient', estimated_stock: 10, average_monthly_sell_out: 20, coverage_days: 15, ...over,
});

const ROWS = [
  row('B', 'S-2', { coverage_days: 30, average_monthly_sell_out: 50 }),
  row('A', 'S-1', { coverage_days: 5, average_monthly_sell_out: 10 }),
  row('C', 'S-3', { coverage_days: 5, average_monthly_sell_out: 80 }),
  row('D', 'S-4', { coverage_days: null, average_monthly_sell_out: 99 }),
  row('E', 'S-5', { coverage_days: 5, average_monthly_sell_out: 80 }),
];
const page = (items: CommercialRow[], total = items.length) => ({ ...partnerRows, items, total });
const skuOrder = () => within(screen.getByRole('region', { name: /Matriz comercial/ })).getAllByRole('link').filter((link) => link.getAttribute('href')?.startsWith('/skus/')).map((link) => link.textContent);

describe('oportunidades: ordem por urgência', () => {
  it('menor cobertura primeiro, maior giro no desempate, parceiro e SKU por último, e ausente por último', () => {
    expect(sortOpportunities(ROWS, 'urgencia').map((item) => item.sku)).toEqual(['S-3', 'S-5', 'S-1', 'S-2', 'S-4']);
    expect(sortOpportunities(ROWS, 'giro').map((item) => item.sku)).toEqual(['S-4', 'S-3', 'S-5', 'S-2', 'S-1']);
    expect(sortOpportunities(ROWS, 'parceiro').map((item) => item.partner)).toEqual(['A', 'B', 'C', 'D', 'E']);
    expect(Object.keys(opportunityOrders)).toEqual(['urgencia', 'giro', 'parceiro']);
  });

  it('o detalhe do parceiro mostra ações e insuficiências antes dos demais SKUs', () => {
    const rows = [row('P', 'MON', { action: 'monitorar_estoque', coverage_days: 1 }), row('P', 'INS', { action: 'dados_insuficientes', data_quality: 'insufficient', coverage_days: null }), row('P', 'ACT', { coverage_days: 40 })];
    expect(sortPartnerRows(rows).map((item) => item.sku)).toEqual(['ACT', 'INS', 'MON']);
  });

  it('a primeira linha da página é a mais urgente e a ordem escolhida vai para a URL', async () => {
    const user = userEvent.setup();
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros');
    await screen.findByRole('region', { name: /Matriz comercial/ });
    expect(skuOrder()).toEqual(['S-3', 'S-5', 'S-1', 'S-2', 'S-4']);
    await user.selectOptions(screen.getByLabelText('Ordenar'), 'giro');
    expect(currentLocation()).toBe('/parceiros?ordem=giro');
    expect(skuOrder()).toEqual(['S-4', 'S-3', 'S-5', 'S-2', 'S-1']);
  });

  it('ordem de outra visão ou inválida cai na urgência', async () => {
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros?ordem=coverage');
    await screen.findByRole('region', { name: /Matriz comercial/ });
    expect(screen.getByLabelText('Ordenar')).toHaveValue('urgencia');
  });

  it('avisa que a ordem vale só para o lote carregado quando há mais oportunidades', async () => {
    mockApi({ commercial: page(ROWS, 450) });
    renderApp('/parceiros');
    expect(await screen.findByText('Ordenação do primeiro lote')).toBeInTheDocument();
  });
});

describe('oportunidades: busca', () => {
  it('busca por parceiro, SKU e produto e grava na URL', async () => {
    const user = userEvent.setup();
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros?busca=S-3');
    await screen.findByRole('region', { name: /Matriz comercial/ });
    expect(screen.getByLabelText('Buscar')).toHaveValue('S-3');
    expect(skuOrder()).toEqual(['S-3']);
    await user.clear(screen.getByLabelText('Buscar'));
    await user.type(screen.getByLabelText('Buscar'), 'parceiro b');
    expect(currentLocation()).toContain('busca=parceiro+b');
    expect(skuOrder()).toEqual(['S-2']);
    await user.clear(screen.getByLabelText('Buscar'));
    await user.type(screen.getByLabelText('Buscar'), 'produto s-4');
    expect(skuOrder()).toEqual(['S-4']);
  });

  it('mostra a contagem de resultados e estado vazio', async () => {
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros?busca=nao-existe');
    expect(await screen.findByText('Nenhum vínculo neste recorte')).toBeInTheDocument();
    expect(within(document.querySelector('.filter-count') as HTMLElement).getByText('0')).toBeInTheDocument();
  });
});

describe('oportunidades: linhas', () => {
  it('rótulo igual em todas as linhas aparece uma vez, e a evidência de cada linha continua acessível', async () => {
    const user = userEvent.setup();
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros');
    const region = await screen.findByRole('region', { name: /Matriz comercial/ });
    expect(screen.getAllByText('Repor', { selector: '.badge' })).toHaveLength(1);
    expect(within(region).queryByText('Repor')).not.toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: /Evidências de/ })[0]);
    expect(screen.getByText(/Rótulo Repor:/)).toBeInTheDocument();
  });

  it('só uma evidência fica aberta por vez', async () => {
    const user = userEvent.setup();
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros');
    await screen.findByRole('region', { name: /Matriz comercial/ });
    const buttons = () => screen.getAllByRole('button', { name: /Evidências de/ });
    await user.click(buttons()[0]);
    await user.click(buttons()[1]);
    expect(screen.getAllByText(/Por que esta sugestão/)).toHaveLength(1);
    expect(buttons().filter((button) => button.getAttribute('aria-expanded') === 'true')).toHaveLength(1);
    expect(buttons()[1]).toHaveAttribute('aria-expanded', 'true');
  });

  it('usa "cobertura de estoque" para dias e "cobertura de dados de sell-out" para a base', async () => {
    const user = userEvent.setup();
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros');
    expect(await screen.findByRole('columnheader', { name: 'Cobertura de estoque (dias)' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Parceiros' }));
    expect(await screen.findByRole('columnheader', { name: 'Visibilidade da venda' })).toBeInTheDocument();
  });
});

describe('oportunidades no celular', () => {
  it('mostra cartões compactos com parceiro e SKU navegáveis, uma evidência por vez e sem tabela', async () => {
    const user = userEvent.setup();
    setViewport('mobile');
    mockApi({ commercial: page(ROWS) });
    renderApp('/parceiros');
    const list = await screen.findByRole('list', { name: 'Oportunidades por parceiro e SKU' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);
    expect(within(list).queryByRole('table')).not.toBeInTheDocument();
    const first = within(list).getAllByRole('listitem')[0];
    expect(within(first).getByRole('link', { name: 'Parceiro C' })).toHaveAttribute('href', '/parceiros/C');
    expect(within(first).getByRole('link', { name: 'S-3' })).toHaveAttribute('href', '/skus/S-3');
    expect(within(first).getByText('Cobertura de estoque')).toBeInTheDocument();
    expect(within(first).queryByText(/Por que esta sugestão/)).not.toBeInTheDocument();
    await user.click(within(first).getByRole('button', { name: /Evidências de C/ }));
    expect(within(first).getByText(/Por que esta sugestão/)).toBeInTheDocument();
    await user.click(within(list).getAllByRole('button', { name: /Evidências de/ })[1]);
    expect(within(list).getAllByText(/Por que esta sugestão/)).toHaveLength(1);
  });

  it('o detalhe do parceiro também usa cartões e começa pelo que pede ação', async () => {
    setViewport('mobile');
    const rows = [row(PARTNER, 'MON', { action: 'monitorar_estoque', coverage_days: 1 }), row(PARTNER, 'ACT', { coverage_days: 40 })];
    mockApi({ partnerSkus: page(rows) });
    renderApp(`/parceiros/${encodeURIComponent(PARTNER)}`);
    const list = await screen.findByRole('list', { name: 'Oportunidades por parceiro e SKU' });
    await waitFor(() => expect(within(list).getAllByRole('listitem')[0]).toHaveTextContent('ACT'));
  });
});
