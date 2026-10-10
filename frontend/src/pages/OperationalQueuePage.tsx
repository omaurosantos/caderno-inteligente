import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, dashboardReaders } from '../api';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { Alert, ErrorState, Icon, LoadingState, PageIntro, Pagination, SectionCard, hasRuptureRisk } from '../components';
import { OperationalQueueTable, joinQueue, rowNeedsAttention, sortQueue } from '../components/OperationalQueue';
import { ProductionPlanChart } from '../components/ProductionPlanChart';
import { AttentionFocus } from '../components/AttentionFocus';
import type { QueueRow, QueueSort } from '../components/OperationalQueue';
import type { SelectedSku } from '../types';

const toSelected = (row: QueueRow): SelectedSku => ({
  sku: row.sku, product: row.product, family: row.family, priority: row.position,
  attention_score: row.priority?.attention_score ?? row.forecast?.attention_score ?? null,
  confidence: row.priority?.confidence ?? row.forecast?.confidence ?? 'média',
  confidence_reason: row.priority?.confidence_reason ?? row.forecast?.confidence_reason ?? '',
});

const SORTS: QueueSort[] = ['priority', 'suggested_quantity', 'forecast_next_month', 'backtest_wape'];
const PAGE_SIZE = 10;

/**
 * Fila única: posição (prioridades) + ação e quantidade (previsões), unidas pelo SKU no cliente.
 * Cada fonte falha sozinha: a outra continua exibida e o que falta aparece como indisponível, nunca como zero.
 */
