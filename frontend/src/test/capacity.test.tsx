import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { capacityPlan, SKU_OK } from './fixtures';
import { mockApi, renderApp } from './utils';

// Etapa 15.4: onde a produção planejada não cabe na capacidade livre de cada linha.
describe('capacidade semanal', () => {
  it('mostra cada família com a situação e explica a falta', async () => {
    const api = mockApi();
    renderApp('/capacidade');
    const table = await screen.findByRole('region', { name: 'Capacidade por linha' });
    const escolar = within(table).getByText('Escolar').closest('tr') as HTMLElement;
    expect(escolar).toHaveTextContent('Não cabe');
    expect(escolar).toHaveTextContent('800');
    expect(within(table).getByText('Refis').closest('tr')).toHaveTextContent('Cabe');
    expect(screen.getByText(new RegExp(`SKUs ${SKU_OK}`))).toHaveTextContent('PED-1 (KA-01)');
    expect(api.gets()).toContain('/api/capacity-plan');
  });

  it('fica em Planejamento e se abre pela fila, como Cenários', async () => {
    mockApi();
    const queue = renderApp('/fila');
    await screen.findByRole('heading', { level: 2, name: 'Qual SKU analisar, o que fazer e quanto' });
    expect(screen.getByRole('link', { name: 'Ver capacidade' })).toHaveAttribute('href', '/capacidade');
    queue.unmount();
    renderApp('/capacidade');
    await screen.findByRole('region', { name: 'Capacidade por linha' });
    expect(within(screen.getByRole('navigation', { name: 'Navegação principal' })).getByRole('link', { name: /Planejamento/ })).toHaveAttribute('aria-current', 'page');
  });

  // Etapa 16.5: semanas além do calendário da base são estimadas e nunca se confundem com as observadas.
  it('marca como estimadas as semanas além do calendário e explica a legenda', async () => {
    mockApi();
    renderApp('/capacidade');
    await screen.findByRole('region', { name: 'Capacidade por linha' });
    const weeks = screen.getByRole('region', { name: 'Semanas da Linha Escolar', hidden: true });
    const estimated = within(weeks).getByText('05/10/2026', { exact: false }).closest('tr') as HTMLElement;
    expect(estimated).toHaveClass('week-estimated');
    expect(estimated).toHaveTextContent('estimada');
    expect(within(weeks).getByText('21/09/2026').closest('tr')).not.toHaveClass('week-estimated');
    expect(within(weeks).getByText('estimada')).toHaveAttribute('title', expect.stringContaining('média dos compromissos das últimas 8 semanas'));
    expect(screen.getByText(/Hachurado = estimado/)).toBeInTheDocument();
  });

  it('o número de semanas da média vem da API; sem o bloco extension o texto não cita número', async () => {
    mockApi({ capacityPlan: { ...capacityPlan, extension: { enabled: true, method: 'media_compromissos_8_semanas', lookback_weeks: 6, scenario: 'central' } } });
    const first = renderApp('/capacidade');
    await screen.findByRole('region', { name: 'Capacidade por linha' });
    expect(screen.getByText('estimada')).toHaveAttribute('title', expect.stringContaining('das últimas 6 semanas'));
    expect(screen.getAllByRole('tooltip', { hidden: true }).map((tip) => tip.textContent).join(' ')).toContain('média dos compromissos de 6 semanas');
    first.unmount();
    const { extension: _extension, ...legacy } = capacityPlan;
    mockApi({ capacityPlan: legacy });
    renderApp('/capacidade');
    await screen.findByRole('region', { name: 'Capacidade por linha' });
    const title = screen.getByText('estimada').getAttribute('title') ?? '';
    expect(title).toContain('média dos compromissos das últimas semanas');
    expect(title).not.toMatch(/\d+ semanas/);
    expect(screen.getAllByRole('tooltip', { hidden: true }).map((tip) => tip.textContent).join(' ')).toContain('média dos compromissos recentes');
  });

  it('mostra os cenários central e conservador no pico, com o estimado sinalizado', async () => {
    mockApi();
    renderApp('/capacidade');
    const table = await screen.findByRole('region', { name: 'Cenários no pico' });
    expect(within(table).getByRole('columnheader', { name: 'Central' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Conservador' })).toBeInTheDocument();
    const escolar = within(table).getByText('Escolar').closest('tr') as HTMLElement;
    expect(escolar).toHaveTextContent('Não cabe 800');
    expect(escolar).toHaveTextContent('Não cabe 950');
    const refis = within(table).getByText('Refis').closest('tr') as HTMLElement;
    expect(refis).toHaveTextContent('Cabe (estimado)');
    expect(refis).toHaveTextContent('Não cabe (estimado) 120');
    expect(within(refis).getByText('Cabe (estimado)')).toHaveClass('badge-good-estimated');
    expect(within(refis).getByText('Não cabe (estimado)')).toHaveClass('badge-critical-estimated');
  });

  it('status estimado na linha aparece como falta estimada, com a quantidade', async () => {
    const [escolar, refis] = capacityPlan.families;
    mockApi({ capacityPlan: { ...capacityPlan, families: [escolar, { ...refis, status: 'insuficiente_estimado', unscheduled_quantity: 120, first_shortfall_due: '2027-02-10', skus_short: ['CI-0014'] }] } });
    renderApp('/capacidade');
    const table = await screen.findByRole('region', { name: 'Capacidade por linha' });
    expect(within(table).getByText('Refis').closest('tr')).toHaveTextContent('Não cabe (estimado)');
    expect(screen.getByText(/120 un\. sem programação \(estimado\)/)).toBeInTheDocument();
  });

  it('respostas sem cenários usam o status do pico e deixam o conservador em branco', async () => {
    const [escolar] = capacityPlan.families;
    const { scenarios: _scenarios, ...legacy } = escolar;
    mockApi({ capacityPlan: { ...capacityPlan, families: [legacy] } });
    renderApp('/capacidade');
    const row = (await screen.findByRole('region', { name: 'Cenários no pico' })).querySelector('tbody tr') as HTMLElement;
    expect(row).toHaveTextContent('Não cabe');
    expect(row).toHaveTextContent('—');
  });
});
