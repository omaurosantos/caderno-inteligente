import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { evidenceText, factorText, mainAlert } from '../components/EventAlerts';
import { glossary } from '../pages/shared';
import { SKU_OK, SKU_SHORT, eventAlerts, eventScenario, skuDetailOk } from './fixtures';
import { fail, mockApi, renderApp } from './utils';

describe('formatos de evento', () => {
  it('formata fator e evidência sem inventar fator quando não há histórico', () => {
    expect(factorText(1.35)).toBe('×1,35');
    expect(factorText(null)).toBe('Sem fator');
    expect(evidenceText(eventAlerts[1].evidence)).toBe('×1,35 · 2 ocorrências');
    expect(evidenceText(eventAlerts[0].evidence)).toBe('Sem histórico direto');
    expect(evidenceText({ ...eventAlerts[1].evidence, occurrences: 1, capped: true })).toBe('×1,35 · 1 ocorrência (limitado)');
  });

  it('escolhe o alerta no horizonte que começa primeiro', () => {
    expect(mainAlert(eventAlerts)?.event).toBe('Lançamento Coleção Teste');
    expect(mainAlert([eventAlerts[2], eventAlerts[1]])?.event).toBe('Black Friday');
    expect(mainAlert([])).toBeUndefined();
  });

  it('a explicação do "?" avisa que é estimativa e que não substitui a previsão', () => {
    expect(glossary.cenario_evento.text).toMatch(/estimativa indicativa/);
    expect(glossary.cenario_evento.text).toMatch(/não substitui a previsão nem a quantidade oficial/);
    expect(glossary.cenario_evento.text).toMatch(/sazonal de 12 meses/);
  });
});

describe('Fila operacional: selo de evento por SKU', () => {
  it('mostra o evento mais urgente e quantos outros existem, sem tirar a ação operacional', async () => {
    mockApi();
    renderApp('/fila?todos=1');
    const table = await screen.findByRole('region', { name: /Fila operacional; role horizontalmente/ });
    const row = within(table).getByText(SKU_OK).closest('tr') as HTMLElement;
    expect(within(row).getByText('Evento: Lançamento Coleção Teste +2')).toBeInTheDocument();
    expect(within(row).getByText('Produzir')).toBeInTheDocument();
    const shortRow = within(table).getByText(SKU_SHORT).closest('tr') as HTMLElement;
    expect(within(shortRow).queryByText(/Evento:/)).not.toBeInTheDocument();
  });

  it('falha do calendário não bloqueia a fila operacional', async () => {
    mockApi({ events: fail(500, 'Erro interno.') });
    renderApp('/fila?todos=1');
    const table = await screen.findByRole('region', { name: /Fila operacional; role horizontalmente/ });
    expect(within(table).getByText(SKU_OK)).toBeInTheDocument();
    expect(within(table).queryByText(/Evento:/)).not.toBeInTheDocument();
  });
});

describe('Detalhe do SKU: eventos e sazonalidade', () => {
  const block = async () => (await screen.findByRole('heading', { level: 4, name: 'Eventos e sazonalidade' })).closest('.event-section') as HTMLElement;

  it('mostra alertas com data de decisão e evidência, e o cenário rotulado como estimativa', async () => {
    mockApi();
    renderApp(`/skus/${SKU_OK}?tab=evidencias`);
    const details = await block();
    const alerts = within(details).getByRole('region', { name: 'Eventos que afetam este SKU' });
    const friday = within(alerts).getByText('Black Friday').closest('tr') as HTMLElement;
    expect(within(friday).getByText('06/11/2026')).toBeInTheDocument();
    expect(within(friday).getByText('×1,35 · 2 ocorrências')).toBeInTheDocument();
    const launch = within(alerts).getByText('Lançamento Coleção Teste').closest('tr') as HTMLElement;
    expect(within(launch).getByText('Sem histórico direto')).toBeInTheDocument();
    expect(within(launch).queryByText(/×\d/)).not.toBeInTheDocument();

    expect(within(details).getAllByText('Estimativa', { selector: '.badge' }).length).toBe(2);
    expect(within(details).getByRole('button', { name: 'O que é: Cenário com evento' })).toBeInTheDocument();
    const scenario = within(details).getByRole('region', { name: 'Cenário com evento' });
    expect(within(scenario).getAllByRole('row')).toHaveLength(1 + eventScenario.months.length);
    expect(within(scenario).getByText('×1,35')).toBeInTheDocument();
    expect(within(scenario).getAllByText('—')).toHaveLength(2);
    expect(within(details).getByText(/A quantidade oficial não é alterada/)).toBeInTheDocument();
  });

  it('sem histórico a evidência é explicada no tooltip, sem fator', async () => {
    mockApi();
    renderApp(`/skus/${SKU_OK}?tab=evidencias`);
    const details = await block();
    const tips = within(details).getAllByRole('tooltip', { hidden: true }).map((node) => node.textContent);
    expect(tips.some((text) => text?.includes('o calendário indica impacto, a evidência não'))).toBe(true);
    expect(tips.some((text) => text?.includes('nenhum fator é estimado'))).toBe(true);
  });

  it('SKU sem previsão não ganha cenário e diz o motivo', async () => {
    const detail = { ...skuDetailOk, event_alerts: [], event_scenario: { applicable: false, note: 'Sem previsão de unidades; não há como montar cenário.', scenario: null } };
    mockApi({ skuDetail: detail });
    renderApp(`/skus/${SKU_OK}?tab=evidencias`);
    expect(await screen.findByText('Riscos e evidências')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 4, name: 'Eventos e sazonalidade' })).not.toBeInTheDocument();
  });

  it('previsão sazonal mostra o alerta e explica por que não há cenário', async () => {
    const note = 'A previsão já incorpora a sazonalidade do ano anterior (modelo sazonal de 12 meses); não há cenário, para não contar duas vezes.';
    mockApi({ skuDetail: { ...skuDetailOk, event_scenario: { applicable: false, note, scenario: null } } });
    renderApp(`/skus/${SKU_OK}?tab=evidencias`);
    const details = await block();
    expect(within(details).getByText(note)).toBeInTheDocument();
    expect(within(details).queryByRole('region', { name: 'Cenário com evento' })).not.toBeInTheDocument();
    expect(within(details).getByRole('region', { name: 'Eventos que afetam este SKU' })).toBeInTheDocument();
  });

  it('resposta antiga sem os campos não quebra e análise indisponível (null) mantém a previsão', async () => {
    const old = { ...skuDetailOk } as Record<string, unknown>;
    delete old.event_alerts; delete old.event_scenario;
    mockApi({ skuDetail: old });
    const { unmount } = renderApp(`/skus/${SKU_OK}?tab=evidencias`);
    expect(await screen.findByText('Riscos e evidências')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 4, name: 'Eventos e sazonalidade' })).not.toBeInTheDocument();
    unmount();
    mockApi({ skuDetail: { ...skuDetailOk, event_alerts: null, event_scenario: null } });
    renderApp(`/skus/${SKU_OK}?tab=evidencias`);
    expect(await screen.findByText(/Análise de eventos indisponível no momento/)).toBeInTheDocument();
    expect(screen.getByText('Sobre a previsão')).toBeInTheDocument();
  });
});
