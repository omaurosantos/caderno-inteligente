import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import budget from './volume-budget.json';
import { mockApi, renderApp } from './utils';

// Teste de volume: mede palavras, números, blocos, colunas e avisos de cada tela (tudo expandido) e falha acima do orçamento.
// Texto só para leitor de tela (.sr-only) e o conteúdo dos "?" não contam.
const WRAPPERS = /(decision-journey|sku-detail-page|sku-list-page|operational-queue|revenue-page|validation-page|guide-page|feedback-layout|scenario-layout)/;
const SKIP = /(rule-line|subnav|page-intro|system-banner)/;

const words = (text: string) => text.split(/\s+/).filter(Boolean).length;
const numbers = (text: string) => (text.replace(/\b[A-Za-z]{1,4}[ -]?\d{1,4}\b/g, '').replace(/\d{1,2}\/\d{1,4}(\/\d{4})?/g, '').match(/\d[\d.,]*%?/g) ?? []).length;

function visibleText(element: Element) {
  const copy = element.cloneNode(true) as Element;
  copy.querySelectorAll('.sr-only, [role="tooltip"], script, style').forEach((node) => node.remove());
  return (copy.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function measure(main: Element) {
  const copy = main.cloneNode(true) as Element;
  copy.querySelectorAll('.sr-only, [role="tooltip"]').forEach((node) => node.remove());
  const evidences = [...copy.querySelectorAll('.evidence-body')];
  const evidenceWords = evidences.map((node) => words(node.textContent ?? ''));
  const tables = [...copy.querySelectorAll('table')].filter((table) => !table.closest('.evidence-body'));
  const perRow = tables.map((table) => {
    const rows = [...table.querySelectorAll('tbody tr')].filter((row) => !row.classList.contains('evidence-row'));
    const text = rows.map((row) => row.classList.contains('evidence-row') ? '' : (row.textContent ?? '')).join(' ');
    return rows.length ? words(text) / rows.length : 0;
  });
  const columns = tables.map((table) => [...(table.tHead?.rows[0]?.cells ?? [])].filter((th) => !th.querySelector('.sr-only') && (th.textContent ?? '').trim()).length);
  tables.forEach((table) => table.remove());
  evidences.forEach((node) => node.closest('tr')?.remove());
  copy.querySelectorAll('.evidence-body').forEach((node) => node.remove());
  // Valores dos eixos dos gráficos são escala, lida de relance como as células de tabela (que também saem da contagem de prosa).
  copy.querySelectorAll('.recharts-cartesian-axis-tick-labels').forEach((node) => node.remove());
  const prose = (copy.textContent ?? '').replace(/\s+/g, ' ').trim();
  const root = [...main.children].map((child) => WRAPPERS.test(child.className.toString()) ? [...child.children] : [child]).flat().filter((child) => !SKIP.test(child.className.toString()) && visibleText(child));
  const alerts = main.querySelectorAll('.ui-alert, .rule-line, .human-review-line, .human-review, .verdict, .details-note').length;
  // Repetição: frase de 4+ palavras que aparece mais de 2 vezes fora de tabelas.
  const seen = new Map<string, number>();
  const walker = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = (node.nodeValue ?? '').replace(/\s+/g, ' ').trim();
    if (words(text) >= 4) seen.set(text, (seen.get(text) ?? 0) + 1);
  }
  return {
    fixed: words(prose), numbers: numbers(prose), blocks: root.length, alerts,
    perRow: Math.max(0, ...perRow), columns: Math.max(0, ...columns), perEvidence: Math.max(0, ...evidenceWords),
    repeated: [...seen.entries()].filter(([, count]) => count > 2).map(([text, count]) => `${count}× ${text.slice(0, 50)}`),
  };
}

describe('volume por tela (orçamento)', () => {
  for (const [path, limits] of Object.entries(budget.routes)) {
    it(`${path} respeita o orçamento de palavras, números, blocos, colunas e avisos`, async () => {
      mockApi();
      renderApp(path);
      await waitFor(() => expect(document.getElementById('page-title')).not.toBeNull());
      await screen.findByRole('heading', { level: 2 });
      await new Promise((resolve) => setTimeout(resolve, 150));
      // Tudo expandido: abre detalhes e mostra painéis de aba.
      document.querySelectorAll('details').forEach((details) => { details.open = true; });
      document.querySelectorAll('[hidden]').forEach((node) => node.removeAttribute('hidden'));
      const result = measure(document.querySelector('.page-content')!);
      const excess = (['fixed', 'perRow', 'perEvidence', 'numbers', 'blocks', 'columns', 'alerts'] as const)
        .filter((key) => result[key] > limits[key]).map((key) => `${path}: ${key} ${Math.round(result[key])} > ${limits[key]}`);
      expect(excess, `volume acima do teto:\n${excess.join('\n')}\nrepetições: ${result.repeated.join(' | ')}`).toEqual([]);
      expect(result.repeated).toEqual([]);
    });
  }
});
