import { EmptyState, mainReason } from '../components';
import { ChallengeBadge } from './ChallengeAction';
import { EventBadge, mainAlert } from './EventAlerts';
import { displayCurrency, displayQuantity, formatDate, reasonNames } from '../pages/shared';
import type { ForecastRecommendationSummary, Priority } from '../types';
import type { EventItem } from '../types-events';

type Recommendation = ForecastRecommendationSummary['operational_recommendation'];

/** Uma linha da fila: o que cada fonte sabe do SKU. Campo ausente nunca vira zero nem recomendação inventada. */
export interface QueueRow {
  sku: string;
  product: string;
  family: string;
  position: number | null;
  priority?: Priority;
  forecast?: ForecastRecommendationSummary;
}

export type QueueSort = 'priority' | 'suggested_quantity' | 'forecast_next_month' | 'backtest_wape';

/** Junção pelo SKU. A prioridade vem de /priorities; ação e quantidade vêm de /forecasts; SKU em só uma fonte permanece na lista. */
export function joinQueue(priorities: Priority[] | undefined, forecasts: ForecastRecommendationSummary[] | undefined): QueueRow[] {
  const rows = new Map<string, QueueRow>();
  for (const priority of priorities ?? []) rows.set(priority.sku, { sku: priority.sku, product: priority.product, family: priority.family, position: priority.priority, priority });
  for (const forecast of forecasts ?? []) {
    const known = rows.get(forecast.sku);
    rows.set(forecast.sku, known
      ? { ...known, forecast, position: known.position ?? forecast.priority }
      : { sku: forecast.sku, product: forecast.product, family: forecast.family, position: forecast.priority, forecast });
  }
  return [...rows.values()];
}

export const forecastNeedsAttention = (item: ForecastRecommendationSummary) => item.forecast.status === 'insufficient_data'
  || item.operational_recommendation.action !== 'sem_acao_necessaria'
  || item.operational_recommendation.capacity_status === 'requires_review';

/** SKU só no ranking (sem previsão carregada) não pode ser dado como "sem atenção". */
export const rowNeedsAttention = (row: QueueRow) => !row.forecast || forecastNeedsAttention(row.forecast);

const NO_POSITION = Number.MAX_SAFE_INTEGER;

export function sortQueue(rows: QueueRow[], sort: QueueSort) {
  return [...rows].sort((left, right) => {
    if (sort === 'priority') return (left.position ?? NO_POSITION) - (right.position ?? NO_POSITION) || left.sku.localeCompare(right.sku);
    const pick = (row: QueueRow) => sort === 'suggested_quantity' ? row.forecast?.operational_recommendation.suggested_quantity ?? null : row.forecast?.forecast[sort] ?? null;
    const leftValue = pick(left);
    const rightValue = pick(right);
    if (leftValue === null && rightValue === null) return left.sku.localeCompare(right.sku);
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    return rightValue - leftValue || left.sku.localeCompare(right.sku);
  });
}

type Urgency = 'urgent' | 'review' | 'none' | 'missing';

/** Margem da linha: urgente só quando o sinal principal é crítico; revisar quando ele é alto, há exceção ou a ação pede validação; tracejada quando não há previsão. */
function urgencyOf(row: QueueRow, severity: string | undefined, exceptions: number): Urgency {
  if (!row.forecast) return 'missing';
  const planned = row.forecast.operational_recommendation.action;
  if (severity === 'crítica' || planned === 'atraso_inevitavel' || planned === 'antecipar_op') return 'urgent';
  if (planned === 'rever_op') return 'review';
  if (severity === 'alta') return 'review';
  const action = row.forecast.operational_recommendation.action;
  if (exceptions > 0 || action === 'investigar_dados' || action === 'produzir_validar_capacidade') return 'review';
  return 'none';
}

function exceptionTexts(row: QueueRow) {
  const rec = row.forecast?.operational_recommendation;
  const forecastConfidence = row.forecast?.forecast.forecast_confidence;
  const dataConfidence = row.priority?.confidence ?? row.forecast?.confidence;
  return [
    row.forecast?.forecast.status === 'insufficient_data' && 'Dados insuficientes',
    rec?.capacity_status === 'requires_review' && 'Validar capacidade',
    forecastConfidence && forecastConfidence !== 'alta' && row.forecast?.forecast.status === 'ok' && `Previsão com confiança ${forecastConfidence}`,
    dataConfidence === 'baixa' && 'Dados com confiança baixa',
  ].filter((item): item is string => !!item);
}

/** Etapa 15.3: com falta datada, o motivo principal diz quando ela começa (vem da projeção, não da regra de cobertura). */
function shortfallReason(rec: ForecastRecommendationSummary['operational_recommendation'] | undefined) {
  if (!rec || !rec.first_shortfall_date || !['atraso_inevitavel', 'antecipar_op'].includes(rec.action)) return undefined;
  return `Falta a partir de ${formatDate(rec.first_shortfall_date)}`;
}

/** "Atender KA-02 antes de KA-05": a primeira frase do rótulo quando o SKU é disputado e a alavanca é alocar. */
export function allocationHeadline(action: ForecastRecommendationSummary['challenge_action'] | undefined) {
  if (!action || action.lever !== 'alocar') return undefined;
  return /^Atender\s.+?\santes de\s[^.]+\./.exec(action.reason)?.[0];
}

/** Motivo principal: faixa e valor em risco (priority_reason). Sem ele (resposta antiga), vale a falta datada ou o sinal mais pesado. */
function queueReason(row: QueueRow, rec: Recommendation | undefined, signal: { code: string; description: string } | undefined) {
  return row.priority?.priority_reason || shortfallReason(rec) || (signal ? (reasonNames[signal.code] ?? signal.description) : undefined);
}

