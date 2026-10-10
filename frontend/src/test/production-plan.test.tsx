import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { glossary } from '../pages/shared';
import { SKU_OK, productionPlan } from './fixtures';
import { fail, mockApi, pending, renderApp } from './utils';

const card = async () => (await screen.findByRole('heading', { level: 3, name: 'Produção planejada por mês' })).closest('section') as HTMLElement;

describe('Fila operacional: produção planejada por mês', () => {
  it('mostra o total como plano sugerido, com barras agora × depois e descrição acessível', async () => {
    mockApi();
    renderApp('/fila');
    const chart = await card();
    expect(within(chart).getByText('Plano sugerido', { selector: '.badge' })).toBeInTheDocument();
    expect(within(chart).getByRole('button', { name: 'O que é: Produção planejada' })).toBeInTheDocument();
    expect(within(chart).getByText('Liberar agora')).toBeInTheDocument();
    expect(within(chart).getByText('Liberar depois')).toBeInTheDocument();
    const image = within(chart).getByRole('img', { name: /Unidades a liberar para produção por mês, Empresa/ });
    expect(image.getAttribute('aria-label')).toMatch(/set\/26: 200 un\. \(200 un\. agora\)/);
    expect(image.getAttribute('aria-label')).toMatch(/Plano sugerido, não ordem liberada/);
    // Barras cheias só nos meses com urgente; tracejadas só nos meses com o resto; mês sem ordens não ganha barra.
    expect(chart.querySelectorAll('.revenue-bar:not(.revenue-bar-estimated)')).toHaveLength(1);
    expect(chart.querySelectorAll('.revenue-bar-estimated')).toHaveLength(2);
    // Eixo X com um mês por barra; eixo Y com valores em unidades.
    expect(chart.querySelectorAll('.recharts-xAxis-tick-labels text.chart-tick')).toHaveLength(productionPlan.total.months.length);
    expect(chart.querySelectorAll('.recharts-yAxis-tick-labels text.chart-tick').length).toBeGreaterThanOrEqual(2);
  });

  it('o total de agora é a soma sugerida da fila e os meses omitidos aparecem na tela', async () => {
    mockApi();
    renderApp('/fila');
    const chart = await card();
    const facts = chart.querySelector('.fact-line') as HTMLElement;
    expect(within(facts).getByText('200 un.')).toBeInTheDocument();
    expect(facts.textContent).toMatch(/600 un\. no horizonte/);
    expect(facts.textContent).toMatch(/jan, fev fora do gráfico/);
    const trigger = within(chart).getByRole('button', { name: 'Unidades por mês de liberação' });
    const tooltip = document.getElementById(trigger.getAttribute('aria-describedby') ?? '') as HTMLElement;
    expect(tooltip.textContent).toMatch(/o prazo de produção passa do fim da previsão/);
    expect(tooltip.textContent).toMatch(/1 SKU sem previsão fora da soma/);
  });

  it('segue o filtro de família da fila', async () => {
    mockApi();
    renderApp('/fila?familia=Fam%C3%ADlia%20A');
    const chart = await card();
    expect(within(chart).getByRole('img', { name: /Família A/ })).toBeInTheDocument();
    expect(within(chart).getByText('200 un.')).toBeInTheDocument();
  });

  it('família sem plano diz que não há ordens, sem barras de zero', async () => {
    mockApi();
    renderApp('/fila?familia=Fam%C3%ADlia%20B');
    const chart = await card();
    expect(within(chart).getByText(/Sem ordens planejadas para Família B/)).toBeInTheDocument();
    expect(within(chart).queryByRole('img')).not.toBeInTheDocument();
    expect(chart.textContent).not.toMatch(/0 un\./);
  });

  it('falha do plano mostra aviso com nova tentativa e a fila continua', async () => {
    mockApi({ productionPlan: fail(500, 'Erro interno.') });
    renderApp('/fila');
    expect(await screen.findByText('Produção planejada indisponível')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` })).toBeInTheDocument();
  });

  it('enquanto calcula, a fila já aparece', async () => {
    mockApi({ productionPlan: pending() });
    renderApp('/fila');
    expect(await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` })).toBeInTheDocument();
    expect(within(await card()).getByText('Calculando…')).toBeInTheDocument();
  });

  it('o "?" diz que é plano sugerido por mês de liberação e que ausência não vira zero', () => {
    expect(glossary.producao_planejada.text).toMatch(/mês em que a produção precisa começar \(liberação\)/);
    expect(glossary.producao_planejada.text).toMatch(/plano sugerido, não OP liberada/);
    expect(glossary.producao_planejada.text).toMatch(/nunca vira zero/);
  });
});
