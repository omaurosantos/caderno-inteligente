import { useState } from 'react';
import { MOBILE_LIST_QUERY, useMediaQuery } from '../hooks/useMediaQuery';
import { Link } from 'react-router-dom';
import { Badge, EmptyState, Hint, SectionCard } from '../components';
import { ChallengeBadge } from './ChallengeAction';
import type { ChallengeAction } from '../types-actions';
import type { CommercialPage, CommercialRow } from '../types-commercial';
import { displayDays, displayNumber, displayShare, displayUnits, formatDate, localizeText } from '../pages/shared';

export const qualityLabels = { sufficient: 'Suficiente no recorte', stale: 'Antigo/descontínuo', insufficient: 'Insuficiente' };
export const commercialActions = { avaliar_reposicao: 'Avaliar reposição', monitorar_estoque: 'Monitorar estoque do parceiro', investigar_divergencia: 'Investigar divergência', solicitar_atualizacao: 'Solicitar atualização dos dados', dados_insuficientes: 'Sem recomendação por dados insuficientes', conter_reposicao: 'Não repor; acionar sell-out com o parceiro', monitorar_excesso_parceiro: 'Monitorar estoque alto no parceiro' };
export const monthLabel = (value: string | null) => value ? value.split('-').reverse().join('/') : 'Não disponível';

const thresholdNames: Record<string, string> = {
  recent_months: 'Meses recentes considerados',
  minimum_sell_out_months: 'Mínimo de meses com sell-out',
  maximum_age_months: 'Idade máxima do dado (meses)',
  reposition_coverage_days: 'Cobertura que sugere reposição (dias)',
  excess_coverage_days: 'Cobertura que indica excesso (dias)',
  minimum_excess_stock: 'Estoque mínimo para apontar excesso (unidades)',
  divergence_ratio: 'Divergência sell-in × sell-out (proporção)',
  minimum_divergence_quantity: 'Divergência mínima (unidades)',
  buildup_months: 'Janela de acúmulo no parceiro (meses)',
  buildup_max_sell_through: 'Sell-through máximo para acúmulo (proporção)',
  buildup_min_stock_growth: 'Crescimento mínimo do estoque para acúmulo (proporção)',
  stock_identity_tolerance: 'Tolerância da conta de estoque (unidades)',
};

const rowKey = (row: CommercialRow) => `${row.partner}-${row.sku}`;

const NO_VALUE = Number.POSITIVE_INFINITY;
const ascending = (value: number | null) => value === null ? NO_VALUE : value;
const descending = (value: number | null) => value === null ? NO_VALUE : -value;
const stable = (left: CommercialRow, right: CommercialRow) => left.partner_name.localeCompare(right.partner_name, 'pt-BR') || left.sku.localeCompare(right.sku, 'pt-BR');

/** Oportunidades: menor cobertura de estoque primeiro; maior giro no desempate; parceiro e SKU como desempate final. Valor ausente vai por último, nunca vira zero. */
export const opportunityOrders = {
  urgencia: (left: CommercialRow, right: CommercialRow) => ascending(left.coverage_days) - ascending(right.coverage_days) || descending(left.average_monthly_sell_out) - descending(right.average_monthly_sell_out) || stable(left, right),
  giro: (left: CommercialRow, right: CommercialRow) => descending(left.average_monthly_sell_out) - descending(right.average_monthly_sell_out) || ascending(left.coverage_days) - ascending(right.coverage_days) || stable(left, right),
  parceiro: stable,
};
export type OpportunityOrder = keyof typeof opportunityOrders;
export const opportunityOrderLabels: Record<OpportunityOrder, string> = { urgencia: 'Menor cobertura de estoque', giro: 'Maior giro', parceiro: 'Parceiro e SKU' };
export const sortOpportunities = (rows: CommercialRow[], order: OpportunityOrder) => [...rows].sort(opportunityOrders[order]);

/** Detalhe do parceiro: o que pede ação vem antes, depois as insuficiências de dados, depois os demais SKUs. */
const actionable: CommercialRow['action'][] = ['conter_reposicao', 'avaliar_reposicao', 'investigar_divergencia', 'solicitar_atualizacao'];
const isBuildup = (row: CommercialRow) => row.signals.some((signal) => signal.code === 'PARTNER_STOCK_BUILDUP');
const BuildupBadge = ({ row }: { row: CommercialRow }) => isBuildup(row) ? <Badge tone="critical">Estoque acumulando</Badge> : null;
const rank = (row: CommercialRow) => actionable.includes(row.action) ? 0 : row.action === 'dados_insuficientes' || row.data_quality === 'insufficient' ? 1 : 2;
export const sortPartnerRows = (rows: CommercialRow[]) => [...rows].sort((left, right) => rank(left) - rank(right) || ascending(left.coverage_days) - ascending(right.coverage_days) || stable(left, right));