/** Detalhe do cálculo: pontuação de sinais, valor observado × estimado e a curva ABC medida × a do cadastro. */
export function reasonDetail(row: QueueRow) {
  const risk = row.priority?.value_at_risk ?? row.forecast?.value_at_risk;
  const measured = row.priority?.abc_measured ?? row.forecast?.abc_measured;
  const registry = row.priority?.abc_registry ?? row.forecast?.abc_registry;
  const score = row.priority?.attention_score ?? row.forecast?.attention_score;
  const parts = [
    risk && `Valor em risco: ${displayCurrency(risk.observed)} observado em pedidos e ${displayCurrency(risk.estimated)} estimado pela previsão.`,
    measured ? `Curva ABC medida pelo faturamento dos últimos 12 meses: ${measured}${registry && registry !== measured ? `; no cadastro está ${registry}` : registry ? ' (igual ao cadastro)' : ''}.` : registry ? `Curva ABC do cadastro: ${registry}; a medida não está disponível.` : undefined,
    typeof score === 'number' && `Pontuação dos sinais: ${score} (desempate dentro da faixa).`,
  ].filter((item): item is string => !!item);
  return parts.join(' ');
}

/** Faixa em destaque e valor em risco ao lado: "Pedido confirmado sem cobertura · R$ 63,9 mil em risco (KA-05, KA-02)". */
function ReasonText({ text }: { text: string }) {
  const [head, ...rest] = text.split(' · ');
  return rest.length ? <><strong>{head}</strong> <span>{rest.join(' · ')}</span></> : <>{text}</>;
}

export function OperationalQueueTable({ rows, onSelect, weights, eventsBySku, forecastsLoaded, prioritiesLoaded }: {
  rows: QueueRow[];
  onSelect: (row: QueueRow) => void;
  weights?: Record<string, number>;
  eventsBySku: Map<string, EventItem>;
  forecastsLoaded: boolean;
  prioritiesLoaded: boolean;
}) {
  if (!rows.length) return <EmptyState title="Nenhum SKU encontrado" description="Ajuste os filtros ou volte à visão completa." />;
  return <div className="table-shell queue-table" tabIndex={0} role="region" aria-label="Fila operacional; role horizontalmente para ver todas as colunas">
    <table className="data-table responsive-table">
      <caption className="sr-only">Fila operacional por posição de atenção; cada sugestão exige revisão humana</caption>
      <thead><tr><th>Posição e SKU</th><th>Ação sugerida</th><th>Quantidade sugerida (un.)</th><th>Motivo principal</th><th>Exceções</th></tr></thead>
      <tbody>{rows.map((row) => {
        const rec = row.forecast?.operational_recommendation;
        const reason = row.priority ? mainReason(row.priority.reasons, weights) : undefined;
        const event = eventsBySku.get(row.sku);
        const hasEvent = !!(event && mainAlert(event.alerts));
        const texts = exceptionTexts(row);
        const detail = reasonDetail(row);
        const allocation = allocationHeadline(row.forecast?.challenge_action);
        const text = queueReason(row, rec, reason);
        const urgency = urgencyOf(row, reason?.severity, texts.length + (hasEvent ? 1 : 0));
        const textTone = !rec || rec.action === 'sem_acao_necessaria' ? 'is-muted-text' : urgency === 'urgent' ? 'is-urgent-text' : urgency === 'review' ? 'is-review-text' : '';
        return <tr key={row.sku} className={`is-${urgency}`}>
          <td className="queue-sku" data-label="SKU">
            <span className={`rank ${row.position !== null && row.position <= 3 ? 'top' : ''}`} title={`Posição na fila de atenção. ${detail}`.trim()}>{row.position ?? '–'}</span>
            <div><button type="button" className="link-button" onClick={() => onSelect(row)} aria-label={`Ver detalhes de ${row.sku}`}><strong>{row.sku}</strong></button><small>{row.product}</small></div>
          </td>
          <td className="queue-action" data-label="Ação sugerida">
            {rec ? <span className={textTone}>{rec.action_label}</span> : <span className="is-muted-text">{forecastsLoaded ? 'Sem previsão para este SKU' : 'Ação indisponível'}</span>}
            {row.forecast?.challenge_action?.code === 'priorizar_producao' && <> <ChallengeBadge action={row.forecast.challenge_action} /></>}
          </td>
          <td className="queue-qty" data-label="Quantidade" title={rec?.planned_quantity_horizon ? `${displayQuantity(rec.planned_quantity_horizon)} un. planejadas no horizonte` : undefined}><strong>{typeof rec?.suggested_quantity === 'number' ? displayQuantity(rec.suggested_quantity) : <><span className="sr-only">Não disponível</span><span aria-hidden="true">–</span></>}</strong></td>
          <td className="queue-reason" data-label="Motivo principal">
            {text ? (row.priority?.priority_reason ? <ReasonText text={text} /> : text) : <span className="queue-none">{prioritiesLoaded ? 'Fora do ranking' : 'Indisponível'}</span>}
            {allocation && <strong className="queue-allocation"> {allocation}</strong>}
            {detail && <span className="sr-only"> {detail}</span>}
          </td>
          <td className={`queue-exceptions ${texts.length || hasEvent ? '' : 'is-empty'}`} data-label="Exceções">
            {texts.length || hasEvent ? <>{texts.join(', ')}{texts.length > 0 && hasEvent && ' · '}{hasEvent && event && <EventBadge item={event} />}</> : <span className="sr-only">Sem exceções</span>}
          </td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}
