import { Link } from 'react-router-dom';
import { api } from '../api';
import { Badge, LoadingState, PageIntro, SectionCard, Tooltip } from '../components';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import type { CapacityFamily, CapacityFamilyStatus } from '../types';
import { displayQuantity, formatDate } from './shared';

// Estimado = além do calendário da base: hachurado, para nunca parecer fato observado.
const STATUS_TONE: Record<CapacityFamilyStatus, string> = { ok: 'good', pre_producao: 'info', a_confirmar: 'neutral', insuficiente: 'critical', ok_estimado: 'good-estimated', insuficiente_estimado: 'critical-estimated' };
const STATUS_TEXT: Record<CapacityFamilyStatus, string> = { ok: 'Cabe', pre_producao: 'Cabe com pré-produção', a_confirmar: 'Cabe no calendário; depois, a confirmar', insuficiente: 'Não cabe', ok_estimado: 'Cabe (estimado)', insuficiente_estimado: 'Não cabe (estimado)' };
const ESTIMATED_NOTE = 'Estimado: além do calendário da base.';
/** O número de semanas vem da API (`extension.lookback_weeks`); sem ele, o texto não cita número. */
const lookbackText = (weeks: number | null | undefined) => weeks ? `das últimas ${weeks} semanas` : 'das últimas semanas';
const methodText = (method: string | null | undefined, weeks: number | null | undefined) => method === 'media_compromissos_8_semanas' ? `Capacidade máxima menos a média dos compromissos ${lookbackText(weeks)}.` : method ?? '';
const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const isShort = (status: CapacityFamilyStatus | null | undefined) => status === 'insuficiente' || status === 'insuficiente_estimado';
const isEstimated = (status: CapacityFamilyStatus | null | undefined) => status === 'ok_estimado' || status === 'insuficiente_estimado';

const statusBadge = (status: CapacityFamilyStatus) => <Badge tone={STATUS_TONE[status]} title={isEstimated(status) ? ESTIMATED_NOTE : undefined}>{STATUS_TEXT[status]}</Badge>;

function shortfallLine(family: CapacityFamily) {
  const orders = family.affected_orders.slice(0, 3).map((order) => `${order.order} (${order.client})`).join(', ');
  return <p key={family.family} className="fact-line"><strong>{family.family}:</strong> {displayQuantity(family.unscheduled_quantity)} un. sem programação{isEstimated(family.status) ? ' (estimado)' : ''}, a primeira para {formatDate(family.first_shortfall_due)}; SKUs {family.skus_short.join(', ')}{orders && `; pedidos em carteira desses SKUs: ${orders}${family.affected_orders.length > 3 ? '…' : ''}`}.</p>;
}

/** Um cenário no pico: situação e, se faltar, quantas unidades ficam sem programação. */
function scenarioCell(status: CapacityFamilyStatus | null | undefined, unscheduled: number | undefined) {
  if (!status) return <span className="validation-muted">—</span>;
  return <>{statusBadge(status)}{isShort(status) && typeof unscheduled === 'number' && unscheduled > 0 ? <> <strong>{displayQuantity(unscheduled)}</strong></> : null}</>;
}

