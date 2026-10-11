import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Alert, ErrorState, Icon, LoadingState, PageIntro } from '../components';
import { CommercialMatrix, monthLabel, opportunityOrderLabels, sortOpportunities } from '../components/CommercialMatrix';
import type { OpportunityOrder } from '../components/CommercialMatrix';
import { RegionRisk } from '../components/RegionRisk';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';

/** Oportunidades de reposição por parceiro e SKU. A lista de parceiros e os canais diretos têm página própria. */
export default function B2BPage({ refreshToken }: { refreshToken: number }) {
  const loader = useCallback((signal: AbortSignal) => api.partners(new URLSearchParams({ limit: '200' }), signal), []);
  const { data, error, loading, loadedAt, refresh } = useApiResource(loader, refreshToken);
  const [params, setParams] = useSearchParams();
  const region = params.get('regiao') ?? '', channel = params.get('canal') ?? '', sort = params.get('ordem') ?? '', search = params.get('busca') ?? '';
  const order: OpportunityOrder = sort in opportunityOrderLabels ? sort as OpportunityOrder : 'urgencia';
  const query = search.trim().toLocaleLowerCase('pt-BR');
  const includes = (...texts: string[]) => !query || texts.some(text => text.toLocaleLowerCase('pt-BR').includes(query));
  const opportunitiesLoader = useCallback(async (signal: AbortSignal) => {
    const filters = new URLSearchParams({ action: 'avaliar_reposicao', limit: '200' });
    if (region) filters.set('region', region);
    if (channel) filters.set('channel', channel);
    return api.commercialRecommendations(filters, signal);
  }, [region, channel]);
  const opportunities = useApiResource(opportunitiesLoader, refreshToken);
  const regionsLoader = useCallback((signal: AbortSignal) => api.allocationRegions(signal), []);
  const regionRisk = useApiResource(regionsLoader, refreshToken).data;
  usePageLoadStatus(loading || opportunities.loading, error || opportunities.error, loadedAt);
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); setParams(next, { replace: true }); };
  const regions = useMemo(() => [...new Set((data?.items ?? []).map(p => p.region).filter((x): x is string => !!x))].sort(), [data]);
  const channels = useMemo(() => [...new Set((data?.items ?? []).map(p => p.channel).filter((x): x is string => !!x))].sort(), [data]);
  const sorted = useMemo(() => opportunities.data ? { ...opportunities.data, items: sortOpportunities(opportunities.data.items.filter(row => includes(row.partner_name, row.partner, row.sku, row.product)), order) } : null, [opportunities.data, order, query]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return error ? <ErrorState message={error} onRetry={() => void refresh()} /> : <LoadingState />;
  const scoped = data.items.filter(p => (!region || p.region === region) && (!channel || p.channel === channel));
  const opportunityCount = scoped.reduce((sum, p) => sum + p.action_counts.avaliar_reposicao, 0);
  const partnersWithOpportunity = scoped.filter(p => p.action_counts.avaliar_reposicao > 0).length;
  return <>
    <PageIntro title="Onde há oportunidade de reposição" description={`${partnersWithOpportunity} de ${scoped.length} parceiros têm sugestão de reposição (${opportunityCount} no total). Dados até ${monthLabel(data.reference_month)}.`} />
    {error && <Alert title="Falha na atualização" tone="warning" action={<button className="secondary-button" onClick={() => void refresh()}>Tentar novamente</button>}>{error}</Alert>}
    <div className="filter-bar" role="search" aria-label="Filtrar oportunidades">
      <label className="search-field"><span>Buscar</span><Icon name="search" /><input value={search} onChange={e => update('busca', e.target.value)} placeholder="Parceiro, SKU ou produto" /></label>
      <label>Região<select value={region} onChange={e => update('regiao', e.target.value)}><option value="">Todas</option>{regions.map(r => <option key={r}>{r}</option>)}</select></label>
      <label>Canal<select value={channel} onChange={e => update('canal', e.target.value)}><option value="">Todos</option>{channels.map(c => <option key={c}>{c}</option>)}</select></label>
      <label>Ordenar<select value={order} onChange={e => update('ordem', e.target.value)}>{(Object.keys(opportunityOrderLabels) as OpportunityOrder[]).map(code => <option key={code} value={code}>{opportunityOrderLabels[code]}</option>)}</select></label>
      <div className="filter-count" role="status"><strong>{sorted?.items.length ?? 0}</strong><span>oportunidades</span></div>
      {params.size > 0 && <button className="secondary-button" onClick={() => setParams({}, { replace: true })}>Limpar filtros</button>}
    </div>
    {data.total > data.items.length && <Alert title="Lista limitada">Exibindo o primeiro lote de {data.items.length} parceiros. A API suporta paginação por limit/offset.</Alert>}
    {regionRisk && <RegionRisk data={regionRisk} />}
    {sorted && opportunities.data ? <>
      {opportunities.data.total > opportunities.data.items.length && <Alert title="Ordenação do primeiro lote">A lista mostra {opportunities.data.items.length} de {opportunities.data.total} oportunidades e a ordem vale só para esse lote.</Alert>}
      <CommercialMatrix response={sorted} />
    </> : opportunities.error ? <ErrorState message={opportunities.error} onRetry={() => void opportunities.refresh()} /> : <LoadingState />}
  </>;
}
