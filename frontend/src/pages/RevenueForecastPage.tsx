import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { Icon, LoadingState, PageIntro, Pagination, SectionCard } from '../components';
import { RevenueSkuTable, RevenueSummaryCard } from '../components/RevenueForecast';

const PAGE_SIZE = 10;

/** Análise financeira separada da fila operacional. Valores são estimativas (unidades previstas × preço vigente). */
export default function RevenueForecastPage({ refreshToken }: { refreshToken: number }) {
  const { data, error, loading, loadedAt, refresh } = useApiResource(api.revenueForecast, refreshToken);
  usePageLoadStatus(loading, data ? '' : error, loadedAt);
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const search = params.get('busca') ?? '';
  const family = params.get('familia') ?? '';

  // Filtro novo volta para a primeira página.
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  if (!data && loading) return <LoadingState />;
  const families = (data?.families ?? []).map((group) => group.label);
  const query = search.trim().toLocaleLowerCase('pt-BR');
  const filtered = (data?.items ?? []).filter((item) => (!query || item.sku.toLocaleLowerCase('pt-BR').includes(query) || (item.product ?? '').toLocaleLowerCase('pt-BR').includes(query))
    && (!family || item.family === family));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const filtersActive = params.size > 0;

  return <div className="revenue-page">
    <PageIntro title="Quanto se estima faturar nos próximos três meses" description="Estimativa: unidades previstas × preço vigente. Não é faturamento realizado nem meta." />
    {/* Filtros no topo: a família também restringe o cartão de resumo. */}
    {data && <div className="filter-bar queue-filters" role="search" aria-label="Filtrar o faturamento previsto">
      <label className="search-field"><span>Buscar</span><Icon name="search" /><input value={search} onChange={(event) => update('busca', event.target.value)} placeholder="SKU ou produto" /></label>
      <label><span>Família</span><select value={family} onChange={(event) => update('familia', event.target.value)}><option value="">Todas</option>{families.map((item) => <option key={item}>{item}</option>)}</select></label>
      <div className="filter-count" role="status"><strong>{filtered.length}</strong><span>de {data.items.length} SKUs</span></div>
      {filtersActive && <button className="secondary-button queue-clear" onClick={() => { setParams({}, { replace: true }); setPage(1); }}>Limpar filtros</button>}
    </div>}
    <RevenueSummaryCard data={data} error={error} loading={loading} refresh={refresh} family={family} />
    {data && <SectionCard title="Estimativa por SKU">
      <RevenueSkuTable items={visible} />
      <Pagination page={current} pages={pages} onChange={setPage} label="Páginas da estimativa por SKU" />
    </SectionCard>}
  </div>;
}
