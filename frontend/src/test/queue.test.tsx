import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { joinQueue, rowNeedsAttention, sortQueue } from '../components/OperationalQueue';
import { allocationHeadline } from '../components/OperationalQueue';
import { SKU_OK, SKU_SHORT, challengeAllocate, forecasts, priorities } from './fixtures';
import { currentLocation, fail, mockApi, renderApp } from './utils';

const INTRO = 'Qual SKU analisar, o que fazer e quanto';
const bodyRows = () => within(screen.getByRole('region', { name: /Fila operacional/ })).getAllByRole('row').slice(1);

describe('fila operacional: junção pelo SKU', () => {
  it('une posição, ação e quantidade e mantém SKU que existe em só uma fonte', () => {
    const rows = joinQueue(priorities, forecasts);
    expect(rows.map((row) => row.sku)).toEqual([SKU_OK, SKU_SHORT, 'TEST-003']);
    expect(rows[0].priority && rows[0].forecast).toBeTruthy();
    const onlyRanking = rows.find((row) => row.sku === 'TEST-003')!;
    expect(onlyRanking.forecast).toBeUndefined();
    expect(rowNeedsAttention(onlyRanking)).toBe(true);
    const onlyForecast = joinQueue([], forecasts);
    expect(onlyForecast.every((row) => row.priority === undefined && row.position !== null)).toBe(true);
  });

  it('ordena por posição e deixa SKU sem previsão por último nas ordens numéricas', () => {
    const rows = joinQueue(priorities, forecasts);
    expect(sortQueue(rows, 'priority').map((row) => row.sku)).toEqual([SKU_OK, SKU_SHORT, 'TEST-003']);
    expect(sortQueue(rows, 'suggested_quantity')[2].sku).toBe('TEST-003');
  });
});

