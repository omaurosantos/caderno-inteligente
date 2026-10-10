import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { PARTNER, SKU_OK, SKU_SHORT } from './fixtures';
import { setViewport } from './setup';
import { currentLocation, mockApi, renderApp } from './utils';

const ROUTES: Array<[string, string, string]> = [
  ['/', 'Início', 'O que olhar primeiro'],
  ['/guia', 'Guia de uso', 'Entenda o Caderno Inteligente em poucos minutos'],
  ['/fila', 'Fila operacional', 'Qual SKU analisar, o que fazer e quanto'],
  ['/faturamento', 'Faturamento previsto', 'Quanto se estima faturar nos próximos três meses'],
  ['/prioridades', 'Fila operacional', 'Qual SKU analisar, o que fazer e quanto'],
  ['/previsoes', 'Fila operacional', 'Qual SKU analisar, o que fazer e quanto'],
  ['/casos', 'Casos', 'Casos em acompanhamento'],
  ['/qualidade', 'Dados da planilha', 'Posso confiar na planilha?'],
  ['/parceiros', 'Oportunidades', 'Onde há oportunidade de reposição'],
  ['/carteira', 'Parceiros', 'Parceiros e cobertura de dados'],
  ['/canais', 'Canais diretos', 'Canais diretos: faturamento observado'],
  ['/parceiros?aba=parceiros', 'Parceiros', 'Parceiros e cobertura de dados'],
  ['/parceiros?aba=diretos', 'Canais diretos', 'Canais diretos: faturamento observado'],
  ['/cenarios', 'Cenários', 'E se o peso de um sinal mudar?'],
  ['/execucoes', 'Execuções', 'O que mudou entre duas execuções'],
  ['/decisoes', 'Histórico de decisões', 'Histórico de decisões'],
  ['/validacao', 'Confiança nas recomendações', 'Quanto confiar nas recomendações'],
  ['/modelo', 'Modelo de previsão', 'O que o modelo prevê e quanto erra'],
  ['/auditoria', 'Auditoria', 'Auditoria: como os resultados foram testados'],
];

describe.each(['desktop', 'mobile'] as const)('rotas em %s', (viewport) => {
  it.each(ROUTES)('%s resolve título, conteúdo e título da aba', async (path, label, intro) => {
    setViewport(viewport);
    mockApi();
    renderApp(path);
    expect(screen.getByRole('heading', { level: 1, name: label })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: intro })).toBeInTheDocument();
    expect(document.title).toBe(`${label} · Caderno Inteligente`);
    expect(screen.getByRole('main')).toBeInTheDocument();
  });
});

describe('deep links', () => {
  it('abre o detalhe de SKU com código codificado e sem carregar o dashboard', async () => {
    const api = mockApi();
    renderApp(`/skus/${encodeURIComponent(SKU_SHORT)}`);
    expect(await screen.findByRole('heading', { level: 2, name: SKU_SHORT })).toBeInTheDocument();
    expect(api.gets()).toContain(`/api/priorities/${encodeURIComponent(SKU_SHORT)}`);
    expect(api.gets().some((path) => path === '/api/overview' || path === '/api/priorities')).toBe(false);
    expect(screen.getByRole('heading', { level: 1, name: 'Detalhe do SKU' })).toBeInTheDocument();
  });

  it('abre o detalhe do parceiro com código codificado', async () => {
    const api = mockApi();
    renderApp(`/parceiros/${encodeURIComponent(PARTNER)}`);
    expect(await screen.findByRole('heading', { level: 2, name: 'Parceiro sintético' })).toBeInTheDocument();
    expect(api.gets()).toContain(`/api/partners/${encodeURIComponent(PARTNER)}`);
    expect(api.gets().some((path) => path.startsWith(`/api/partners/${encodeURIComponent(PARTNER)}/skus?`))).toBe(true);
    expect(within(screen.getByRole('navigation', { name: 'Navegação principal' })).getByRole('link', { name: /Comercial/ })).toHaveAttribute('aria-current', 'page');
  });

  it('abre a comparação de execuções pela URL', async () => {
    const api = mockApi();
    renderApp('/execucoes?base=1&alvo=2');
    expect(await screen.findByText('Execução #1', { selector: 'strong' })).toBeInTheDocument();
    expect(api.gets()).toContain('/api/run-comparisons?base=1&target=2');
  });

  it('abre a página do SKU a partir de uma prioridade e preserva o retorno', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/prioridades?familia=Fam%C3%ADlia+A');
    await user.click(await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` }));
    expect(await screen.findByRole('heading', { level: 2, name: SKU_OK })).toBeInTheDocument();
    expect(currentLocation()).toBe(`/skus/${SKU_OK}`);
    await user.click(screen.getByRole('button', { name: 'Voltar' }));
    await waitFor(() => expect(currentLocation()).toBe('/fila?familia=Fam%C3%ADlia+A'));
  });
});

describe('404 e guia offline', () => {
  it('rota desconhecida mostra 404 sem consultar a API', async () => {
    const api = mockApi();
    renderApp('/rota-inexistente');
    expect(await screen.findByRole('heading', { level: 2, name: 'Página não encontrada' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Voltar para a visão geral/ })).toHaveAttribute('href', '/');
    expect(api.calls).toHaveLength(0);
  });

  it('o guia funciona com a API fora do ar', async () => {
    const api = mockApi();
    api.fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    renderApp('/guia');
    expect(await screen.findByRole('heading', { level: 2, name: 'Entenda o Caderno Inteligente em poucos minutos' })).toBeInTheDocument();
    expect(screen.getByText('Não consulta a API')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Atualizar/ })).not.toBeInTheDocument();
    expect(api.fetchMock).not.toHaveBeenCalled();
    // Trilhas por papel (PCP, Comercial, Gestão) levam às telas principais, todas offline.
    const trails = screen.getAllByRole('link').filter((link) => link.classList.contains('guide-link'));
    expect(trails.length).toBeGreaterThanOrEqual(8);
  });
});

describe('menu', () => {
  it('marca apenas o link ativo e move o foco para o título ao navegar', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/prioridades');
    const nav = screen.getByRole('navigation', { name: 'Navegação principal' });
    expect(within(nav).getAllByRole('link')).toHaveLength(7);
    expect(within(nav).getByRole('link', { name: /Planejamento/ })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: /Início/ })).not.toHaveAttribute('aria-current');
    await user.click(within(nav).getByRole('link', { name: /Confiança/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Confiança nas recomendações' })).toHaveFocus();
    expect(within(nav).getByRole('link', { name: /Confiança/ })).toHaveAttribute('aria-current', 'page');
    expect(document.title).toBe('Confiança nas recomendações · Caderno Inteligente');
  });
});
