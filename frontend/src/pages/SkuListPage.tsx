import { useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { useSystemInfo } from '../hooks/useSystemInfo';
import { EmptyState, ErrorState, Icon, LoadingState, PageIntro, Pagination, SectionCard } from '../components';
import { SkuRegistryPanel, useSkuRegistry } from '../components/SkuRegistry';
import type { SkuRegistryItem } from '../types-registry';

const PAGE_SIZE = 10;

/** Lista completa de SKUs, com busca e família; cada linha leva à página do SKU (/skus/:sku).
 * Com a base no banco (fase 3), o bloco Cadastro permite entrar, adicionar, editar, excluir (lógica) e reativar SKUs. */
export default function SkuListPage({ refreshToken }: { refreshToken: number }) {
  const { data, error, loading, loadedAt, refresh } = useApiResource(api.forecasts, refreshToken);
  usePageLoadStatus(loading, data ? '' : error, loadedAt);
  const system = useSystemInfo();
  const registryEnabled = system?.data_source === 'banco';
  const writeEnabled = system?.write_enabled !== false;
  const registry = useSkuRegistry(registryEnabled, refreshToken, system?.auth_required === true);
  const [editing, setEditing] = useState<SkuRegistryItem | null>(null);
  const [confirming, setConfirming] = useState('');
  const [notice, setNotice] = useState('');
  const canEdit = Boolean(registry.active && registry.registry?.editable);
  const itemsBySku = new Map(registry.registry?.items.map((item) => [item.sku, item]));
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const search = params.get('busca') ?? '';
  const family = params.get('familia') ?? '';

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
    setPage(1);
  };

  const changed = (message: string) => {
    setNotice(message);
    setConfirming('');
    registry.reload();
    void refresh();
  };
  const remove = async (sku: string) => {
    if (!registry.active) return;
    try {
      await api.deleteSku(registry.token, sku);
      changed(`${sku} excluído. Ele sai da fila e dos cálculos; casos e decisões já registrados ficam.`);
    } catch (caught) {
      if (!registry.expire(caught)) setNotice(caught instanceof Error ? caught.message : 'A exclusão falhou.');
      setConfirming('');
    }
  };

  if (!data) return error ? <ErrorState message={error} onRetry={() => void refresh()} /> : <LoadingState />;
  const families = [...new Set(data.map((item) => item.family))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  const query = search.trim().toLocaleLowerCase('pt-BR');
  const filtered = data
    .filter((item) => (!query || item.sku.toLocaleLowerCase('pt-BR').includes(query) || item.product.toLocaleLowerCase('pt-BR').includes(query)) && (!family || item.family === family))
    .sort((a, b) => a.sku.localeCompare(b.sku, 'pt-BR'));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const from = `${location.pathname}${location.search}`;

  return <div className="sku-list-page">
    <PageIntro title="Todos os SKUs" description={`${data.length} SKUs no cadastro. Abra um SKU para ver resumo, evidências, parceiros e impacto financeiro.`} />
    <div className="filter-bar" role="search" aria-label="Filtrar SKUs">
      <label className="search-field"><span>Buscar</span><Icon name="search" /><input value={search} onChange={(event) => update('busca', event.target.value)} placeholder="SKU ou produto" /></label>
      <label><span>Família</span><select value={family} onChange={(event) => update('familia', event.target.value)}><option value="">Todas</option>{families.map((item) => <option key={item}>{item}</option>)}</select></label>
      <div className="filter-count" role="status"><strong>{filtered.length}</strong><span>de {data.length} SKUs</span></div>
      {params.size > 0 && <button className="secondary-button" onClick={() => { setParams({}, { replace: true }); setPage(1); }}>Limpar filtros</button>}
    </div>
    {registryEnabled && <SkuRegistryPanel state={registry} authEnabled={system?.auth_enabled !== false} writeEnabled={writeEnabled} editing={editing}
      onEdit={(item) => { setEditing(item); setNotice(''); }} onChanged={changed} />}
    {notice && <p className="form-message registry-notice" role="status">{notice}</p>}
    <SectionCard title="SKUs">
      {!visible.length ? <EmptyState title="Nenhum SKU encontrado" description="Ajuste a busca ou a família." />
        : <div className="table-shell" tabIndex={0} role="region" aria-label="Lista de SKUs; role horizontalmente para ver todas as colunas"><table className="data-table responsive-table"><thead><tr><th>SKU / Produto</th><th>Família</th><th>Posição na fila</th><th>Ação sugerida</th>{canEdit && <th>Cadastro</th>}</tr></thead><tbody>{visible.map((item) => <tr key={item.sku}>
          <td data-label="SKU"><Link className="link-button" to={`/skus/${encodeURIComponent(item.sku)}`} state={{ from }} aria-label={`Abrir ${item.sku}`}><strong>{item.sku}</strong></Link><small>{item.product}</small></td>
          <td data-label="Família">{item.family}</td>
          <td data-label="Posição na fila">{item.priority ?? <span className="queue-none">Fora da fila</span>}</td>
          <td data-label="Ação sugerida">{item.operational_recommendation.action_label}</td>
          {canEdit && <td data-label="Cadastro" className="registry-row-actions">{confirming === item.sku
            ? <><button type="button" className="secondary-button danger-button" disabled={!writeEnabled} onClick={() => void remove(item.sku)}>Confirmar exclusão de {item.sku}</button><button type="button" className="secondary-button" onClick={() => setConfirming('')}>Cancelar</button></>
            : <><button type="button" className="secondary-button" disabled={!writeEnabled || !itemsBySku.has(item.sku)} onClick={() => { const found = itemsBySku.get(item.sku); if (found) { setEditing(found); window.scrollTo({ top: 0 }); } }} aria-label={`Editar ${item.sku}`}>Editar</button>
              <button type="button" className="secondary-button" disabled={!writeEnabled} onClick={() => setConfirming(item.sku)} aria-label={`Excluir ${item.sku}`}>Excluir</button></>}</td>}
        </tr>)}</tbody></table></div>}
      <Pagination page={current} pages={pages} onChange={setPage} label="Páginas da lista de SKUs" />
    </SectionCard>
  </div>;
}
