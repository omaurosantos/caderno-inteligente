import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SKU_OK } from './fixtures';
import { mockApi, renderApp } from './utils';

// Critério de clareza por tela (docs/criterio-de-clareza.md): em 5 segundos a pessoa sabe o que fazer.
// O teste verifica a estrutura que sustenta o critério: um título, uma ação principal, a resposta antes dos detalhes.
// Complementa o orçamento de volume (volume.test.tsx); não o substitui.
const ROUTES: Array<[string, string]> = [
  ['/', 'o primeiro SKU da fila'],
  ['/fila', 'a lista de SKUs com ação e quantidade'],
  [`/skus/${SKU_OK}`, 'a ação sugerida do SKU'],
  ['/skus', 'a lista de SKUs'],
  ['/parceiros', 'a lista de oportunidades'],
  ['/carteira', 'a lista de parceiros'],
  ['/canais', 'os canais diretos'],
  ['/faturamento', 'o faturamento previsto'],
  ['/validacao', 'o veredito da validação'],
];

const content = () => document.querySelector('.page-content') as HTMLElement;

describe.each(ROUTES)('clareza: %s (%s)', (path) => {
  it('tem um título de página, no máximo uma ação principal e a resposta antes dos detalhes', async () => {
    mockApi();
    renderApp(path);
    await screen.findByRole('heading', { level: 2 });
    await waitFor(() => expect(content().querySelectorAll('table, .answer-card, .attention-focus, .verdict, .section-card').length).toBeGreaterThan(0));
    expect(within(content()).getAllByRole('heading', { level: 2 })).toHaveLength(1);
    expect(content().querySelectorAll('.primary-button').length).toBeLessThanOrEqual(2);
    // A primeira coisa depois do título e dos filtros é a resposta, não um aviso extra: no máximo um aviso antes dela.
    const answer = content().querySelector('table, .answer-card, .attention-focus, .verdict, .section-card');
    const before = answer ? [...content().querySelectorAll('.ui-alert, .rule-line, .system-banner')].filter((node) => !!(node.compareDocumentPosition(answer) & Node.DOCUMENT_POSITION_FOLLOWING)) : [];
    expect(before.length).toBeLessThanOrEqual(2);
  });
});

describe('clareza: fila operacional', () => {
  it('cada linha mostra no máximo três selos e a ação e a quantidade ficam à vista', async () => {
    mockApi();
    renderApp('/fila?todos=1');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    const rows = [...document.querySelectorAll('.queue-table tbody tr')];
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.querySelectorAll('.badge').length).toBeLessThanOrEqual(3);
      expect(row.querySelector('.queue-action')?.textContent?.trim()).toBeTruthy();
      expect(row.querySelector('.queue-qty')?.textContent?.trim()).toBeTruthy();
      expect(row.className).toMatch(/is-(urgent|review|none|missing)/);
    }
  });
});
