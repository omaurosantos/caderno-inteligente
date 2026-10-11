import { useCallback } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Alert, ErrorState, LoadingState, PageIntro } from '../components';
import { CommercialMatrix, commercialActions, monthLabel, sortPartnerRows } from '../components/CommercialMatrix';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { CHALLENGE_NAMES, displayShare } from './shared';

const PAGE = 50;
const FILTER_FROM = 25;

export default function PartnerDetailPage({ refreshToken }: { refreshToken: number }) {
  const { codigo = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const sku = params.get('sku') ?? '', action = params.get('acao') ?? '', quality = params.get('qualidade') ?? '', label = params.get('rotulo') ?? '';
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const loader = useCallback(async (signal: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (sku) query.set('sku', sku); if (action) query.set('action', action); if (quality) query.set('data_quality', quality); if (label in CHALLENGE_NAMES) query.set('challenge_action', label);
    const [detail, rows] = await Promise.all([api.partnerDetail(codigo, signal), api.partnerSkus(codigo, query, signal)]);
    return { detail, rows };
  }, [codigo, sku, action, quality, label, offset]);
  const { data, error, loading, loadedAt, refresh } = useApiResource(loader, refreshToken);
  usePageLoadStatus(loading, error, loadedAt);
  const update = (key: string, value: string) => { const next = new URLSearchParams(params); next.delete('offset'); if (value) next.set(key, value); else next.delete(key); setParams(next, { replace: true }); };
  if (!data) return error ? <ErrorState message={error} onRetry={() => void refresh()} /> : <LoadingState />;
  const p = data.detail.partner;
  const total = data.rows.total;
  return <>
    <PageIntro title={p.name} description={`${p.code} · ${p.region ?? 'Região ausente'} · ${p.channel ?? 'Canal ausente'}`} action={<Link className="secondary-button" to="/carteira">Voltar aos parceiros</Link>} />
    {error && <Alert title="Falha na atualização" tone="warning" action={<button className="secondary-button" onClick={() => void refresh()}>Tentar novamente</button>}>{error}</Alert>}
    {p.visibility_source === 'faturamento_direto'
      ? <p className="summary-line">Venda direta: a venda ao consumidor é <strong>observada pelo faturamento</strong>, sem sell-out de parceiro nem estoque intermediário · último mês {monthLabel(p.latest_sell_out_month)}</p>
      : <p className="summary-line">Cobertura de dados de sell-out <strong>{displayShare(p.coverage)}</strong> ({p.observed_skus} de {p.total_catalog_skus} SKUs) · <strong>{p.action_counts.avaliar_reposicao}</strong> oportunidades de reposição · último sell-out {monthLabel(p.latest_sell_out_month)}{p.quality_counts.stale > 0 && ` · ${p.quality_counts.stale} com dado antigo`}</p>}
    {(total > FILTER_FROM || params.size > 0) && <div className="filter-bar" role="search" aria-label="Filtrar SKUs do parceiro"><label>Ação comercial<select value={action} onChange={e => update('acao', e.target.value)}><option value="">Todas</option>{Object.entries(commercialActions).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label><label>Rótulo<select value={label} onChange={e => update('rotulo', e.target.value)}><option value="">Todos</option>{['repor', 'recomendar_recompra', 'monitorar', 'investigar'].map(code => <option key={code} value={code}>{CHALLENGE_NAMES[code]}</option>)}</select></label>{(sku || quality) && <span className="filter-chip">{sku && `SKU ${sku}`}{sku && quality && ' · '}{quality && `qualidade: ${quality}`}</span>}{params.size > 0 && <button className="secondary-button" onClick={() => setParams({}, { replace: true })}>Limpar filtros</button>}</div>}
    <CommercialMatrix response={{ ...data.rows, items: sortPartnerRows(data.rows.items) }} />
    {total > PAGE && <div className="commercial-pagination"><button className="secondary-button" disabled={offset === 0} onClick={() => update('offset', String(Math.max(0, offset - PAGE)))}>Anterior</button><span>{data.rows.items.length ? data.rows.offset + 1 : 0}–{data.rows.offset + data.rows.items.length} de {total}</span><button className="secondary-button" disabled={offset + PAGE >= total} onClick={() => update('offset', String(offset + PAGE))}>Próxima</button></div>}
  </>;
}
