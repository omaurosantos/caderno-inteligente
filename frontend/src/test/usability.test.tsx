import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { displayPercent, displayQuantity, localizeText, sortReasons } from '../pages/shared';
import { PARTNER, SKU_OK, SKU_SHORT } from './fixtures';
import { currentLocation, mockApi, renderApp } from './utils';

describe('motivo principal e formatos (apresentação)', () => {
  it('ordena os sinais pelo peso, sem alterar quais sinais existem', () => {
    const reasons = [
      { code: 'CAPACITY_CONFLICT', severity: 'alta' },
      { code: 'LOW_SELLOUT_VISIBILITY', severity: 'média' },
      { code: 'RUP_SAFETY_STOCK', severity: 'crítica' },
    ];
    const weights = { CAPACITY_CONFLICT: 5, LOW_SELLOUT_VISIBILITY: 2, RUP_SAFETY_STOCK: 10 };
    const ordered = sortReasons(reasons, weights);
    expect(ordered.map((item) => item.code)).toEqual(['RUP_SAFETY_STOCK', 'CAPACITY_CONFLICT', 'LOW_SELLOUT_VISIBILITY']);
    expect(ordered).toHaveLength(reasons.length);
    // Sem pesos, a severidade desempata.
    expect(sortReasons(reasons)[0].code).toBe('RUP_SAFETY_STOCK');
  });

  it('padroniza percentuais, quantidades e dado ausente (nunca zero)', () => {
    expect(displayPercent(0.08)).toBe('8,0%');
    expect(displayPercent(0.069)).toBe('6,9%');
    expect(displayPercent(null)).toBe('Não disponível');
    expect(displayQuantity(1246.3)).toBe('1.246');
    expect(displayQuantity(754.7)).toBe('754,7'.replace('754,7', '755'));
    expect(displayQuantity(12.5)).toBe('12,5');
    expect(displayQuantity(null)).toBe('Não disponível');
    expect(displayQuantity(0)).toBe('0');
  });

  it('troca decimais com ponto dos textos prontos do backend por pt-BR sem tocar em datas e códigos', () => {
    expect(localizeText('Demanda a cobrir: previsão (1246.3) e carteira (1327.0).')).toBe('Demanda a cobrir: previsão (1.246) e carteira (1.327).');
    expect(localizeText('promessa 2026-09-13, SKU CI-0014, lote 400.0')).toBe('promessa 2026-09-13, SKU CI-0014, lote 400');
  });
});

describe('navegação agrupada', () => {
  it('mostra as abas do grupo e mantém as rotas antigas acessíveis por URL', async () => {
    mockApi();
    renderApp('/qualidade');
    await screen.findByRole('heading', { level: 2, name: 'Posso confiar na planilha?' });
    const tabs = screen.getByRole('navigation', { name: 'Seções desta área' });
    expect(within(tabs).getByRole('link', { name: 'Dados da planilha' })).toHaveAttribute('aria-current', 'page');
    expect(within(tabs).getByRole('link', { name: 'Auditoria' })).toHaveAttribute('href', '/auditoria');
    expect(within(screen.getByRole('navigation', { name: 'Navegação principal' })).getByRole('link', { name: /Bastidores/ })).toHaveAttribute('aria-current', 'page');
  });

  it('diz a regra uma vez, só onde há sugestão, e não a repete nas demais telas', async () => {
    mockApi();
    const { unmount } = renderApp('/fila');
    await screen.findByRole('heading', { level: 2, name: 'Qual SKU analisar, o que fazer e quanto' });
    expect(screen.getAllByText(/não é ordem de produção/)).toHaveLength(1);
    unmount();
    renderApp('/casos');
    await screen.findByRole('heading', { level: 2, name: 'Casos em acompanhamento' });
    expect(screen.queryByText(/não é ordem de produção/)).not.toBeInTheDocument();
  });
});

describe('fila operacional enxuta', () => {
  it('mostra uma linha curta por SKU (sem detalhe repetido) e abre o SKU com um clique', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    expect(screen.queryByText('Ver sinais, data e lacuna')).not.toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: /Fila operacional/ })).getAllByRole('columnheader').filter((header) => !header.querySelector('.sr-only'))).toHaveLength(5);
    await user.click(screen.getByRole('button', { name: `Ver detalhes de ${SKU_OK}` }));
    expect(currentLocation()).toBe(`/skus/${SKU_OK}`);
  });
});

