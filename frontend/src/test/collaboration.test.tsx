import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { collaboration } from './fixtures';
import { mockApi, renderApp } from './utils';

describe('Comercial: Colaboração', () => {
  it('mostra a linha de base, a reconciliação dos dois recortes e o aviso de proposta a validar', async () => {
    const api = mockApi();
    renderApp('/colaboracao');
    await screen.findByRole('heading', { level: 2, name: 'Colaboração com parceiros' });
    expect(api.gets()).toContain('/api/collaboration');
    expect(screen.getByText('Proposta a validar')).toBeInTheDocument();
    expect(screen.getByText(/Dois recortes, ambos corretos/)).toBeInTheDocument();
    expect(screen.getByText(/Há apenas uma fotografia/)).toBeInTheDocument();
    expect(screen.getByText(/ainda não é medida/)).toBeInTheDocument();
  });

  it('lista o nível e o índice por parceiro e troca a simulação ao escolher outro parceiro', async () => {
    mockApi();
    renderApp('/colaboracao');
    const [first, second] = collaboration.partners;
    await screen.findByRole('heading', { level: 3, name: `Simulação: o que muda para ${first.name}` });
    const table = screen.getByRole('region', { name: /Parceiros do programa/ });
    expect(within(table).getAllByRole('row')).toHaveLength(collaboration.partners.length + 1);
    expect(within(table).getAllByText(/Essencial/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: `Simular ${second.code}` }));
    expect(await screen.findByRole('heading', { level: 3, name: `Simulação: o que muda para ${second.name}` })).toBeInTheDocument();
  });

  it('a simulação não promete concessão e informa a contrapartida como hipótese', async () => {
    mockApi();
    renderApp('/colaboracao');
    await screen.findByRole('region', { name: 'Simulação de níveis' });
    expect(screen.getByText(/Efeito esperado sobre os dados desta base; não é garantia nem acordo comercial/)).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /hipótese/ })).toBeInTheDocument();
  });
});