/** Evidência de um vínculo parceiro–SKU: o motivo, três números e a origem mensal. */
function Evidence({ row }: { row: CommercialRow }) {
  return <div className="evidence-body">
    <p><strong>Por que esta sugestão:</strong> {localizeText(row.recommendation_reason)}</p>
    <dl className="evidence-figures">
      <div><dt>Enviado (sell-in)</dt><dd>{displayUnits(row.sell_in_recent)}{row.sell_in_months.length === 0 && <small>Não observado</small>}</dd></div>
      <div><dt>Vendido (sell-out)</dt><dd>{displayUnits(row.sell_out_recent)}{row.sell_out_months.length === 0 ? <small>Não observado</small> : <small>{row.sell_out_months.map(monthLabel).join(', ')}</small>}</dd></div>
      <div><dt>Estoque estimado</dt><dd>{displayUnits(row.estimated_stock)}<small>{monthLabel(row.stock_month)} · estimado</small></dd></div>
      {isBuildup(row) && <div><dt>Vendido ÷ enviado</dt><dd>{displayShare(row.sell_through_window)}<small>{row.buildup_window_months} meses · estoque {displayNumber(row.stock_start)} → {displayNumber(row.estimated_stock)}</small></dd></div>}
    </dl>
    <div className="table-shell" tabIndex={0} role="region" aria-label={`Origem mensal de ${row.partner} e ${row.sku}`}><table className="data-table"><caption>Origem: Sell_In e Sell_Out · {row.partner} · {row.sku}</caption><thead><tr><th>Mês</th><th>Enviado</th><th>Vendido</th><th>Estoque estimado</th></tr></thead><tbody>{row.periods.map(period => <tr key={period.month}><td>{monthLabel(period.month)}</td><td>{displayNumber(period.sell_in_quantity)}</td><td>{displayNumber(period.sell_out_quantity)}</td><td>{displayNumber(period.estimated_stock)}</td></tr>)}</tbody></table></div>
    {row.challenge_action && <p><strong>Rótulo {row.challenge_action.label}:</strong> {row.challenge_action.evidence.filter((item) => item.value !== null).map((item) => `${item.label}: ${typeof item.value === 'number' ? displayNumber(item.value) : item.value}`).join('; ') || row.challenge_action.reason}.</p>}
    {row.orders.length > 0 && <ul className="plain-list">{row.orders.map(order => <li key={order.order}>Pedido {order.order}: {displayUnits(order.quantity)}, prometido para {order.promised_date ? formatDate(order.promised_date) : 'data ausente'} ({order.status}).</li>)}</ul>}
  </div>;
}

/** Rótulo igual em todas as linhas: aparece uma vez no cabeçalho da lista, sem repetir o selo e o "?" em cada linha. */
function sharedLabel(rows: CommercialRow[]): ChallengeAction | undefined {
  const first = rows[0]?.challenge_action;
  return rows.length > 1 && first && rows.every((row) => row.challenge_action?.code === first.code) ? first : undefined;
}

function Stats({ row }: { row: CommercialRow }) {
  return <dl className="opp-stats">
    <div><dt>Estoque (un.)</dt><dd>{displayNumber(row.estimated_stock)}</dd></div>
    <div><dt>Cobertura de estoque</dt><dd>{displayDays(row.coverage_days)}</dd></div>
    <div><dt>Vende por mês</dt><dd>{displayNumber(row.average_monthly_sell_out)}</dd></div>
  </dl>;
}

/** Cartão compacto para celular: o necessário para decidir; a evidência abre sob demanda, uma por vez. */
export function OpportunityCard({ row, uniform, hideLabel, expanded, onToggle }: { row: CommercialRow; uniform: boolean; hideLabel: boolean; expanded: boolean; onToggle: () => void }) {
  return <li className={`opp-card ${expanded ? 'is-expanded' : ''}`}>
    <div className="opp-head">
      <Link to={`/parceiros/${encodeURIComponent(row.partner)}`}>{row.partner_name}</Link>
      <span><Link to={`/skus/${encodeURIComponent(row.sku)}`}>{row.sku}</Link> <small>{row.product}</small></span>
    </div>
    {(!uniform || row.data_quality !== 'sufficient' || (!hideLabel && row.challenge_action)) && <div className="opp-flags">
      {!uniform && <strong className="commercial-action">{row.action_label}</strong>}
      {row.data_quality !== 'sufficient' && <Badge tone="medium">{qualityLabels[row.data_quality]}</Badge>}
      <BuildupBadge row={row} />
      {!hideLabel && <ChallengeBadge action={row.challenge_action} />}
    </div>}
    <Stats row={row} />
    <button type="button" className="secondary-button evidence-toggle" aria-expanded={expanded} aria-label={`Evidências de ${row.partner} · ${row.sku} — ${row.action_label}`} onClick={onToggle}>{expanded ? 'Ocultar evidências' : 'Ver evidências'}</button>
    {expanded && <Evidence row={row} />}
  </li>;
}

