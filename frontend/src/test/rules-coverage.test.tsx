import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { rulesCoverage } from './fixtures';
import { fail, mockApi, renderApp } from './utils';

// Etapa 16.6: Bastidores › Auditoria mostra quantas vezes cada regra dispara e por que os zeros são zeros.
describe('cobertura de regras na Auditoria', () => {
  it('mostra disparos por regra e rótulo e resume quantos zeros foram explicados', async () => {
    const api = mockApi();
    renderApp('/auditoria');
    const summary = await screen.findByText('Cobertura das regras', { selector: 'summary' });
    expect(summary).toHaveTextContent('2 de 3 disparam na base atual; 1 em zero, todos explicados');
    expect(summary.closest('details')).toHaveAttribute('open');
    const signals = await screen.findByRole('region', { name: 'Sinais do ranking' });
    expect(within(signals).getByText('Cobertura abaixo do lead time').closest('tr')).toHaveTextContent('2');
    const labels = screen.getByRole('region', { name: 'Rótulos de ação' });
    expect(within(labels).getByText('Produzir').closest('tr')).toHaveTextContent('SKU 1');
    expect(api.gets()).toContain('/api/rules/coverage');
  });

  it('explica o zero com motivo, dado necessário e caso de referência sintético', async () => {
    mockApi();
    renderApp('/auditoria');
    const labels = await screen.findByRole('region', { name: 'Rótulos de ação' });
    const row = within(labels).getByText('Ampliar mix').closest('tr') as HTMLElement;
    expect(row).toHaveTextContent('Faturamento sem lacunas em 4 de 4 pares canal × SKU.');
    expect(row).toHaveTextContent('Dado necessário: SKU ativo sem faturamento em um canal direto nos 24 meses.');
    expect(row).toHaveTextContent('sintético');
    expect(row).toHaveTextContent('VC-T1: Ampliar mix sintético');
    expect(row).toHaveClass('is-zero');
  });

  it('zero sem motivo registrado aparece como tal, nunca em branco', async () => {
    const [first, ...rest] = rulesCoverage.rules;
    const unexplained = { ...rulesCoverage.rules[2], rule: 'reativar', label: 'Reativar', zero_reason: null, data_needed: null, reference_case: null };
    mockApi({ rulesCoverage: { ...rulesCoverage, rules: [first, ...rest, unexplained] } });
    renderApp('/auditoria');
    const labels = await screen.findByRole('region', { name: 'Rótulos de ação' });
    expect(within(labels).getByText('Reativar').closest('tr')).toHaveTextContent('Sem motivo registrado para o zero; verificar.');
    expect(screen.getByText('Cobertura das regras', { selector: 'summary' })).toHaveTextContent('1 sem motivo');
  });

  it('lista a precedência dos rótulos e lembra que a revisão é humana', async () => {
    mockApi();
    renderApp('/auditoria');
    const precedence = await screen.findByRole('region', { name: 'Precedência dos rótulos' });
    expect(within(precedence).getByText('investigar (dado insuficiente)')).toBeInTheDocument();
    expect(screen.getByText(/Caso de referência sintético comprova a regra/)).toBeInTheDocument();
    expect(screen.getByText('revisão humana')).toBeInTheDocument();
  });

  it('a Auditoria continua disponível se a cobertura falhar', async () => {
    mockApi({ rulesCoverage: fail(500, 'indisponível') });
    renderApp('/auditoria');
    expect(await screen.findByText('Casos de teste congelados', { selector: 'summary' })).toBeInTheDocument();
    expect(screen.queryByText('Cobertura das regras', { selector: 'summary' })).not.toBeInTheDocument();
  });

  it('lista os pedidos de sell-out recolhidos, do maior valor ao menor, com valor ausente por último', async () => {
    mockApi();
    renderApp('/auditoria');
    const summary = await screen.findByText(/Sell-out a pedir aos parceiros \(2 pares\)/, { selector: 'summary' });
    expect(summary.closest('details')).not.toHaveAttribute('open');
    const table = screen.getByRole('region', { name: 'Pedidos de sell-out', hidden: true });
    const rows = within(table).getAllByRole('row', { hidden: true }).slice(1);
    expect(rows[0]).toHaveTextContent('KA-T1');
    expect(rows[0]).toHaveTextContent('R$ 1.500');
    expect(rows[1]).toHaveTextContent('KA-T2');
    expect(rows[1]).toHaveTextContent('Não disponível');
  });
});