/** Etapa 15.4: onde a produção planejada não cabe na capacidade livre de cada linha, semana a semana. */
export default function CapacityPage({ refreshToken }: { refreshToken: number }) {
  const { data, error, loading, loadedAt } = useApiResource(api.capacityPlan, refreshToken);
  usePageLoadStatus(loading, data ? '' : error, loadedAt);
  if (!data && loading) return <LoadingState />;
  if (!data) return <p className="fact-line">Plano de capacidade indisponível no momento.</p>;
  const short = data.families.filter((family) => isShort(family.status));
  const calendarEnd = data.families[0]?.calendar_end;
  const lookbackWeeks = data.extension?.lookback_weeks;
  const peakMonths = (data.families[0]?.peak_months ?? []).map((month) => MONTHS[month - 1]).join(', ');
  const peakFamilies = data.families.filter((family) => family.peak_status || family.scenarios);
  const hasEstimated = data.families.some((family) => family.weeks.some((week) => week.nature === 'estimada'));

  return <div className="revenue-page">
    <PageIntro title="Onde a produção planejada não cabe" description={`Ordens planejadas encaixadas na capacidade livre de cada linha até ${formatDate(calendarEnd)}. Simulação: nada é reservado.`} />
    <SectionCard title="Por linha" action={<Tooltip label="Premissas do encaixe">{data.assumptions.join(' ')}</Tooltip>}>
      <div className="table-shell" tabIndex={0} role="region" aria-label="Capacidade por linha"><table className="data-table">
        <thead><tr><th>Família</th><th>Livre no calendário</th><th>Encaixado</th><th>Sem programação</th><th>Situação</th></tr></thead>
        <tbody>{data.families.map((family) => <tr key={family.family}>
          <td><strong>{family.family}</strong></td>
          <td>{displayQuantity(family.available_until_calendar_end)}</td>
          <td>{displayQuantity(family.planned_in_calendar)}</td>
          <td>{displayQuantity(family.unscheduled_quantity)}</td>
          <td>{statusBadge(family.status)}</td>
        </tr>)}</tbody>
      </table></div>
      {short.length ? short.map(shortfallLine) : <p className="fact-line">Todas as ordens planejadas cabem até o fim do calendário.</p>}
      {peakFamilies.length > 0 && <div className="table-shell" tabIndex={0} role="region" aria-label="Cenários no pico"><table className="data-table scenario-table">
        <caption>Cenários no pico ({peakMonths}); unidades sem programação ao lado da situação <Tooltip label="O que são os cenários">Central: capacidade máxima menos a média dos compromissos {lookbackWeeks ? `de ${lookbackWeeks} semanas` : 'recentes'}. Conservador: a menor disponibilidade observada. Cenário estimado vale além do calendário da base.</Tooltip></caption>
        <thead><tr><th>Família</th><th>Central</th><th>Conservador</th></tr></thead>
        <tbody>{peakFamilies.map((family) => <tr key={family.family}>
          <td><strong>{family.family}</strong></td>
          <td>{scenarioCell(family.scenarios?.central.peak_status ?? family.peak_status, family.scenarios?.central.unscheduled_quantity)}</td>
          <td>{scenarioCell(family.scenarios?.conservador.peak_status, family.scenarios?.conservador.unscheduled_quantity)}</td>
        </tr>)}</tbody>
      </table></div>}
      <p className="fact-line">{hasEstimated && <><span className="estimated-swatch" aria-hidden="true" /><strong>Hachurado = estimado:</strong> além do calendário da base. </>}Ordens que começariam depois do calendário ficam a confirmar.</p>
    </SectionCard>
    {data.families.map((family) => <details key={family.family} className="validation-details"><summary>Semanas da {family.line || family.family}</summary>
      <div className="table-shell" tabIndex={0} role="region" aria-label={`Semanas da ${family.line || family.family}`}><table className="data-table">
        <thead><tr><th>Semana</th><th>Livre</th><th>Encaixado</th><th>Sobra</th><th>Natureza</th></tr></thead>
        <tbody>{family.weeks.map((week) => {
          const estimated = week.nature === 'estimada';
          return <tr key={week.week_start} className={estimated ? 'week-estimated' : undefined}><td>{formatDate(week.week_start)}</td><td>{displayQuantity(week.available)}</td><td>{displayQuantity(week.allocated)}</td><td>{displayQuantity(week.remaining)}</td>
            <td>{week.nature ? <Badge tone={estimated ? 'medium' : 'neutral'} title={estimated ? `${ESTIMATED_NOTE} ${methodText(week.method, lookbackWeeks)}`.trim() : undefined}>{estimated ? 'estimada' : 'observada'}</Badge> : <span className="validation-muted">—</span>}</td></tr>;
        })}</tbody>
      </table></div>
    </details>)}
    <p className="fact-line"><Link to="/fila">Voltar à fila</Link> para ver a ação de cada SKU.</p>
  </div>;
}