export default function OperationalQueuePage({ onSelect, refreshToken }: { onSelect: (item: SelectedSku) => void; refreshToken: number }) {
  const priorities = useApiResource(dashboardReaders.priorities, refreshToken);
  const forecasts = useApiResource(api.forecasts, refreshToken);
  const config = useApiResource(dashboardReaders.config, refreshToken);
  // Camada aditiva: eventos carregam à parte e nunca bloqueiam a fila. O faturamento tem página própria.
  const { data: events } = useApiResource(api.events, refreshToken);
  const productionPlan = useApiResource(api.productionPlan, refreshToken);
  const eventsBySku = useMemo(() => new Map((events?.items ?? []).map((item) => [item.sku, item])), [events]);

  const loading = priorities.loading || forecasts.loading;
  const bothFailed = !priorities.data && !forecasts.data && !!(priorities.error || forecasts.error);
  usePageLoadStatus(loading, bothFailed ? priorities.error || forecasts.error : '', priorities.loadedAt ?? forecasts.loadedAt);

  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const search = params.get('busca') ?? '';
  const family = params.get('familia') ?? '';
  const action = params.get('acao') ?? '';
  const label = params.get('rotulo') ?? '';
  const confidence = params.get('confianca') ?? '';
  const rupture = params.get('sinal') === 'ruptura';
  const showAll = params.get('todos') === '1';
  const requestedSort = params.get('ordem') as QueueSort | null;
  const sort: QueueSort = requestedSort && SORTS.includes(requestedSort) ? requestedSort : 'priority';
  // Só o que pede atenção por padrão; buscar, escolher ação/rótulo/confiança/sinal ou pedir todos mostra tudo o que combina.
  const attentionOnly = !showAll && !action && !label && !confidence && !rupture && !search.trim() && !!forecasts.data;

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value && value !== 'priority') next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  const all = useMemo(() => joinQueue(priorities.data, forecasts.data), [priorities.data, forecasts.data]);
  const families = useMemo(() => [...new Set(all.map((row) => row.family))].sort(), [all]);
  const labels = useMemo(() => [...new Map((forecasts.data ?? []).filter((item) => item.challenge_action).map((item) => [item.challenge_action!.code, item.challenge_action!.label])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'pt-BR')), [forecasts.data]);
  const filtered = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('pt-BR');
    return sortQueue(all.filter((row) => (!query || row.sku.toLocaleLowerCase('pt-BR').includes(query) || row.product.toLocaleLowerCase('pt-BR').includes(query))
      && (!family || row.family === family)
      && (!action || row.forecast?.operational_recommendation.action === action)
      && (!label || row.forecast?.challenge_action?.code === label)
      && (!confidence || (row.priority?.confidence ?? row.forecast?.confidence) === confidence)
      && (!rupture || hasRuptureRisk(row.priority?.reasons))
      && (!attentionOnly || rowNeedsAttention(row))), sort);
  }, [action, all, attentionOnly, confidence, family, label, rupture, search, sort]);

  if (loading && !priorities.data && !forecasts.data) return <LoadingState />;
  if (bothFailed) return <ErrorState message={priorities.error || forecasts.error} onRetry={() => { void priorities.refresh(); void forecasts.refresh(); }} />;

  const source = forecasts.data ?? [];
  const production = source.filter((item) => ['produzir', 'produzir_validar_capacidade', 'atraso_inevitavel', 'antecipar_op'].includes(item.operational_recommendation.action)).length;
  const capacity = source.filter((item) => item.operational_recommendation.capacity_status === 'requires_review').length;
  const investigate = source.filter((item) => item.forecast.status === 'insufficient_data' || item.operational_recommendation.action === 'investigar_dados').length;
  const description = forecasts.data
    ? `${production} SKUs para produzir · ${capacity} com capacidade a validar${investigate > 0 ? ` · ${investigate} para investigar dados` : ''}`
    : 'Posição de cada SKU na fila de atenção. A ação e a quantidade sugeridas estão indisponíveis agora.';
  const filtersActive = params.size > 0;
  // 10 SKUs por página, só com troca de página (sem "ver mais"). A página volta para a 1 a cada filtro.
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const noFilters = !action && !label && !confidence && !rupture && !search.trim();
  const retry = () => { void priorities.refresh(); void forecasts.refresh(); void config.refresh(); };
  const clear = () => { setParams({}, { replace: true }); setPage(1); };
  const goTo = (next: number) => {
    setPage(next);
    // Ao trocar de página, volta ao começo da lista (o botão fica no fim dela).
    document.getElementById('fila-skus')?.scrollIntoView?.({ block: 'start' });
  };

  return <div className="operational-queue">
    <PageIntro title="Qual SKU analisar, o que fazer e quanto" description={description} action={<div className="validation-actions"><Link className="secondary-button" to="/capacidade">Ver capacidade</Link><Link className="secondary-button" to="/cenarios">Simular pesos</Link></div>} />
    {forecasts.error && priorities.data && <Alert tone="warning" title="Ação e quantidade indisponíveis" action={<button className="secondary-button" onClick={retry}>Tentar novamente</button>}>{forecasts.error} A posição na fila continua exibida; nenhuma sugestão foi estimada no lugar.</Alert>}
    {priorities.error && forecasts.data && <Alert tone="warning" title="Posição e motivo indisponíveis" action={<button className="secondary-button" onClick={retry}>Tentar novamente</button>}>{priorities.error} Ação e quantidade continuam exibidas, sem a ordem da fila de atenção.</Alert>}
    {priorities.data && <AttentionFocus priorities={priorities.data} weights={config.data?.weights} onSelect={onSelect} />}
    <div className="filter-bar queue-filters" role="search" aria-label="Filtrar a fila operacional">
      <label className="search-field"><span>Buscar</span><Icon name="search" /><input value={search} onChange={(event) => update('busca', event.target.value)} placeholder="SKU ou produto" /></label>
      <label><span>Ação</span><select value={action} onChange={(event) => update('acao', event.target.value)}><option value="">Todas</option><option value="atraso_inevitavel">Falta inevitável</option><option value="antecipar_op">Antecipar OP</option><option value="produzir">Produzir</option><option value="produzir_validar_capacidade">Produzir e validar capacidade</option><option value="rever_op">Rever OP</option><option value="monitorar_excesso">Monitorar excesso</option><option value="investigar_dados">Investigar dados</option><option value="sem_acao_necessaria">Sem ação necessária</option></select></label>
      <label><span>Família</span><select value={family} onChange={(event) => update('familia', event.target.value)}><option value="">Todas</option>{families.map((item) => <option key={item}>{item}</option>)}</select></label>
      <div className="filter-count" role="status"><strong>{filtered.length}</strong><span>de {all.length} SKUs</span></div>
      <details className="more-filters">
        <summary>Mais filtros</summary>
        <div className="more-filters-grid">
          {labels.length > 0 && <label><span>Rótulo</span><select value={label} onChange={(event) => update('rotulo', event.target.value)}><option value="">Todos</option>{labels.map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label>}
          <label><span>Sinal</span><select value={rupture ? 'ruptura' : ''} onChange={(event) => update('sinal', event.target.value)}><option value="">Todos</option><option value="ruptura">Risco de ruptura</option></select></label>
          <label><span>Confiança nos dados</span><select value={confidence} onChange={(event) => update('confianca', event.target.value)}><option value="">Todas</option><option value="baixa">Baixa</option><option value="média">Média</option><option value="alta">Alta</option></select></label>
          <label><span>Ordenar por</span><select value={sort} onChange={(event) => update('ordem', event.target.value)}><option value="priority">Posição na fila de atenção</option><option value="suggested_quantity">Maior quantidade sugerida</option><option value="forecast_next_month">Maior previsão do próximo mês</option><option value="backtest_wape">Maior erro da previsão</option></select></label>
        </div>
      </details>
      {filtersActive && <button className="secondary-button queue-clear" onClick={clear}>Limpar filtros</button>}
    </div>
    <ProductionPlanChart data={productionPlan.data} error={productionPlan.error} loading={productionPlan.loading} refresh={productionPlan.refresh} family={family} />
    <div id="fila-skus" className="queue-list"><SectionCard title={attentionOnly ? `SKUs que pedem atenção (${filtered.length} de ${all.length})` : 'Ação e quantidade por SKU'} action={attentionOnly ? <button className="secondary-button" onClick={() => update('todos', '1')}>Ver os {all.length} SKUs</button> : showAll && noFilters ? <button className="secondary-button" onClick={() => update('todos', '')}>Só os que pedem atenção</button> : undefined}>
      <OperationalQueueTable rows={visible} onSelect={(row) => onSelect(toSelected(row))} weights={config.data?.weights} eventsBySku={eventsBySku} forecastsLoaded={!!forecasts.data} prioritiesLoaded={!!priorities.data} />
      <Pagination page={current} pages={pages} onChange={goTo} label="Páginas da fila operacional" />
    </SectionCard></div>
  </div>;
}
