import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { overview } from './fixtures';
import { fail, mockApi, renderApp } from './utils';

const section = async (title: string) => (await screen.findByRole('heading', { level: 3, name: title })).closest('section') as HTMLElement;

describe('Início: estoque projetado (fase 2)', () => {
  it('falha só na agregação: o gráfico semanal some, sem barras de zero, e os indicadores seguem', async () => {
    mockApi({ overview: { ...overview, projected_stock: null } });
    renderApp('/');
    const list = within(await screen.findByRole('list', { name: 'Indicadores principais' }));
    expect(list.getByText('SKUs com risco de ruptura').nextSibling).toHaveTextContent('2');
    expect(screen.queryByRole('heading', { name: 'SKUs em falta por semana' })).not.toBeInTheDocument();
  });
});

describe('Início: gráficos do painel (fase 4)', () => {
  it('SKUs em falta por semana: duas linhas com eixos, legenda e a frase do pico', async () => {
    mockApi();
    renderApp('/');
    const chart = await section('SKUs em falta por semana');
    const image = within(chart).getByRole('img', { name: /SKUs em falta por semana, sem novas ordens e com o plano/ });
    expect(image.getAttribute('aria-label')).toMatch(/Pico de 2 SKUs em falta na semana de 02\/11 sem novas ordens; com o plano, o pico é de 1 SKU\./);
    expect(within(chart).getByText('Sem novas ordens')).toBeInTheDocument();
    expect(within(chart).getByText('Com o plano')).toBeInTheDocument();
    expect(chart.querySelectorAll('.recharts-line')).toHaveLength(2);
    expect(chart.querySelectorAll('.recharts-xAxis-tick-labels text').length).toBeGreaterThanOrEqual(2);
    expect(chart.querySelectorAll('.recharts-yAxis-tick-labels text').length).toBeGreaterThanOrEqual(2);
    // Vem depois dos indicadores, como o resto do painel.
    expect(screen.getByRole('list', { name: 'Indicadores principais' }).compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('sem falta no horizonte, diz isso em vez de desenhar um pico', async () => {
    const base = overview.projected_stock!;
    mockApi({ overview: { ...overview, projected_stock: { ...base, weekly: base.weekly!.map((week) => ({ ...week, shortfall_sku_count: 0, shortfall_with_plan_sku_count: 0 })) } } });
    renderApp('/');
    const chart = await section('SKUs em falta por semana');
    expect(within(chart).getByText('Nenhum SKU em falta no horizonte, com ou sem novas ordens.')).toBeInTheDocument();
  });

  it('resposta antiga sem a série semanal: o gráfico não aparece e os números seguem', async () => {
    const { weekly: _removed, ...base } = overview.projected_stock!;
    mockApi({ overview: { ...overview, projected_stock: base } });
    renderApp('/');
    expect(await screen.findByRole('list', { name: 'Indicadores principais' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'SKUs em falta por semana' })).not.toBeInTheDocument();
  });

  it('o Início não mostra mais o gráfico de produção planejada; falha do plano só esvazia o cartão', async () => {
    mockApi({ productionPlan: fail(500, 'Erro interno.') });
    renderApp('/');
    expect(await screen.findByText('Plano indisponível agora')).toBeInTheDocument();
    expect(screen.queryByText('Produção planejada indisponível')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Produção planejada por mês' })).not.toBeInTheDocument();
    expect(await section('SKUs em falta por semana')).toBeInTheDocument();
  });
});
