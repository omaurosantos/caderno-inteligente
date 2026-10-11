import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AllocationBlock } from '../components/AllocationBlock';
import { ChallengeBadge, ChallengeLever } from '../components/ChallengeAction';
import { SKU_OK, SKU_SHORT, allocationContested, allocationNoPrice, challengeAllocate, challengeInvestigate } from './fixtures';
import { mockApi, renderApp } from './utils';

const tipOf = (trigger: HTMLElement) => document.getElementById(trigger.getAttribute('aria-describedby') ?? '')?.textContent ?? '';

describe('bloco "Quem atender primeiro"', () => {
  it('a frase da decisão é exibida como veio, sem ponto final acrescentado', () => {
    render(<AllocationBlock allocation={allocationContested} />);
    const text = screen.getByText(/^Atender KA-T1 \(120 un\.\) integralmente/);
    expect(text.textContent).toBe(allocationContested.decision_text);
    expect(text.closest('p')?.textContent).toBe(allocationContested.decision_text);
  });

  it('uma linha por pedido na ordem sugerida, com a decisão, o descoberto e a limitação', () => {
    render(<AllocationBlock allocation={allocationContested} />);
    expect(screen.getByText('Quem atender primeiro', { selector: 'summary' })).toBeInTheDocument();
    expect(screen.getByText(/^Atender KA-T1 \(120 un\.\) integralmente; KA-T2 recebe 50 un\. agora/)).toBeInTheDocument();
    const table = screen.getByRole('region', { name: 'Ordem de atendimento dos pedidos' });
    const rows = within(table).getAllByRole('row').slice(1) as HTMLTableRowElement[];
    expect(rows.map((row) => row.cells[0].textContent)).toEqual(['1º', '2º']);
    expect(rows[0]).toHaveTextContent('KA-T1');
    expect(rows[0]).toHaveTextContent('120 de 120');
    expect(rows[0]).toHaveTextContent('no prazo');
    expect(rows[1]).toHaveTextContent('50 de 200');
    expect(rows[1]).toHaveTextContent('150 em 05/10/2026');
    expect(rows[1]).toHaveTextContent('19 dias');
    expect(within(table).getAllByRole('columnheader')).toHaveLength(5);
    expect(screen.getByText(/Descoberto na data prometida: 150 un\./)).toHaveTextContent(/R\$\s?1\.875/);
    expect(screen.getByText(/não reserva estoque nem altera pedidos/)).toBeInTheDocument();
  });

  it('os componentes da pontuação, com a natureza, e a regra atual ficam no "?" do pedido', () => {
    render(<AllocationBlock allocation={allocationContested} />);
    const tip = tipOf(screen.getByRole('button', { name: 'Por que o pedido PED-T2 está nesta posição' }));
    expect(tip).toContain('PED-T2 · Sul · 200 un. para 16/09/2026');
    expect(tip).toContain('urgência 2,6 (observado');
    expect(tip).toContain('sem sell-out 0 (ausente: Sem dado do parceiro');
    expect(tip).toContain('150 un. em 05/10/2026 (OP-T1)');
    expect(tip).toContain('Pela regra atual (data prometida), não cobre no horizonte.');
  });

  it('sem preço o valor não vira R$ 0: mostra o motivo', () => {
    render(<AllocationBlock allocation={allocationNoPrice} />);
    const line = screen.getByText(/Descoberto na data prometida/);
    expect(line).toHaveTextContent('Sem preço vigente em Precos_Produtos para o SKU.');
    expect(line.textContent).not.toMatch(/R\$\s?0/);
  });

  it('sem alocação (resposta antiga ou SKU sem pedido descoberto) não renderiza nada', () => {
    const { container } = render(<><AllocationBlock allocation={null} /><AllocationBlock /><AllocationBlock allocation={{ ...allocationContested, orders: [] }} /></>);
    expect(container).toBeEmptyDOMElement();
  });

  it('no detalhe do SKU, o bloco aparece no Resumo; o SKU sem alocação não o mostra', async () => {
    mockApi();
    const { unmount } = renderApp(`/skus/${SKU_OK}`);
    expect(await screen.findByText('Quem atender primeiro', { selector: 'summary' })).toBeInTheDocument();
    unmount();
    renderApp(`/skus/${encodeURIComponent(SKU_SHORT)}`);
    await screen.findByRole('region', { name: 'Ação operacional sugerida' });
    expect(screen.queryByText('Quem atender primeiro')).not.toBeInTheDocument();
  });
});

describe('alavanca e prazo de decisão', () => {
  it('mostra a alavanca e o "decidir até", com o motivo do prazo no "?"', () => {
    render(<ChallengeLever action={challengeAllocate} />);
    expect(screen.getByText(/^Decisão:/)).toHaveTextContent('Decisão: Alocar estoque · decidir até 15/09/2026');
    expect(tipOf(screen.getByRole('button', { name: 'Por que este prazo' }))).toContain('menor data prometida entre os pedidos sem cobertura');
  });

  it('alavanca "nenhuma" ou ausente não renderiza; o "?" do selo traz a alavanca', () => {
    const { container } = render(<><ChallengeLever action={challengeInvestigate} /><ChallengeLever action={{ ...challengeAllocate, lever: undefined }} /><ChallengeLever action={null} /></>);
    expect(container).toBeEmptyDOMElement();
    render(<ChallengeBadge action={challengeAllocate} />);
    expect(screen.getByRole('tooltip', { hidden: true })).toHaveTextContent('Alavanca: Alocar estoque, decidir até 15/09/2026.');
  });

  it('o cartão da ação no detalhe mostra a alavanca do rótulo', async () => {
    mockApi();
    renderApp(`/skus/${SKU_OK}`);
    const answer = await screen.findByRole('region', { name: 'Ação operacional sugerida' });
    expect(within(answer).getByText(/^Decisão:/)).toHaveTextContent('Produzir agora · decidir até 15/09/2026');
  });
});