describe('fila operacional: página', () => {
  it('mostra ação e quantidade na mesma linha da posição e do motivo, com cinco colunas', async () => {
    mockApi();
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    const headers = within(screen.getByRole('region', { name: /Fila operacional/ })).getAllByRole('columnheader').map((header) => header.textContent);
    expect(headers).toEqual(['Posição e SKU', 'Ação sugerida', 'Quantidade sugerida (un.)', 'Motivo principal', 'Exceções']);
    const first = bodyRows()[0];
    expect(within(first).getByText('Produzir')).toBeInTheDocument();
    expect(within(first).getByTitle(/^Posição na fila de atenção/)).toHaveTextContent('1');
    // Previsão completa, cálculo e erro do modelo ficam no detalhe do SKU.
    expect(within(screen.getByRole('region', { name: /Fila operacional/ })).queryByRole('columnheader', { name: /Próximo mês/ })).not.toBeInTheDocument();
  });

  it('SKU só no ranking aparece sem ação inventada e sem quantidade zero', async () => {
    mockApi();
    renderApp('/fila');
    const row = (await screen.findByRole('button', { name: 'Ver detalhes de TEST-003' })).closest('tr') as HTMLElement;
    expect(within(row).getByText('Sem previsão para este SKU')).toBeInTheDocument();
    expect(within(row).getByText('Não disponível')).toBeInTheDocument();
    expect(within(row).queryByText('0')).not.toBeInTheDocument();
  });

  it('falha das previsões mantém a posição e avisa que ação e quantidade estão indisponíveis', async () => {
    mockApi({ forecasts: fail(500, 'Previsões fora do ar') });
    renderApp('/fila');
    expect(await screen.findByText('Ação e quantidade indisponíveis')).toBeInTheDocument();
    expect(screen.getByText(/Previsões fora do ar/)).toBeInTheDocument();
    expect(bodyRows()).toHaveLength(3);
    const row = bodyRows()[0];
    expect(within(row).getByText('Ação indisponível')).toBeInTheDocument();
    expect(within(row).queryByText('Produzir')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });

  it('falha das prioridades mantém ação e quantidade, sem a posição', async () => {
    mockApi({ priorities: fail(500, 'Ranking fora do ar') });
    renderApp('/fila?todos=1');
    expect(await screen.findByText('Posição e motivo indisponíveis')).toBeInTheDocument();
    const first = bodyRows()[0];
    expect(within(first).getByText('Produzir')).toBeInTheDocument();
    expect(within(first).getByText('Indisponível')).toBeInTheDocument();
  });

  it('falha das configurações não impede a fila', async () => {
    mockApi({ config: fail(500, 'Configuração indisponível') });
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    expect(bodyRows()).toHaveLength(3);
  });

  it('ordem escolhida fica na URL; ordem inválida cai na posição', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/fila?ordem=invalida&todos=1');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    expect(screen.getByLabelText('Ordenar por')).toHaveValue('priority');
    await user.selectOptions(screen.getByLabelText('Ordenar por'), 'suggested_quantity');
    await waitFor(() => expect(currentLocation()).toContain('ordem=suggested_quantity'));
  });

  it('os endereços antigos preservam os parâmetros ao redirecionar para a fila', async () => {
    mockApi();
    renderApp('/previsoes?acao=investigar_dados&ordem=suggested_quantity');
    await screen.findByRole('heading', { level: 2, name: INTRO });
    expect(currentLocation()).toBe('/fila?acao=investigar_dados&ordem=suggested_quantity');
  });

  it('abre o SKU com um clique e volta para a fila com os mesmos filtros', async () => {
    const user = userEvent.setup();
    mockApi();
    renderApp('/prioridades?familia=Fam%C3%ADlia+A&todos=1');
    await user.click(await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` }));
    expect(await screen.findByRole('heading', { level: 2, name: SKU_OK })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Voltar' }));
    await waitFor(() => expect(currentLocation()).toBe('/fila?familia=Fam%C3%ADlia+A&todos=1'));
  });
});

describe('fila operacional: faixa, valor e disputa (Etapa 16)', () => {
  it('o motivo começa pela faixa e pelo valor em risco, sem coluna nova', async () => {
    mockApi();
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    const region = screen.getByRole('region', { name: /Fila operacional/ });
    expect(within(region).getAllByRole('columnheader')).toHaveLength(5);
    const reason = within(bodyRows()[0]).getByText('Pedido confirmado sem cobertura');
    expect(reason.closest('td')).toHaveTextContent(/^Pedido confirmado sem cobertura R\$ 1\.4 mil em risco \(KA-T\)/);
  });

  it('o detalhe do cálculo traz ABC medida × cadastro, observado × estimado e a pontuação, sem aparecer como coluna', async () => {
    mockApi();
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    const rank = within(bodyRows()[0]).getByTitle(/^Posição na fila de atenção/);
    expect(rank.getAttribute('title')).toMatch(/Curva ABC medida pelo faturamento dos últimos 12 meses: A; no cadastro está C/);
    expect(rank.getAttribute('title')).toMatch(/observado em pedidos e .* estimado pela previsão/);
    expect(rank.getAttribute('title')).toMatch(/Pontuação dos sinais: 29/);
    // Leitor de tela recebe o mesmo texto no motivo.
    expect(bodyRows()[0].querySelector('.queue-reason .sr-only')?.textContent).toMatch(/Curva ABC medida/);
  });

  it('SKU disputado mostra "Atender X antes de Y" no motivo', async () => {
    mockApi({ forecasts: forecasts.map((item, index) => index === 0 ? { ...item, challenge_action: challengeAllocate } : item) });
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    expect(within(bodyRows()[0]).getByText('Atender KA-T1 antes de KA-T2.')).toBeInTheDocument();
    expect(within(bodyRows()[1]).queryByText(/Atender/)).not.toBeInTheDocument();
  });

  it('sem priority_reason (resposta antiga) mantém o motivo pelo sinal mais pesado', async () => {
    mockApi({ priorities: priorities.map((item) => ({ ...item, priority_reason: undefined })) });
    renderApp('/fila');
    await screen.findByRole('button', { name: `Ver detalhes de ${SKU_OK}` });
    expect(within(bodyRows()[1]).getByText(/Falta|cobertura|lead time/i)).toBeInTheDocument();
  });

  it('allocationHeadline só vale para a alavanca alocar', () => {
    expect(allocationHeadline(challengeAllocate)).toBe('Atender KA-T1 antes de KA-T2.');
    expect(allocationHeadline({ ...challengeAllocate, lever: 'antecipar_op' })).toBeUndefined();
    expect(allocationHeadline(undefined)).toBeUndefined();
  });
});
