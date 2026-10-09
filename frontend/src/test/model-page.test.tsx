import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { modelBenchmark } from './fixtures';
import { fail, mockApi, pending, renderApp } from './utils';

const region = (name: string) => screen.findByRole('region', { name });
const rowOf = (table: HTMLElement, name: string) => within(table).getByText(name).closest('tr') as HTMLElement;

describe('Confiança › Modelo de previsão', () => {
  it('abre como aba de Confiança, ao lado da Validação', async () => {
    mockApi();
    renderApp('/modelo');
    await screen.findByRole('heading', { level: 2, name: 'O que o modelo prevê e quanto erra' });
    const tabs = within(screen.getByRole('navigation', { name: 'Seções desta área' }));
    expect(tabs.getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')])).toEqual([['Validação', '/validacao'], ['Modelo de previsão', '/modelo']]);
    expect(tabs.getByRole('link', { name: 'Modelo de previsão' })).toHaveAttribute('aria-current', 'page');
    expect(within(screen.getByRole('navigation', { name: 'Navegação principal' })).getByRole('link', { name: /Confiança/ })).toHaveAttribute('aria-current', 'page');
  });

  it('diz o que é previsto, com a cadeia de modelos, o erro e as premissas', async () => {
    const api = mockApi();
    renderApp('/modelo');
    expect(await screen.findByText('Unidades faturadas por SKU e mês')).toBeInTheDocument();
    expect(screen.getByText(/6 meses à frente, para 2 de 3 SKUs/)).toBeInTheDocument();
    const chain = await region('Modelos da previsão oficial, na ordem em que são tentados');
    expect(within(rowOf(chain, 'Mês do ano anterior ajustado pelo nível')).getByText('15 meses')).toBeInTheDocument();
    expect(screen.getByText('8,0%')).toBeInTheDocument();
    expect(screen.getByText(/nos picos \(nov, jan\); viés \+0,1%/)).toBeInTheDocument();
    expect(screen.getByText('Premissa sintética do nível.')).toBeInTheDocument();
    expect(screen.getByText(/2 alta, 0 média, 1 baixa/)).toBeInTheDocument();
    expect(api.gets()).toContain('/api/model-benchmark');
  });

  it('compara os modelos com o oficial, sem transformar modelo que não rodou em erro zero', async () => {
    mockApi();
    renderApp('/modelo');
    const table = await region('Modelos comparados com o oficial nas mesmas datas');
    expect(within(rowOf(table, 'Motor oficial')).getByText('Em uso')).toBeInTheDocument();
    expect(within(rowOf(table, 'Prophet sintético')).getByText('Erra mais que o oficial')).toBeInTheDocument();
    expect(within(rowOf(table, 'Prophet sintético')).getByText('36,4% · 37,4%')).toBeInTheDocument();
    const unavailable = rowOf(table, 'LightGBM sintético');
    expect(within(unavailable).getByText('Não rodou')).toBeInTheDocument();
    expect(within(unavailable).queryByText(/0,0%/)).not.toBeInTheDocument();
    expect(screen.getByText('Rodadas anteriores')).toBeInTheDocument();
  });

  it('avisa quando a rodada é de outra planilha e quando não há rodada', async () => {
    const stale = structuredClone(modelBenchmark);
    if (stale.benchmark.status === 'ok') Object.assign(stale.benchmark, { stale: true, note: 'A planilha mudou depois desta rodada.' });
    mockApi({ modelBenchmark: stale });
    const view = renderApp('/modelo');
    expect((await screen.findByText('A planilha mudou depois desta rodada.')).closest('.ui-alert')).toHaveAttribute('role', 'status');
    view.unmount();

    mockApi({ modelBenchmark: { ...modelBenchmark, benchmark: { status: 'no_run', stale: null, note: 'Nenhuma rodada de benchmark neste ambiente.', run: null, history: [] } } });
    renderApp('/modelo');
    expect(await screen.findByText('Nenhuma rodada de benchmark neste ambiente.')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Modelos comparados com o oficial nas mesmas datas' })).not.toBeInTheDocument();
  });

  it('mostra carregamento e falha sem quebrar a página', async () => {
    mockApi({ modelBenchmark: pending() });
    const view = renderApp('/modelo');
    expect(await screen.findByRole('status', { name: 'Carregando dados' })).toBeInTheDocument();
    view.unmount();

    mockApi({ modelBenchmark: fail(500, 'Erro interno.') });
    renderApp('/modelo');
    expect(await screen.findByText('Informações do modelo indisponíveis no momento.')).toBeInTheDocument();
  });
});
