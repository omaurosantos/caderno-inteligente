import type { ReactNode } from 'react';
import { Badge, Hint, Tooltip } from '../components';
import { displayCurrency, displayUnits, formatDate, formatMonth } from '../pages/shared';
import type { EventAlert, EventEvidence, EventItem, EventScenario, SkuEventScenario } from '../types-events';

const ptFactor = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const SEM_FATOR: Record<string, string> = { sem_historico_direto: 'Sem histórico direto', sem_evidencia: 'Sem evidência', queda: 'Queda histórica', sem_alteracao: 'Sem variação', aumento: 'Aumento histórico' };

export const factorText = (factor: number | null) => factor === null ? 'Sem fator' : `×${ptFactor.format(factor)}`;
const period = (start: string, end: string) => `${formatDate(start)} a ${formatDate(end)}`;

export function evidenceText(evidence: EventEvidence) {
  if (evidence.factor === null) return SEM_FATOR[evidence.evidence_status] ?? 'Sem evidência';
  return `${factorText(evidence.factor)} · ${evidence.occurrences} ${evidence.occurrences === 1 ? 'ocorrência' : 'ocorrências'}${evidence.capped ? ' (limitado)' : ''}`;
}

/** O alerta mais urgente de um SKU: o que está no horizonte e começa primeiro; senão, o que começa primeiro. */
export function mainAlert(alerts: EventAlert[]): EventAlert | undefined {
  return [...alerts].sort((a, b) => Number(b.in_horizon) - Number(a.in_horizon) || a.days_to_start - b.days_to_start)[0];
}

/** Selo curto para listas; o detalhe vive no SKU. */
export function EventBadge({ item }: { item: EventItem | undefined }) {
  const main = item ? mainAlert(item.alerts) : undefined;
  if (!item || !main) return null;
  const extra = item.alerts.length - 1;
  return <Badge tone="info" title={item.alerts.map((alert) => `${alert.event}: ${period(alert.start, alert.end)}`).join('; ')}>Evento: {main.event}{extra > 0 ? ` +${extra}` : ''}</Badge>;
}

/** Uma linha com o evento mais urgente do SKU; o quadro completo fica nas evidências. */
export function UrgentEventLine({ alerts, onOpen }: { alerts: EventAlert[] | null | undefined; onOpen: () => void }) {
  const main = alerts ? mainAlert(alerts) : undefined;
  if (!main) return null;
  return <p className="fact-line"><strong>Evento mais urgente:</strong> {main.event}, {period(main.start, main.end)}{main.decision_date ? `; decidir até ${formatDate(main.decision_date)}` : ''}. <button type="button" className="link-button" onClick={onOpen}>Ver eventos e cenário</button></p>;
}

function ScenarioTable({ scenario }: { scenario: EventScenario }) {
  return <div className="table-shell" tabIndex={0} role="region" aria-label="Cenário com evento"><table className="data-table"><caption>{scenario.formula}</caption><thead><tr><th>Mês</th><th>Previsão base</th><th>Fator</th><th>Cenário com evento</th></tr></thead><tbody>{scenario.months.map((month, index) => <tr key={month}>
    <td>{formatMonth(month)}{scenario.events[index] && <small>{scenario.events[index]}</small>}</td>
    <td>{displayUnits(scenario.base_units[index])}</td>
    <td>{scenario.factors[index] === null ? '—' : factorText(scenario.factors[index])}</td>
    <td>{displayUnits(scenario.scenario_units[index])}</td>
  </tr>)}</tbody></table></div>;
}

/**
 * Eventos e sazonalidade do SKU. `embedded` mostra o conteúdo dentro de outro bloco (a previsão), sem criar um bloco novo.
 * `undefined` = resposta antiga sem o campo; `null` = análise indisponível.
 */
export function SkuEventsBlock({ alerts, scenario, embedded = false }: { alerts: EventAlert[] | null | undefined; scenario: SkuEventScenario | null | undefined; embedded?: boolean }) {
  if (alerts === undefined) return null;
  const plan = scenario?.scenario ?? null;
  const wrap = (children: ReactNode) => embedded ? <div className="event-section"><h4>Eventos e sazonalidade</h4>{children}</div> : <details className="detail-block" open><summary>Eventos e sazonalidade</summary>{children}</details>;
  if (alerts === null) return wrap(<p className="fact-line">Análise de eventos indisponível no momento. A previsão e a ação seguem válidas.</p>);
  if (!alerts.length && !plan) return null;
  return wrap(<>
    {alerts.length > 0 && <div className="table-shell" tabIndex={0} role="region" aria-label="Eventos que afetam este SKU"><table className="data-table responsive-table"><caption className="sr-only">Eventos do calendário que afetam a família do SKU; decidir até = início do evento menos o prazo de produção</caption><thead><tr><th>Evento</th><th>Período</th><th>Decidir até</th><th>Evidência histórica</th></tr></thead><tbody>{alerts.map((alert) => <tr key={alert.event_id}>
      <td data-label="Evento"><strong>{alert.event}</strong>{alert.impact && <small>Impacto {alert.impact.toLocaleLowerCase('pt-BR')}</small>}</td>
      <td data-label="Período">{period(alert.start, alert.end)}</td>
      <td data-label="Decidir até">{alert.decision_date ? formatDate(alert.decision_date) : 'Não disponível'}</td>
      <td data-label="Evidência">{evidenceText(alert.evidence)}{alert.evidence.note && <Tooltip label={`Sobre a evidência de ${alert.event}`}>{alert.evidence.note}</Tooltip>}</td>
    </tr>)}</tbody></table></div>}
    {plan ? <>
      <p className="fact-line"><strong>Cenário com evento</strong> <Badge tone="info">Estimativa</Badge><Hint term="cenario_evento" /> · não substitui a previsão base</p>
      <ScenarioTable scenario={plan} />
      {plan.quantity && <p className="fact-line">Quantidade oficial sugerida <strong>{displayUnits(plan.quantity.official)}</strong>{plan.quantity.differs ? <>; com o cenário, {displayUnits(plan.quantity.with_event)}</> : ', sem mudança no cenário'}. A quantidade oficial não é alterada.</p>}
      {plan.scenario_revenue_total_3m !== null && <p className="fact-line">Faturamento no cenário {displayCurrency(plan.scenario_revenue_total_3m)} contra {displayCurrency(plan.base_revenue_total_3m)} da base <Badge tone="info">Estimativa</Badge></p>}
    </> : scenario?.note && <p className="fact-line">{scenario.note}</p>}
  </>);
}
