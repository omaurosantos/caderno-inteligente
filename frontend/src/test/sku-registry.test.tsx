import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, describe, expect, it } from 'vitest';
import { SKU_OK, sessionUser, system } from './fixtures';
import { fail, mockApi, renderApp } from './utils';

const banco = { system: { ...system, data_source: 'banco' } };
const SESSION_KEY = 'caderno-inteligente.sessao';
const signedIn = () => window.localStorage.setItem(SESSION_KEY, JSON.stringify({ token: 'token-salvo', expiresAt: 4_102_444_800, user: sessionUser }));

afterEach(() => window.localStorage.clear());

describe('cadastro de SKU (fase 3)', () => {
  it('com a base na planilha, a lista de SKUs não mostra cadastro nem pede login', async () => {
    mockApi();
    renderApp('/skus');
    await screen.findByRole('link', { name: `Abrir ${SKU_OK}` });
    expect(screen.queryByRole('heading', { name: 'Cadastro' })).not.toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Entrar para cadastrar SKUs' })).not.toBeInTheDocument();
  });

  it('com a base no banco, pede login e depois consulta o cadastro com o token', async () => {
    const api = mockApi(banco);
    renderApp('/skus');
    const form = await screen.findByRole('form', { name: 'Entrar para cadastrar SKUs' });
    expect(screen.queryByRole('button', { name: `Excluir ${SKU_OK}` })).not.toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText('E-mail'), sessionUser.email);
    await userEvent.type(within(form).getByLabelText('Senha'), 'senha-forte-123');
    await userEvent.click(within(form).getByRole('button', { name: 'Entrar' }));

    expect(await screen.findByRole('button', { name: 'Adicionar SKU' })).toBeEnabled();
    expect(screen.getByText('Ana PCP')).toBeInTheDocument();
    expect(api.calls.find((call) => call.path === '/api/auth/login')?.body).toEqual({ email: sessionUser.email, password: 'senha-forte-123' });
    expect(api.calls.find((call) => call.path === '/api/skus/cadastro')?.headers.Authorization).toBe('Bearer token-sintetico');
    expect(screen.getByRole('button', { name: `Excluir ${SKU_OK}` })).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem(SESSION_KEY) ?? '{}').user.email).toBe(sessionUser.email);
  });

  it('login recusado mostra o motivo e não guarda sessão', async () => {
    mockApi({ ...banco, 'POST login': fail(401, 'E-mail ou senha incorretos.') });
    renderApp('/skus');
    const form = await screen.findByRole('form', { name: 'Entrar para cadastrar SKUs' });
    await userEvent.type(within(form).getByLabelText('E-mail'), sessionUser.email);
    await userEvent.type(within(form).getByLabelText('Senha'), 'errada');
    await userEvent.click(within(form).getByRole('button', { name: 'Entrar' }));
    expect(await within(form).findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.');
    expect(window.localStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('cadastra um SKU novo e recarrega a lista', async () => {
    signedIn();
    const api = mockApi(banco);
    renderApp('/skus');
    await userEvent.click(await screen.findByRole('button', { name: 'Adicionar SKU' }));
    const form = screen.getByRole('form', { name: 'Novo SKU' });
    await userEvent.type(within(form).getByLabelText('Código do SKU'), 'ci-9001');
    await userEvent.type(within(form).getByLabelText('Produto'), 'Caderno Teste');
    await userEvent.selectOptions(within(form).getByLabelText('Família'), 'Premium');
    await userEvent.clear(within(form).getByLabelText('Estoque atual'));
    await userEvent.type(within(form).getByLabelText('Estoque atual'), '300');
    const before = api.gets().filter((path) => path === '/api/forecasts').length;
    await userEvent.click(within(form).getByRole('button', { name: 'Cadastrar SKU' }));

    expect(await screen.findByText('CI-9001 cadastrado. Ele já entra na fila e nas previsões.')).toBeInTheDocument();
    const created = api.calls.find((call) => call.method === 'POST' && call.path === '/api/skus');
    expect(created?.body).toEqual({ sku: 'CI-9001', produto: 'Caderno Teste', familia: 'Premium', curva_abc: 'C', lead_time_dias: 0, lote_minimo: 0, estoque_atual: 300, estoque_seguranca_dias: 0, venda_media_dia: 0 });
    expect(created?.headers.Authorization).toBe('Bearer token-salvo');
    await waitFor(() => expect(api.gets().filter((path) => path === '/api/forecasts').length).toBeGreaterThan(before));
    expect(screen.queryByRole('form', { name: 'Novo SKU' })).not.toBeInTheDocument();
  });

  it('erro do servidor no cadastro fica no formulário, que continua aberto', async () => {
    signedIn();
    mockApi({ ...banco, 'POST skus': fail(409, 'SKU CI-9001 já existe no cadastro (ativo ou inativo).') });
    renderApp('/skus');
    await userEvent.click(await screen.findByRole('button', { name: 'Adicionar SKU' }));
    const form = screen.getByRole('form', { name: 'Novo SKU' });
    await userEvent.type(within(form).getByLabelText('Código do SKU'), 'CI-9001');
    await userEvent.type(within(form).getByLabelText('Produto'), 'Caderno Teste');
    await userEvent.click(within(form).getByRole('button', { name: 'Cadastrar SKU' }));
    expect(await within(form).findByRole('alert')).toHaveTextContent('já existe');
  });

  it('edita um SKU com o formulário preenchido pelo cadastro', async () => {
    signedIn();
    const api = mockApi(banco);
    renderApp('/skus');
    await userEvent.click(await screen.findByRole('button', { name: `Editar ${SKU_OK}` }));
    const form = screen.getByRole('form', { name: `Editar ${SKU_OK}` });
    expect(within(form).queryByLabelText('Código do SKU')).not.toBeInTheDocument();
    expect(within(form).getByLabelText('Produto')).toHaveValue('Produto sintético A');
    await userEvent.clear(within(form).getByLabelText('Lote mínimo'));
    await userEvent.type(within(form).getByLabelText('Lote mínimo'), '500');
    await userEvent.click(within(form).getByRole('button', { name: 'Salvar alterações' }));
    expect(await screen.findByText(`${SKU_OK} atualizado.`)).toBeInTheDocument();
    const updated = api.calls.find((call) => call.method === 'PUT');
    expect(updated?.path).toBe(`/api/skus/${SKU_OK}`);
    expect(updated?.body).toMatchObject({ produto: 'Produto sintético A', lote_minimo: 500 });
  });

  it('exclusão pede confirmação e explica que o histórico fica', async () => {
    signedIn();
    const api = mockApi(banco);
    renderApp('/skus');
    await userEvent.click(await screen.findByRole('button', { name: `Excluir ${SKU_OK}` }));
    expect(api.calls.some((call) => call.path.endsWith('/excluir'))).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: `Confirmar exclusão de ${SKU_OK}` }));
    expect(await screen.findByText(/excluído\. Ele sai da fila e dos cálculos; casos e decisões já registrados ficam\./)).toBeInTheDocument();
    expect(api.calls.find((call) => call.path === `/api/skus/${SKU_OK}/excluir`)?.method).toBe('POST');
  });

  it('lista os excluídos e permite reativar', async () => {
    signedIn();
    const api = mockApi(banco);
    renderApp('/skus');
    await userEvent.click(await screen.findByText('Excluídos (1)'));
    await userEvent.click(screen.getByRole('button', { name: 'Reativar' }));
    expect(await screen.findByText('OLD-009 reativado.')).toBeInTheDocument();
    expect(api.calls.some((call) => call.method === 'POST' && call.path === '/api/skus/OLD-009/reativar')).toBe(true);
  });

  it('sessão expirada volta ao login', async () => {
    signedIn();
    mockApi({ ...banco, skuRegistry: fail(401, 'Sessão inválida ou expirada. Entre novamente.') });
    renderApp('/skus');
    expect(await screen.findByText('Sua sessão expirou. Entre novamente.')).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'Entrar para cadastrar SKUs' })).toBeInTheDocument();
    expect(window.localStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('publicação somente leitura desabilita o cadastro', async () => {
    signedIn();
    mockApi({ system: { ...system, data_source: 'banco', write_enabled: false } });
    renderApp('/skus');
    expect(await screen.findByRole('button', { name: 'Adicionar SKU' })).toBeDisabled();
    expect(screen.getByText('Cadastro desabilitado nesta publicação (somente leitura).')).toBeInTheDocument();
  });

  it.each([false, true])('formulário (com sessão: %s) não tem violações de acessibilidade', async (withSession) => {
    if (withSession) signedIn();
    mockApi(banco);
    const { container } = renderApp('/skus');
    if (withSession) await userEvent.click(await screen.findByRole('button', { name: 'Adicionar SKU' }));
    await screen.findByRole('form', { name: withSession ? 'Novo SKU' : 'Entrar para cadastrar SKUs' });
    expect((await axe.run(container, { rules: { 'color-contrast': { enabled: false } }, resultTypes: ['violations'] })).violations).toEqual([]);
  });

  it('sem login exigido, o cadastro abre direto, sem formulário de login nem token', async () => {
    const api = mockApi({ system: { ...system, data_source: 'banco', auth_required: false } });
    renderApp('/skus');
    expect(await screen.findByRole('button', { name: 'Adicionar SKU' })).toBeEnabled();
    expect(screen.queryByRole('form', { name: 'Entrar para cadastrar SKUs' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sair' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: `Excluir ${SKU_OK}` }));
    await userEvent.click(screen.getByRole('button', { name: `Confirmar exclusão de ${SKU_OK}` }));
    await screen.findByText(/excluído\./);
    const writes = api.calls.filter((call) => call.path.startsWith('/api/skus'));
    expect(writes.length).toBeGreaterThan(1);
    expect(writes.every((call) => !('Authorization' in call.headers))).toBe(true);
  });
});
