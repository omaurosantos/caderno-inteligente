import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { mockApi, renderApp } from './utils';

describe('robustez', () => {
  it('resposta malformada fica contida na rota e o menu continua utilizável', async () => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    mockApi({ overview: null as unknown as never });
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Esta página não pôde ser exibida' })).toBeInTheDocument();
    expect(screen.getByText(/Os dados de origem não foram alterados/)).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: /Ajuda: abrir/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Entenda o Caderno Inteligente em poucos minutos' })).toBeInTheDocument();
  });

  it('resposta que não é JSON gera mensagem legível', async () => {
    const api = mockApi();
    api.fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => { throw new SyntaxError('Unexpected token <'); } } as unknown as Response);
    renderApp('/validacao');
    expect(await screen.findByText('O servidor retornou uma resposta inválida.')).toBeInTheDocument();
  });

  it('trocar de rota cancela a leitura anterior sem sobrescrever a nova página', async () => {
    const user = userEvent.setup();
    let release: (value: unknown) => void = () => {};
    const api = mockApi({ forecasts: () => new Promise((resolve) => { release = resolve; }) });
    renderApp('/previsoes');
    await waitFor(() => expect(api.gets()).toContain('/api/forecasts'));
    await user.click(within(screen.getByRole('navigation', { name: 'Navegação principal' })).getByRole('link', { name: /Confiança/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Quanto confiar nas recomendações' })).toBeInTheDocument();
    release([]);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByRole('heading', { level: 2, name: 'Quanto confiar nas recomendações' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: 'Preciso produzir? Quanto?' })).not.toBeInTheDocument();
    expect((api.fetchMock.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true);
  });
});
