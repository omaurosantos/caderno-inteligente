import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearAnalysis, elapsedMinutes, startAnalysis } from '../analysisTimer';
import { SKU_OK, SKU_SHORT } from './fixtures';
import { currentLocation, mockApi, renderApp } from './utils';

// Storage em memória: o Node recente expõe um `sessionStorage` global que pode não ser o do jsdom.
function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; }, clear: () => data.clear(), key: (index: number) => [...data.keys()][index] ?? null,
    getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, String(value)); }, removeItem: (key: string) => { data.delete(key); },
  };
}

const MINUTE = 60_000;

beforeEach(() => { Object.defineProperty(window, 'sessionStorage', { configurable: true, value: memoryStorage() }); });
afterEach(() => { vi.restoreAllMocks(); [SKU_OK, SKU_SHORT, 'X'].forEach(clearAnalysis); });

describe('analysisTimer', () => {
  it('mede em minutos (mínimo 1, com teto) desde o primeiro início, por SKU, e zera depois da decisão', () => {
    expect(elapsedMinutes('X', 0)).toBeNull();
    startAnalysis('X', 1_000);
    startAnalysis('X', 5 * MINUTE);                  // reabrir o SKU não reinicia a contagem
    expect(window.sessionStorage.getItem('caderno-inteligente.analise.X')).toBe('1000');
    expect(elapsedMinutes('X', 1_000 + 20_000)).toBe(1);
    expect(elapsedMinutes('X', 1_000 + 12 * MINUTE)).toBe(12);
    expect(elapsedMinutes('X', 1_000 + 3000 * MINUTE)).toBe(1440);
    expect(elapsedMinutes('X', 0)).toBeNull();       // relógio voltou: não inventa tempo
    expect(elapsedMinutes(SKU_SHORT, 1_000 + MINUTE)).toBeNull();
    clearAnalysis('X');
    expect(elapsedMinutes('X', 1_000 + MINUTE)).toBeNull();
  });

  it('sem sessionStorage (bloqueado) continua medindo nesta tela', () => {
    Object.defineProperty(window, 'sessionStorage', { configurable: true, get() { throw new Error('bloqueado'); } });
    startAnalysis('X', 0);
    expect(elapsedMinutes('X', 4 * MINUTE)).toBe(4);
  });
});

describe('tempo de análise automático no registro da decisão', () => {
  it('abrir o SKU e registrar a decisão envia o tempo medido, com o aviso de que é medido', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    renderApp(`/skus/${SKU_OK}`);
    await screen.findByRole('region', { name: 'Ação operacional sugerida' });
    const opened = Date.now();
    vi.spyOn(Date, 'now').mockReturnValue(opened + 7 * MINUTE);
    await user.click(screen.getByRole('link', { name: 'Registrar decisão' }));
    await waitFor(() => expect(currentLocation()).toMatch(/^\/decisoes\?sku=TEST-001/));
    const field = await screen.findByLabelText(/Tempo de análise/);
    expect(field).toHaveValue(7);
    expect(field).toHaveAccessibleDescription(/Tempo medido desde que você abriu o SKU/);
    vi.spyOn(Date, 'now').mockReturnValue(opened + 9 * MINUTE);   // o envio usa o tempo até o registro
    await user.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    expect(await screen.findByText('Decisão registrada com sucesso.')).toBeInTheDocument();
    expect(api.calls.find((call) => call.method === 'POST')?.body).toMatchObject({ sku: SKU_OK, analysis_minutes: 9 });
    expect(elapsedMinutes(SKU_OK)).toBeNull();     // a próxima análise começa do zero
    expect(field).toHaveValue(null);
  });

  it('o tempo é editável: o valor corrigido pelo usuário é o enviado', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    startAnalysis(SKU_OK, Date.now() - 5 * MINUTE);
    renderApp(`/decisoes?sku=${SKU_OK}`);
    const field = await screen.findByLabelText(/Tempo de análise/);
    expect(field).toHaveValue(5);
    await user.clear(field);
    await user.type(field, '3');
    expect(screen.queryByText(/Tempo medido desde que você abriu o SKU/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    await waitFor(() => expect(api.calls.find((call) => call.method === 'POST')).toBeTruthy());
    expect(api.calls.find((call) => call.method === 'POST')?.body).toMatchObject({ analysis_minutes: 3 });
  });

  it('trocar o SKU depois de editar os minutos descarta a edição e mede o tempo do novo SKU', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    startAnalysis(SKU_OK, Date.now() - 2 * MINUTE);
    startAnalysis(SKU_SHORT, Date.now() - 7 * MINUTE);
    renderApp(`/decisoes?sku=${SKU_OK}`);
    const field = await screen.findByLabelText(/Tempo de análise/);
    await user.clear(field);
    await user.type(field, '30');
    await user.selectOptions(screen.getByLabelText('SKU'), SKU_SHORT);
    await waitFor(() => expect(field).toHaveValue(7));
    expect(screen.getByText(/Tempo medido desde que você abriu o SKU/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    await waitFor(() => expect(api.calls.find((call) => call.method === 'POST')).toBeTruthy());
    expect(api.calls.find((call) => call.method === 'POST')?.body).toMatchObject({ sku: SKU_SHORT, analysis_minutes: 7 });
  });

  it('trocar para um SKU que não foi aberto deixa o campo vazio; sem medição não há tempo inventado', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    startAnalysis(SKU_OK, Date.now() - 2 * MINUTE);
    renderApp(`/decisoes?sku=${SKU_OK}`);
    const field = await screen.findByLabelText(/Tempo de análise/);
    expect(field).toHaveValue(2);
    await user.selectOptions(screen.getByLabelText('SKU'), SKU_SHORT);
    expect(field).toHaveValue(null);
    await user.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    await waitFor(() => expect(api.calls.find((call) => call.method === 'POST')).toBeTruthy());
    expect(api.calls.find((call) => call.method === 'POST')?.body).toMatchObject({ sku: SKU_SHORT, analysis_minutes: null });
  });
});
