import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { menuGroups, navigation, subNavigation } from '../components';
import { SKU_OK } from './fixtures';
import { mockApi, renderApp } from './utils';

const mainMenu = () => within(screen.getByRole('navigation', { name: 'Navegação principal' }));

describe('arquitetura de navegação final', () => {
  it('o menu tem oito grupos, com SKUs, Financeiro e Bastidores separados, sem "Avançado"', async () => {
    mockApi();
    renderApp('/');
    await screen.findByRole('heading', { level: 2, name: 'Indicadores' });
    expect(mainMenu().getAllByRole('link').map((link) => link.querySelector('strong')?.textContent)).toEqual(['Início', 'Planejamento', 'SKUs', 'Financeiro', 'Comercial', 'Acompanhamento', 'Confiança', 'Bastidores']);
    expect(screen.queryByText('Avançado')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ajuda: abrir o guia de uso' })).toHaveAttribute('href', '/guia');
    expect(menuGroups.map((group) => group.label)).not.toContain('Avançado');
  });

  it('Cenários se alcança pela fila, e Execuções fica em Bastidores, com abas e menu ativo corretos', async () => {
    mockApi();
    const { unmount } = renderApp('/fila');
    await screen.findByRole('heading', { level: 2, name: 'Qual SKU analisar, o que fazer e quanto' });
    expect(screen.getByRole('link', { name: 'Simular pesos' })).toHaveAttribute('href', '/cenarios');
    expect(screen.queryByRole('navigation', { name: 'Seções desta área' })).not.toBeInTheDocument();
    unmount();

    const scenarios = renderApp('/cenarios');
    await screen.findByRole('heading', { level: 2, name: 'E se o peso de um sinal mudar?' });
    expect(mainMenu().getByRole('link', { name: /Planejamento/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Voltar à fila' })).toHaveAttribute('href', '/fila');
    scenarios.unmount();

    renderApp('/execucoes');
    await screen.findByRole('heading', { level: 2, name: 'O que mudou entre duas execuções' });
    expect(mainMenu().getByRole('link', { name: /Bastidores/ })).toHaveAttribute('aria-current', 'page');
    const backstage = within(screen.getByRole('navigation', { name: 'Seções desta área' }));
    expect(backstage.getAllByRole('link').map((link) => link.textContent)).toEqual(['Auditoria', 'Execuções', 'Dados da planilha']);
    expect(backstage.getByRole('link', { name: 'Execuções' })).toHaveAttribute('aria-current', 'page');
  });

  it('Comercial tem uma página para cada visão: oportunidades, parceiros e canais diretos', async () => {
    mockApi();
    renderApp('/carteira');
    await screen.findByRole('heading', { level: 2, name: 'Parceiros e cobertura de dados' });
    expect(mainMenu().getByRole('link', { name: /Comercial/ })).toHaveAttribute('aria-current', 'page');
    const tabs = within(screen.getByRole('navigation', { name: 'Seções desta área' }));
    expect(tabs.getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')])).toEqual([['Oportunidades', '/parceiros'], ['Parceiros', '/carteira'], ['Canais diretos', '/canais']]);
    expect(tabs.getByRole('link', { name: 'Parceiros' })).toHaveAttribute('aria-current', 'page');
  });

  it('toda rota de página pertence a exatamente um grupo do menu', () => {
    const owners = (path: string) => menuGroups.filter((group) => group.paths.some((item) => item === path || (item !== '/' && path.startsWith(`${item}/`)))).map((group) => group.id);
    for (const item of navigation.filter((entry) => entry.path !== '/guia')) expect(owners(item.path), item.path).toHaveLength(1);
    for (const tabs of Object.values(subNavigation)) for (const tab of tabs) expect(navigation.some((entry) => entry.path === tab.to), tab.to).toBe(true);
  });
});

describe('endereços antigos continuam abrindo', () => {
  it.each([
    '/prioridades', '/prioridades?familia=Fam%C3%ADlia+A', '/previsoes', '/previsoes?acao=investigar_dados&ordem=suggested_quantity',
    '/fila', '/faturamento', '/cenarios', '/execucoes', '/execucoes?base=1&alvo=2', '/casos', '/casos?sku=TEST-001', '/decisoes', '/decisoes?sku=TEST-001',
    '/qualidade', '/validacao', '/auditoria', '/parceiros', '/carteira', '/canais', '/parceiros?aba=parceiros', '/parceiros?aba=diretos', '/guia', `/skus/${SKU_OK}`, `/skus/${SKU_OK}?tab=impacto`,
  ])('%s não resulta em 404', async (path) => {
    mockApi();
    renderApp(path);
    await screen.findByRole('heading', { level: 2 });
    expect(screen.queryByText('Página não encontrada')).not.toBeInTheDocument();
    expect(document.title).not.toMatch(/Página não encontrada/);
  });
});
