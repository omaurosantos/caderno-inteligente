import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { forecasts, priorities, SKU_OK, skuDetailOk } from './fixtures';
import { mockApi, renderApp } from './utils';

// Etapa 15.3: a ação vem do plano datado; falta inevitável é urgente e o porquê mostra o plano.
describe('plano datado na fila e no detalhe', () => {
  it('o detalhe do SKU explica a ação com as linhas do plano', async () => {
    mockApi();
    renderApp(`/skus/${encodeURIComponent(SKU_OK)}`);
    expect(await screen.findByText(/Ordem planejada de 500 un\. para chegar em 05\/10/)).toBeInTheDocument();
  });

  it('falta inevitável aparece na fila com o rótulo do plano', async () => {
    const rows = forecasts.map((item, index) => index === 0
      ? { ...item, operational_recommendation: { ...item.operational_recommendation, action: 'atraso_inevitavel' as const, action_label: 'Falta inevitável: renegociar prazos e garantir a OP' } }
      : item);
    mockApi({ forecasts: rows });
    renderApp('/fila');
    expect(await screen.findByText('Falta inevitável: renegociar prazos e garantir a OP')).toBeInTheDocument();
  });
});

describe('bloco Plano de suprimento no detalhe do SKU', () => {
  it('mostra a cascata, os pedidos afetados, os ajustes de OP, as ordens com capacidade e a projeção', async () => {
    mockApi();
    renderApp(`/skus/${encodeURIComponent(SKU_OK)}?tab=evidencias`);
    expect(await screen.findByText('Plano de suprimento')).toBeInTheDocument();
    expect(screen.getByText(/demanda 400 \+ segurança 100 − estoque 50 − OPs no prazo 0 =/)).toBeInTheDocument();
    expect(screen.getByText(/veja "Quem atender primeiro" no Resumo/)).toBeInTheDocument();   // com alocação, os pedidos afetados ficam lá
    expect(screen.getByText('Reduzir OP-T1')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Ordens planejadas', hidden: true })).toHaveTextContent('não cabe');
    expect(screen.getByRole('region', { name: 'Projeção semanal de estoque', hidden: true })).toHaveTextContent('falta');
  });

  it('sem alocação, lista os pedidos afetados pela data prometida', async () => {
    mockApi({ skuDetail: { ...skuDetailOk, allocation: null } });
    renderApp(`/skus/${encodeURIComponent(SKU_OK)}?tab=evidencias`);
    expect(await screen.findByText('PED-T1')).toBeInTheDocument();
    expect(screen.queryByText(/Quem atender primeiro/)).not.toBeInTheDocument();
  });

  it('sem priority_reason (resposta antiga), a fila mostra quando a falta começa como motivo principal', async () => {
    const rows = forecasts.map((item, index) => index === 0
      ? { ...item, operational_recommendation: { ...item.operational_recommendation, action: 'atraso_inevitavel' as const, action_label: 'Falta inevitável: renegociar prazos e garantir a OP', first_shortfall_date: '2026-09-20' } }
      : item);
    // Etapa 16.3: com priority_reason, a faixa e o valor em risco são o motivo principal (fila, T3A).
    mockApi({ forecasts: rows, priorities: priorities.map((item) => ({ ...item, priority_reason: null })) });
    renderApp('/fila');
    expect(await screen.findByText('Falta a partir de 20/09/2026')).toBeInTheDocument();
  });
});
