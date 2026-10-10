import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { setViewport } from './setup';
import { fail, mockApi, renderApp } from './utils';

describe('navegação por teclado', () => {
  it('o primeiro Tab alcança o link "Pular para o conteúdo", que leva ao título', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/fila');
    await screen.findByRole('heading', { level: 2, name: 'Qual SKU analisar, o que fazer e quanto' });
    await user.tab();
    expect(screen.getByRole('link', { name: 'Pular para o conteúdo' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('heading', { level: 1, name: 'Fila operacional' })).toHaveFocus();
  });

  it('no desktop o menu é alcançável e ativado por teclado', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/');
    await screen.findByRole('heading', { level: 2, name: 'Indicadores' });
    const nav = screen.getByRole('navigation', { name: 'Navegação principal' });
    const parceiros = within(nav).getByRole('link', { name: /Comercial/ });
    parceiros.focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { level: 1, name: 'Oportunidades' })).toHaveFocus();
  });

  it('no celular o menu abre com foco, fecha com Esc e devolve o foco ao botão', async () => {
    const user = userEvent.setup();
    setViewport('mobile');
    mockApi();
    renderApp('/');
    const menuButton = screen.getByRole('button', { name: 'Abrir menu' });
    const aside = document.getElementById('menu-principal')!;
    expect(aside).toHaveAttribute('inert');
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    expect(menuButton).toHaveAttribute('aria-controls', 'menu-principal');

    await user.click(menuButton);
    expect(menuButton).toHaveAttribute('aria-expanded', 'true');
    expect(aside).not.toHaveAttribute('inert');
    await waitFor(() => expect(within(aside).getAllByRole('link')[0]).toHaveFocus());

    await user.keyboard('{Escape}');
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    expect(menuButton).toHaveFocus();
    expect(aside).toHaveAttribute('inert');
  });

  it('no celular escolher uma página fecha o menu', async () => {
    const user = userEvent.setup();
    setViewport('mobile');
    mockApi();
    renderApp('/');
    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    await user.click(within(document.getElementById('menu-principal')!).getByRole('link', { name: /Confiança/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Confiança nas recomendações' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Abrir menu' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('o botão do SKU na fila abre o detalhe com Enter', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/fila');
    (await screen.findByRole('button', { name: 'Ver detalhes de TEST-003' })).focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { level: 2, name: 'TEST-003' })).toBeInTheDocument();
  });
});

describe('formulários por teclado', () => {
  it('registro de decisão: campos rotulados, ordem de tabulação e envio por Enter', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    renderApp('/decisoes');
    const sku = await screen.findByLabelText('SKU');
    expect(sku).toHaveValue('');
    await user.selectOptions(sku, 'TEST-001');
    const fields = [sku, screen.getByLabelText('O que você decidiu?'), screen.getByLabelText('O dado do parceiro ajudou?'), screen.getByLabelText(/Tempo de análise/), screen.getByLabelText('Usuário'), screen.getByLabelText('Observação')];
    sku.focus();
    for (const field of fields.slice(1)) { await user.tab(); expect(field).toHaveFocus(); }
    await user.type(screen.getByLabelText('Observação'), 'Decisão por teclado');
    await user.tab();
    expect(screen.getByRole('button', { name: 'Registrar decisão' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(await screen.findByText('Decisão registrada com sucesso.')).toBeInTheDocument();
    const post = api.calls.find((call) => call.method === 'POST');
    expect(post?.body).toMatchObject({ sku: 'TEST-001', action: 'aceita', note: 'Decisão por teclado', partner_data_effect: 'nao_utilizado', analysis_minutes: null });
  });

  it('tempo de análise informado é enviado como número; erro do servidor é exibido', async () => {
    const user = userEvent.setup();
    const api = mockApi({ 'POST feedback': fail(422, 'Tempo de análise deve ser um número inteiro não negativo') });
    renderApp('/decisoes?sku=TEST-001');
    await user.type(await screen.findByLabelText(/Tempo de análise/), '15');
    await user.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    expect(await screen.findByText('Tempo de análise deve ser um número inteiro não negativo')).toBeInTheDocument();
    expect(api.calls.find((call) => call.method === 'POST')?.body).toMatchObject({ analysis_minutes: 15 });
  });

  it('criação de caso: campos rotulados e envio', async () => {
    const user = userEvent.setup();
    const api = mockApi();
    renderApp('/casos');
    await user.selectOptions(await screen.findByLabelText('SKU'), 'TEST-003');
    const form = within(document.getElementById('new-case') as HTMLElement);
    await user.type(form.getByLabelText('Responsável'), 'PCP');
    await user.selectOptions(form.getByLabelText('Status'), 'em_investigacao');
    expect(form.getByLabelText('Prazo')).toHaveAttribute('type', 'date');
    await user.click(screen.getByRole('button', { name: 'Criar caso' }));
    expect(await screen.findByText('Caso criado e incluído no acompanhamento.')).toBeInTheDocument();
    expect(api.calls.find((call) => call.method === 'POST')).toMatchObject({ path: '/api/cases', body: { sku: 'TEST-003', owner: 'PCP', status: 'em_investigacao', due_date: '' } });
  });
});
