import { useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, dashboardReaders } from '../api';
import { Alert, Badge, EmptyState, ErrorState, Icon, LoadingState, PageIntro, SectionCard } from '../components';
import { ChallengeBadge } from '../components/ChallengeAction';
import { monthLabel } from '../components/CommercialMatrix';
import { VisibilityJourney } from '../components/VisibilityJourney';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { CHALLENGE_NAMES, displayShare } from './shared';

/** Parceiros cadastrados com cobertura de dados de sell-out e quantidade de sugestões. */
export default function PartnersListPage({ refreshToken }: { refreshToken: number }) {
  const loader = useCallback((signal: AbortSignal) => api.partners(new URLSearchParams({ limit: '200' }), signal), []);
  const { data, error, loading, loadedAt, refresh } = useApiResource(loader, refreshToken);
  usePageLoadStatus(loading, error, loadedAt);
  const journeyLoader = useCallback((signal: AbortSignal) => dashboardReaders.b2b(signal), []);
  const journey = useApiResource(journeyLoader, refreshToken).data?.journey ?? null;
  const [params, setParams] = useSearchParams();
  const region = params.get('regiao') ?? '', channel = params.get('canal') ?? '', sort = params.get('ordem') ?? 'opportunities', label = params.get('rotulo') ?? '', search = params.get('busca') ?? '';
  const query = search.trim().toLocaleLowerCase('pt-BR');
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); setParams(next, { replace: true }); };
  const regions = useMemo(() => [...new Set((data?.items ?? []).map(p => p.region).filter((x): x is string => !!x))].sort(), [data]);
  const channels = useMemo(() => [...new Set((data?.items ?? []).map(p => p.channel).filter((x): x is string => !!x))].sort(), [data]);
  const filtered = useMemo(() => (data?.items ?? []).filter(p => (!region || p.region === region) && (!channel || p.channel === channel) && (!label || p.challenge_action?.code === label))
    .sort((a, b) => sort === 'coverage' ? b.coverage - a.coverage || a.name.localeCompare(b.name) : sort === 'name' ? a.name.localeCompare(b.name) : b.action_counts.avaliar_reposicao - a.action_counts.avaliar_reposicao || a.name.localeCompare(b.name)), [data, region, channel, sort, label]);
  if (!data) return error ? <ErrorState message={error} onRetry={() => void refresh()} /> : <LoadingState />;
  const listed = filtered.filter(p => !query || p.name.toLocaleLowerCase('pt-BR').includes(query) || p.code.toLocaleLowerCase('pt-BR').includes(query));
  return <>
    <PageIntro title="Parceiros e cobertura de dados" description={`${listed.length} parceiros. Dados até ${monthLabel(data.reference_month)}.`} />
    {error && <Alert title="Falha na atualização" tone="warning" action={<button className="secondary-button" onClick={() => void refresh()}>Tentar novamente</button>}>{error}</Alert>}
    <div className="filter-bar" role="search" aria-label="Filtrar parceiros">
      <label className="search-field"><span>Buscar</span><Icon name="search" /><input value={search} onChange={e => update('busca', e.target.value)} placeholder="Parceiro" /></label>
      <label>Região<select value={region} onChange={e => update('regiao', e.target.value)}><option value="">Todas</option>{regions.map(r => <option key={r}>{r}</option>)}</select></label>
      <label>Canal<select value={channel} onChange={e => update('canal', e.target.value)}><option value="">Todos</option>{channels.map(c => <option key={c}>{c}</option>)}</select></label>
      <label>Rótulo<select value={label} onChange={e => update('rotulo', e.target.value)}><option value="">Todos</option><option value="priorizar_parceiro">{CHALLENGE_NAMES.priorizar_parceiro}</option></select></label>
      <label>Ordenar<select value={sort} onChange={e => update('ordem', e.target.value)}><option value="opportunities">Sugestões de reposição</option><option value="coverage">Cobertura de dados de sell-out</option><option value="name">Nome</option></select></label>
      <div className="filter-count" role="status"><strong>{listed.length}</strong><span>parceiros</span></div>
      {params.size > 0 && <button className="secondary-button" onClick={() => setParams({}, { replace: true })}>Limpar filtros</button>}
    </div>
    {data.total > data.items.length && <Alert title="Lista limitada">Exibindo o primeiro lote de {data.items.length} parceiros. A API suporta paginação por limit/offset.</Alert>}
    {journey && <VisibilityJourney journey={journey} />}
    <SectionCard title="Parceiros e canais">
      {!listed.length ? <EmptyState title="Nenhum parceiro neste filtro" description="Ajuste região e canal. Ausência de informação não significa venda zero." /> : <div className="table-shell" tabIndex={0} role="region" aria-label="Parceiros; role horizontalmente para ver todas as colunas"><table className="data-table responsive-table"><thead><tr><th>Parceiro</th><th>Visibilidade da venda</th><th>Oportunidades</th><th>Sem dados suficientes</th><th><span className="sr-only">Abrir</span></th></tr></thead><tbody>{listed.map(p => <tr key={p.code}>
        <td data-label="Parceiro"><strong>{p.name}</strong><small>{p.region ?? 'Região ausente'} · {p.channel ?? 'Canal ausente'}</small><ChallengeBadge action={p.challenge_action} /></td>
        {p.visibility_source === 'faturamento_direto'
          ? <td data-label="Visibilidade da venda"><Badge tone="ok">Venda direta</Badge><small>observada no faturamento</small></td>
          : <td data-label="Visibilidade da venda">{displayShare(p.coverage)}<small>sell-out do parceiro</small></td>}
        <td data-label="Oportunidades">{p.visibility_source === 'faturamento_direto' ? 'Não se aplica' : p.action_counts.avaliar_reposicao}</td>
        <td data-label="Sem dados">{p.visibility_source === 'faturamento_direto' ? 'Não se aplica' : p.quality_counts.insufficient}</td>
        <td className="cell-action"><Link className="secondary-button" to={`/parceiros/${encodeURIComponent(p.code)}`} aria-label={`Abrir parceiro ${p.name} e evidências`}>Abrir</Link></td>
      </tr>)}</tbody></table></div>}
    </SectionCard>
  </>;
}
