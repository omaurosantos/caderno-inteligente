import { screen } from '@testing-library/react';
import axe from 'axe-core';
import { describe, expect, it } from 'vitest';
import { CHANNEL, PARTNER, SKU_SHORT } from './fixtures';
import { setViewport } from './setup';
import { mockApi, renderApp } from './utils';

// jsdom has no layout engine: color contrast is checked separately in contrast.test.ts.
const OPTIONS: axe.RunOptions = { rules: { 'color-contrast': { enabled: false } }, resultTypes: ['violations'] };

const PAGES: Array<[string, string]> = [
  ['/', 'Indicadores'],
  ['/guia', 'Entenda o Caderno Inteligente em poucos minutos'],
  ['/fila', 'Qual SKU analisar, o que fazer e quanto'],
  ['/faturamento', 'Quanto se estima faturar nos próximos três meses'],
  ['/prioridades', 'Qual SKU analisar, o que fazer e quanto'],
  ['/previsoes', 'Qual SKU analisar, o que fazer e quanto'],
  [`/skus/${encodeURIComponent(SKU_SHORT)}`, SKU_SHORT],
  [`/skus/${encodeURIComponent(SKU_SHORT)}?tab=evidencias`, SKU_SHORT],
  [`/skus/${encodeURIComponent(SKU_SHORT)}?tab=parceiros`, SKU_SHORT],
  [`/skus/${encodeURIComponent(SKU_SHORT)}?tab=impacto`, SKU_SHORT],
  ['/casos', 'Casos em acompanhamento'],
  ['/qualidade', 'Posso confiar na planilha?'],
  ['/parceiros', 'Onde há oportunidade de reposição'],
  [`/parceiros/${encodeURIComponent(PARTNER)}`, 'Parceiro sintético'],
  ['/carteira', 'Parceiros e cobertura de dados'],
  ['/canais', 'Canais diretos: faturamento observado'],
  ['/parceiros?aba=diretos', 'Canais diretos: faturamento observado'],
  [`/canais/${encodeURIComponent(CHANNEL)}`, 'Loja própria'],
  ['/cenarios', 'E se o peso de um sinal mudar?'],
  ['/execucoes?base=1&alvo=2', 'O que mudou entre duas execuções'],
  ['/decisoes', 'Histórico de decisões'],
  ['/validacao', 'Quanto confiar nas recomendações'],
  ['/modelo', 'O que o modelo prevê e quanto erra'],
  ['/auditoria', 'Auditoria: como os resultados foram testados'],
  ['/rota-inexistente', 'Página não encontrada'],
];

function describeViolations(violations: axe.Result[]) {
  return violations.map((violation) => `${violation.impact} ${violation.id}: ${violation.help} → ${violation.nodes.slice(0, 3).map((node) => node.target.join(' ')).join(' | ')}`);
}

describe.each(['desktop', 'mobile'] as const)('acessibilidade automatizada (%s)', (viewport) => {
  it.each(PAGES)('%s não tem violações de acessibilidade', async (path, heading) => {
    setViewport(viewport);
    mockApi();
    const { container } = renderApp(path);
    await screen.findByRole('heading', { level: 2, name: heading });
    if (path.startsWith('/execucoes')) await screen.findByText('Fonte e configuração');
    const results = await axe.run(container, OPTIONS);
    // Every impact level (critical, serious, moderate, minor) must be clean in the main flow.
    expect(describeViolations(results.violations)).toEqual([]);
    // jsdom cannot detect overflow, so enforce the pattern axe checks in real browsers (scrollable-region-focusable).
    for (const shell of container.querySelectorAll('.table-shell')) {
      expect(shell).toHaveAttribute('tabindex', '0');
      expect(shell).toHaveAccessibleName();
    }
  });
});