export function CommercialMatrix({ response }: { response: CommercialPage<CommercialRow> }) {
  const mobile = useMediaQuery(MOBILE_LIST_QUERY);
  // Uma evidência aberta por vez. `undefined` = padrão: com um único vínculo (ex.: filtro por SKU) a evidência já vem aberta.
  const [openKey, setOpenKey] = useState<string | null | undefined>(undefined);
  const single = response.items.length === 1;
  const isOpen = (key: string) => openKey === undefined ? single : openKey === key;
  const toggle = (key: string) => setOpenKey(isOpen(key) ? null : key);
  // Quando todas as linhas têm a mesma ação e dados suficientes (ex.: lista de oportunidades), a coluna não informa nada.
  const uniform = response.items.length > 1 && response.items.every(row => row.action === response.items[0].action && row.data_quality === 'sufficient');
  const shared = sharedLabel(response.items);
  const columns = uniform ? 5 : 6;
  const empty = <EmptyState title="Nenhum vínculo neste recorte" description="Ajuste os filtros. Não são criadas combinações entre todos os parceiros e todos os SKUs." />;
  // Dica do rótulo comum sem as evidências de uma linha só: elas ficam na evidência de cada linha.
  const sharedAction = shared ? <span className="revenue-card-tag"><ChallengeBadge action={{ ...shared, evidence: [] }} /></span> : undefined;
  return <>
    <SectionCard title="Matriz parceiro–SKU" action={sharedAction}>
      {!response.items.length ? empty : mobile ? <ul className="opp-list" aria-label="Oportunidades por parceiro e SKU">{response.items.map(row => <OpportunityCard key={rowKey(row)} row={row} uniform={uniform} hideLabel={!!shared} expanded={isOpen(rowKey(row))} onToggle={() => toggle(rowKey(row))} />)}</ul>
      : <div className="table-shell" tabIndex={0} role="region" aria-label="Matriz comercial por parceiro e SKU"><table className={`data-table commercial-table responsive-table ${uniform ? '' : 'has-action'}`}><thead><tr><th>Parceiro / SKU</th>{!uniform && <th>Ação comercial</th>}<th className="num">Estoque estimado (un.)</th><th className="num">Cobertura de estoque (dias)</th><th className="num">Vende por mês (un.) <Hint term="sellout" /></th><th className="cell-action"><span className="sr-only">Evidências</span></th></tr></thead><tbody>{response.items.map(row => {
        const key = rowKey(row);
        const expanded = isOpen(key);
        return [
          <tr key={key} className={expanded ? 'is-expanded' : ''}>
            <td data-label="Parceiro / SKU"><Link to={`/parceiros/${encodeURIComponent(row.partner)}`}>{row.partner_name}</Link><br /><Link to={`/skus/${encodeURIComponent(row.sku)}`}>{row.sku}</Link><small>{row.product}</small>{!shared && <ChallengeBadge action={row.challenge_action} />}</td>
            {!uniform && <td className="cell-stack" data-label="Ação comercial"><strong className="commercial-action">{row.action_label}</strong>{row.data_quality !== 'sufficient' && <Badge tone="medium">{qualityLabels[row.data_quality]}</Badge>}<BuildupBadge row={row} /></td>}
            <td className="num" data-label="Estoque estimado">{displayNumber(row.estimated_stock)}</td>
            <td className="num" data-label="Cobertura de estoque">{displayDays(row.coverage_days)}</td>
            <td className="num" data-label="Vende por mês">{displayNumber(row.average_monthly_sell_out)}</td>
            <td className="cell-action"><button type="button" className="secondary-button evidence-toggle" aria-expanded={expanded} aria-label={`Evidências de ${row.partner} · ${row.sku} — ${row.action_label}`} onClick={() => toggle(key)}>{expanded ? 'Ocultar evidências' : 'Ver evidências'}</button></td>
          </tr>,
          expanded && <tr key={`${key}-evidence`} className="evidence-row"><td colSpan={columns}><Evidence row={row} /></td></tr>,
        ];
      })}</tbody></table></div>}
    </SectionCard>
  </>;
}

/** Método, natureza dos campos e limites configurados: material de auditoria (página Auditoria). */
export function CommercialMethod({ response }: { response: Pick<CommercialPage<unknown>, 'limitation' | 'field_nature' | 'thresholds'> }) {
  return <div>
    <p>{response.limitation}</p>
    <ul>{Object.entries(response.field_nature).map(([name, info]) => <li key={name}><strong>{name.split('_').join(' ')}</strong>: {info.nature}. Origem: {info.origin}.</li>)}</ul>
    <dl className="commercial-thresholds">{Object.entries(response.thresholds).map(([key, value]) => <div key={key}><dt>{thresholdNames[key] ?? key}</dt><dd>{displayNumber(value)}</dd></div>)}</dl>
    <p>Limites demonstrativos, não validados como política comercial pela empresa. Nenhuma recomendação libera reposição ou produção automaticamente.</p>
  </div>;
}