describe('detalhe do SKU: resposta primeiro e próximo passo', () => {
  it('mostra a ação sugerida no topo e leva ao registro com o SKU preenchido', async () => {
    mockApi();
    renderApp(`/skus/${SKU_OK}`);
    const answer = await screen.findByRole('region', { name: 'Ação operacional sugerida' });
    expect(within(answer).getByText('Revisão humana obrigatória')).toBeInTheDocument();
    expect(within(answer).getByRole('link', { name: 'Registrar decisão' })).toHaveAttribute('href', `/decisoes?sku=${SKU_OK}&rotulo=priorizar_producao`);
    expect(within(answer).getByRole('link', { name: 'Criar caso' })).toHaveAttribute('href', `/casos?sku=${SKU_OK}`);
    // Evidências continuam a um clique: o bloco de riscos abre por padrão.
    expect(screen.getByRole('tab', { name: 'Evidências' })).toBeInTheDocument();
  });

  it('o formulário de decisão aceita o SKU da URL, inclusive fora do ranking', async () => {
    mockApi();
    renderApp(`/decisoes?sku=${encodeURIComponent(SKU_SHORT)}`);
    const select = await screen.findByLabelText('SKU');
    expect(select).toHaveValue(SKU_SHORT);
    expect(screen.getByRole('link', { name: `Voltar ao SKU ${SKU_SHORT}` })).toBeInTheDocument();
  });
});

describe('parceiros: oportunidades e evidências na própria linha', () => {
  it('lista as oportunidades de reposição e abre a evidência com um clique', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    renderApp('/parceiros');
    await screen.findByRole('heading', { level: 2, name: 'Onde há oportunidade de reposição' });
    await screen.findByRole('region', { name: /Matriz comercial/ });
    expect(api.gets().some((path) => path.includes('/api/commercial-recommendations') && path.includes('action=avaliar_reposicao'))).toBe(true);
    const toggle = screen.getAllByRole('button', { name: /^Evidências de/ })[0];
    // O fixture tem um único vínculo: a evidência já vem aberta e pode ser recolhida.
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByText(/Por que esta sugestão/).length).toBeGreaterThan(0);
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Por que esta sugestão/)).not.toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  it('a página de parceiros tem endereço próprio e abre o detalhe do parceiro', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/parceiros');
    await screen.findByRole('heading', { level: 2, name: 'Onde há oportunidade de reposição' });
    await user.click(within(screen.getByRole('navigation', { name: 'Seções desta área' })).getByRole('link', { name: 'Parceiros' }));
    expect(currentLocation()).toBe('/carteira');
    expect(await screen.findByRole('link', { name: /Abrir parceiro/ })).toHaveAttribute('href', `/parceiros/${encodeURIComponent(PARTNER)}`);
  });
});

describe('validação: veredito e falhas visíveis, detalhes em abas', () => {
  it('mostra o veredito e as falhas conhecidas antes das abas e troca de aba por teclado/clique', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/validacao');
    expect(await screen.findByRole('heading', { name: 'Em resumo' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Falhas conhecidas' })).toBeInTheDocument();
    const tablist = screen.getByRole('tablist', { name: 'Detalhes da validação' });
    expect(within(tablist).getByRole('tab', { name: 'Processo atual' })).toHaveAttribute('aria-selected', 'true');
    await user.click(within(tablist).getByRole('tab', { name: 'Modelos de previsão' }));
    expect(within(tablist).getByRole('tab', { name: 'Modelos de previsão' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Modelos de previsão' })).toBeVisible();
    // Material de auditoria saiu da tela de decisão e vive em /auditoria.
    expect(screen.queryByText('Casos representativos congelados')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Auditoria completa' })).toHaveAttribute('href', '/auditoria');
  });

  it('a página de Auditoria reúne casos congelados, verificações e histórico', async () => {
    mockApi();
    renderApp('/auditoria');
    expect(await screen.findByRole('heading', { level: 2, name: 'Auditoria: como os resultados foram testados' })).toBeInTheDocument();
    // Os blocos começam recolhidos: o título e uma nota ficam visíveis, o conteúdo abre sob demanda.
    for (const title of ['Casos de teste congelados', 'Comportamento seguro', 'Limitações', 'Histórico de ajustes']) {
      const summary = screen.getByText(title, { selector: 'summary' });
      expect(summary.closest('details')).not.toHaveAttribute('open');
    }
    expect(await screen.findByText('Método comercial', { selector: 'summary' })).toBeInTheDocument();
  });
});
