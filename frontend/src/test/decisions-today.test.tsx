import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { overview } from './fixtures';
import { mockApi, renderApp } from './utils';

const section = async () => (await screen.findByRole('heading', { level: 3, name: 'Decisões de hoje' })).closest('section') as HTMLElement;

describe('Início: Decisões de hoje', () => {
  it('lista o que decidir, até quando e em qual SKU, em três colunas, com o motivo no "?"', async () => {
    mockApi();
    renderApp('/');
    const block = await section();
    expect(within(block).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Decidir até', 'SKU', 'Decisão']);
    const rows = within(block).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('15/09/2026');
    expect(rows[0]).toHaveTextContent('Priorizar parceiro · Alocar estoque');
    expect(within(rows[0]).getByRole('link', { name: 'TEST-001' })).toHaveAttribute('href', '/skus/TEST-001');
    expect(within(rows[0]).getByRole('tooltip', { hidden: true })).toHaveTextContent('Atender KA-T1 antes de KA-T2');
    expect(within(rows[1]).getByRole('tooltip', { hidden: true })).toHaveTextContent('Antecipar OP-T3');
    expect(within(block).getByRole('link', { name: 'Ver a fila' })).toHaveAttribute('href', '/fila');
  });

  it('ordena pelo prazo e mostra só as cinco mais próximas, dizendo o total', async () => {
    const base = overview.decisions_today!.items[0];
    const items = Array.from({ length: 7 }, (_, index) => ({ ...base, sku: `TEST-${100 + index}`, decide_by: `2026-09-${20 - index}` }));
    mockApi({ overview: { ...overview, decisions_today: { window_end: '2026-09-21', count: 26, items } } });
    renderApp('/');
    const block = await section();
    const rows = within(block).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(5);
    expect(rows[0]).toHaveTextContent('TEST-106');
    expect(within(block).getByText(/26 no total/)).toBeInTheDocument();
  });

  it('janela sem decisão explica em vez de listar; sem o campo, o bloco não aparece', async () => {
    mockApi({ overview: { ...overview, decisions_today: { window_end: '2026-09-21', count: 0, items: [] } } });
    const { unmount } = renderApp('/');
    expect(await screen.findByText('Nenhuma decisão com prazo até 21/09/2026.')).toBeInTheDocument();
    unmount();
    mockApi({ overview: { ...overview, decisions_today: null } });
    renderApp('/');
    await screen.findByRole('list', { name: 'Indicadores principais' });
    expect(screen.queryByRole('heading', { name: 'Decisões de hoje' })).not.toBeInTheDocument();
  });
});
