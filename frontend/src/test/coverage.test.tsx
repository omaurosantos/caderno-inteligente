import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { quality, SKU_OK } from './fixtures';
import { mockApi, renderApp } from './utils';

// Etapa 15.2: a cobertura usa a demanda prevista; o cadastro divergente vira aviso de qualidade.
describe('cobertura pela demanda prevista', () => {
  it('Dados da planilha mostra quantos SKUs têm venda média cadastrada distante da prevista', async () => {
    mockApi();
    renderApp('/qualidade');
    expect(await screen.findByText('2 SKUs')).toBeInTheDocument();
    expect(screen.getByText('distantes da demanda prevista')).toBeInTheDocument();
  });

  it('o detalhe do SKU mostra a cobertura pela demanda e a do cadastro quando divergem', async () => {
    mockApi();
    renderApp(`/skus/${encodeURIComponent(SKU_OK)}?tab=evidencias`);
    expect(await screen.findByText(/cadastro: 9 dias/)).toBeInTheDocument();
  });

  // Etapa 16.1/16.3: avisos de fontes que não fecham entre si.
  it('Dados da planilha lista os avisos de Curva ABC, sell-in × faturado e rateio do faturamento', async () => {
    mockApi();
    renderApp('/qualidade');
    const table = await screen.findByRole('region', { name: 'Avisos de consistência entre as abas da planilha' });
    const abc = within(table).getByText('Curva ABC do cadastro').closest('tr') as HTMLElement;
    expect(abc).toHaveTextContent('1 SKU');
    expect(abc).toHaveTextContent('discordam');
    const sellIn = within(table).getByText('Sell-in × faturado').closest('tr') as HTMLElement;
    expect(sellIn).toHaveTextContent('1 parceiro');
    expect(sellIn).toHaveTextContent('KA-T1 (×3)');
    expect(sellIn).toHaveTextContent('×1,25');
    const split = within(table).getByText('Faturamento por cliente').closest('tr') as HTMLElement;
    expect(split).toHaveTextContent('0,92 a 1,03');
    expect(split).toHaveTextContent('rateio');
  });

  it('os itens dos avisos ficam sob demanda, com os maiores faturamentos primeiro', async () => {
    const items = Array.from({ length: 12 }, (_, index) => ({ sku: `CI-${index + 1}`, registry: 'C' as const, measured: 'A' as const, revenue_12m: (index + 1) * 1000 }));
    const warnings = quality.warnings.map((item) => item.code === 'ABC_REGISTRY_DIVERGENCE' ? { ...item, count: 12, items } : item);
    mockApi({ quality: { ...quality, warnings } });
    renderApp('/qualidade');
    const abc = await screen.findByRole('region', { name: 'SKUs com Curva ABC divergente', hidden: true });
    expect(within(abc).getAllByRole('row', { hidden: true })).toHaveLength(11);
    expect(within(abc).getByRole('link', { name: 'CI-12', hidden: true })).toBeInTheDocument();
    expect(within(abc).queryByRole('link', { name: 'CI-1', hidden: true })).not.toBeInTheDocument();
    expect(within(await screen.findByRole('region', { name: 'Parceiros com sell-in divergente do faturado', hidden: true })).getByText('KA-T1')).toBeInTheDocument();
  });

  it('sem os avisos novos a tabela não aparece', async () => {
    mockApi({ quality: { ...quality, warnings: quality.warnings.filter((item) => item.code === 'REGISTERED_DEMAND_DIVERGENCE') } });
    renderApp('/qualidade');
    expect(await screen.findByText('2 SKUs')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Avisos de consistência entre as abas da planilha' })).not.toBeInTheDocument();
  });
});
