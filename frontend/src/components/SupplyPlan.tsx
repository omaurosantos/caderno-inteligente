import { Link } from 'react-router-dom';
import type { OperationalRecommendation } from '../types';
import { displayQuantity, formatDate } from '../pages/shared';
import { Badge } from '../components';

const WEEKS_VISIBLE = 8;
const ADJUSTMENT: Record<string, string> = { antecipar: 'Antecipar', reduzir: 'Reduzir', cancelar: 'Cancelar' };
const CAPACITY: Record<string, { text: string; tone: string }> = {
  ok: { text: 'cabe', tone: 'good' }, pre_producao: { text: 'pré-produção', tone: 'info' },
  a_confirmar: { text: 'a confirmar', tone: 'neutral' }, insuficiente: { text: 'não cabe', tone: 'critical' },
};

type Week = NonNullable<OperationalRecommendation['projection']>[number];

function WeekRows({ weeks }: { weeks: Week[] }) {
  // A marca de falta segue a mesma projeção exibida (com as ordens planejadas); `shortfall` é a projeção sem elas.
  return <>{weeks.map((week) => <tr key={week.week_start} className={week.shortfall_with_plan ? 'is-urgent' : ''}>
    <td>{formatDate(week.week_start)}</td>
    <td>{displayQuantity(week.carteira + week.forecast_demand)}</td>
    <td>{displayQuantity(week.op_receipts + week.planned_receipts)}</td>
    <td>{displayQuantity(week.projected_end_with_plan)}{week.shortfall_with_plan && <small> · falta</small>}</td>
  </tr>)}</>;
}

/**
 * Etapa 15.3–15.5: o plano datado do SKU — cascata, ordens planejadas, ajustes de OP, pedidos afetados e projeção.
 * Etapa 16.2: com alocação (`allocated`), os pedidos afetados ficam em "Quem atender primeiro"; a lista pela data prometida sairia com outras datas.
 */
export function SupplyPlanBlock({ recommendation, allocated = false }: { recommendation: OperationalRecommendation; allocated?: boolean }) {
  const { planned_orders: orders = [], op_adjustments: adjustments = [], affected_orders: late = [], projection = [], calculation: calc } = recommendation;
  const capacityOrders = recommendation.capacity?.orders ?? [];
  const firstWeeks = projection.slice(0, WEEKS_VISIBLE);
  const header = <thead><tr><th>Semana</th><th>Demanda</th><th>Entradas</th><th>Estoque projetado</th></tr></thead>;
  return <details className="detail-block" open>
    <summary>Plano de suprimento</summary>
    <p className="fact-line">Até {formatDate(String(calc.cover_end ?? ''))}: demanda {displayQuantity(calc.demand_to_cover)} + segurança {displayQuantity(calc.safety_stock_quantity)} − estoque {displayQuantity(calc.current_stock)} − OPs no prazo {displayQuantity(calc.open_production_quantity)} = <strong>{displayQuantity(calc.raw_quantity)} un.</strong> Reposição nova chega a partir de {formatDate(recommendation.earliest_arrival)}.</p>
    {late.length > 0 && allocated && <p className="fact-line">Pedidos afetados e ordem de atendimento: veja "Quem atender primeiro" no Resumo.</p>}
    {late.length > 0 && !allocated && <ul className="plain-list">{late.map((order) => <li key={order.order}><strong>{order.order}</strong> ({order.client}): {displayQuantity(order.quantity)} un. para {formatDate(order.promised_date)}, {order.expected_date ? `atende em ${formatDate(order.expected_date)}` : 'sem cobertura no horizonte'}.</li>)}</ul>}
    {adjustments.length > 0 && <ul className="plain-list">{adjustments.map((item) => <li key={`${item.order}-${item.adjustment}`}><Badge tone={item.adjustment === 'antecipar' ? 'critical' : 'medium'}>{ADJUSTMENT[item.adjustment]} {item.order}</Badge> {item.adjustment === 'antecipar' ? `para ${formatDate(item.suggested_finish)}` : `de ${displayQuantity(item.quantity)} para ${displayQuantity(item.suggested_quantity)} un.`}</li>)}</ul>}
    {orders.length > 0 && <div className="table-shell" tabIndex={0} role="region" aria-label="Ordens planejadas"><table className="data-table">
      <thead><tr><th>Liberar até</th><th>Chegada</th><th>Quantidade</th><th>Capacidade</th></tr></thead>
      <tbody>{orders.map((order, index) => {
        const capacity = CAPACITY[capacityOrders[index]?.status ?? ''];
        return <tr key={`${order.due_date}-${index}`}><td>{formatDate(order.release_date)}{order.urgent && <small> · agora</small>}</td><td>{formatDate(order.due_date)}</td><td>{displayQuantity(order.quantity)}</td>
          <td>{capacity ? <Badge tone={capacity.tone}>{capacity.text}</Badge> : '—'}</td></tr>;
      })}</tbody>
    </table></div>}
    {projection.length > 0 && <div className="table-shell" tabIndex={0} role="region" aria-label="Projeção semanal de estoque"><table className="data-table">{header}<tbody><WeekRows weeks={firstWeeks} /></tbody></table></div>}
    {projection.length > WEEKS_VISIBLE && <details className="validation-details"><summary>Ver as demais {projection.length - WEEKS_VISIBLE} semanas</summary>
      <div className="table-shell" tabIndex={0} role="region" aria-label="Projeção semanal completa"><table className="data-table">{header}<tbody><WeekRows weeks={projection.slice(WEEKS_VISIBLE)} /></tbody></table></div>
    </details>}
    {recommendation.capacity?.status === 'insuficiente' && <p className="fact-line">Há ordem que não cabe na linha: veja <Link to="/capacidade">Capacidade</Link>.</p>}
  </details>;
}
