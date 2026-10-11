import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { validationSummary } from './fixtures';
import { mockApi, renderApp } from './utils';

// Etapa 16.7: a Validação mostra o valor em risco endereçado e a divergência modelo × S&OP como pauta de revisão.
const openModels = async () => userEvent.click(await screen.findByRole('tab', { name: 'Modelos de previsão' }));

describe('validação: valor endereçado e pauta S&OP', () => {
  it('mostra o valor observado dos SKUs decididos, sem tratá-lo como valor recuperado', async () => {
    mockApi();
    renderApp('/validacao');
    const card = (await screen.findByText(/Valor em risco endereçado/)).closest('article') as HTMLElement;
    expect(card).toHaveTextContent('R$ 1.875');
    expect(card).toHaveTextContent('em SKUs com decisão registrada');
    expect(within(card).getByRole('tooltip', { hidden: true })).toHaveTextContent('não é dinheiro recuperado');
    expect(within(card).getByRole('tooltip', { hidden: true })).toHaveTextContent('Sem valor calculado: TEST-003');
  });

  it('valor endereçado nulo mostra "Não disponível" com o motivo, nunca R$ 0', async () => {
    mockApi({ validation: { ...validationSummary, addressed_value: { ...validationSummary.addressed_value!, observed_total: null, missing_reason: 'Falha ao ler as decisões registradas.', sku_count: 0, decided_skus: [], skus_without_value: [] } } });
    renderApp('/validacao');
    const card = (await screen.findByText(/Valor em risco endereçado/)).closest('article') as HTMLElement;
    expect(card).toHaveTextContent('Não disponível');
    expect(card).not.toHaveTextContent('R$');
    expect(within(card).getByRole('tooltip', { hidden: true })).toHaveTextContent('Falha ao ler as decisões registradas.');
  });

  it('sem decisão registrada o cartão mostra zero e diz que ainda não há decisão', async () => {
    mockApi({ validation: { ...validationSummary, addressed_value: { ...validationSummary.addressed_value!, observed_total: 0, sku_count: 0, decided_skus: [], skus_without_value: [] } } });
    renderApp('/validacao');
    const card = (await screen.findByText(/Valor em risco endereçado/)).closest('article') as HTMLElement;
    expect(card).toHaveTextContent('R$ 0');
    expect(card).toHaveTextContent('nenhuma decisão registrada ainda');
  });

  it('lista a divergência modelo × S&OP com a ressalva de que nenhum lado é o certo', async () => {
    mockApi();
    renderApp('/validacao');
    await openModels();
    const table = await screen.findByRole('region', { name: /Divergências entre modelo e S&OP/ });
    const row = within(table).getByRole('link', { name: 'TEST-001' }).closest('tr') as HTMLElement;
    expect(row).toHaveTextContent('150');
    expect(row).toHaveTextContent('100');
    expect(row).toHaveTextContent('+50,0%');
    expect(screen.getByText(/O erro do S&OP não é mensurável/)).toBeInTheDocument();
    expect(screen.getByText('Modelo × S&OP: pauta de revisão')).toBeInTheDocument();
  });

  it('mostra só as maiores divergências e deixa o resto sob demanda', async () => {
    const items = Array.from({ length: 13 }, (_, index) => ({ sku: `CI-${index + 1}`, month: '2026-11', model: 100 + index, sop: 100, ratio: (index + 1) / 100 }));
    mockApi({ validation: { ...validationSummary, sop_divergence: { ...validationSummary.sop_divergence!, items, count: 13 } } });
    renderApp('/validacao');
    await openModels();
    const main = await screen.findByRole('region', { name: /Divergências entre modelo e S&OP/ });
    expect(within(main).getAllByRole('row')).toHaveLength(11);
    expect(within(main).getByRole('link', { name: 'CI-13' })).toBeInTheDocument();
    expect(within(main).queryByRole('link', { name: 'CI-1' })).not.toBeInTheDocument();
    const rest = screen.getByRole('region', { name: 'Demais divergências entre modelo e S&OP', hidden: true });
    expect(within(rest).getAllByRole('row', { hidden: true })).toHaveLength(4);
  });

  it('respostas antigas, sem os campos novos, não quebram a tela', async () => {
    const { addressed_value: _a, sop_divergence: _s, ...old } = validationSummary;
    mockApi({ validation: old });
    renderApp('/validacao');
    expect(await screen.findByRole('heading', { level: 2, name: 'Quanto confiar nas recomendações' })).toBeInTheDocument();
    await openModels();
    expect(screen.queryByText(/Valor em risco endereçado/)).not.toBeInTheDocument();
    expect(screen.queryByText('Modelo × S&OP: pauta de revisão')).not.toBeInTheDocument();
  });
});
