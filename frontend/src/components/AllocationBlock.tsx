import { Tooltip } from '../components';
import { displayCurrency, displayNumber, displayQuantity, formatDate } from '../pages/shared';
import type { AllocationOrder, AllocationSku } from '../types-allocation';

const COMPONENT_NAMES: Record<string, string> = {
  urgencia: 'urgência', canal_direto: 'canal direto', cobertura_baixa_parceiro: 'cobertura baixa no parceiro',
  estoque_acumulando_parceiro: 'estoque acumulando no parceiro', sem_sell_out: 'sem sell-out', pedido_pequeno: 'pedido pequeno',
};

function delayText(order: AllocationOrder) {
  if (order.expected_date === null) return 'sem cobertura';
  if (order.delay_days === null || order.delay_days <= 0) return 'no prazo';
  return `${displayQuantity(order.delay_days)} ${order.delay_days === 1 ? 'dia' : 'dias'}`;
}

function laterText(order: AllocationOrder) {
  if (order.uncovered_at_promise <= 0) return '—';
  return `${displayQuantity(order.uncovered_at_promise)} ${order.expected_date ? `em ${formatDate(order.expected_date)}` : 'sem data'}`;
}

/** O "porquê" da posição: pedido, região, motivo, componentes da pontuação com a natureza e a comparação com a regra atual. */
function orderWhy(order: AllocationOrder) {
  const parts = order.score_components.map((item) => `${COMPONENT_NAMES[item.component] ?? item.component} ${displayNumber(item.points)} (${item.nature}: ${item.reason})`);
  const sources = order.allocated_later.map((item) => `${displayQuantity(item.quantity)} un. em ${formatDate(item.expected_date)}${item.source_ref ? ` (${item.source_ref})` : ''}`);
  const fifo = order.fifo_delay_days === null ? 'Pela regra atual (data prometida), não cobre no horizonte.' : `Pela regra atual (data prometida), atraso de ${displayQuantity(order.fifo_delay_days)} dias.`;
  return `${order.order} · ${order.region} · ${displayQuantity(order.quantity)} un. para ${formatDate(order.promised_date)}. ${order.reason} Pontuação ${displayNumber(order.allocation_score)}: ${parts.join('; ') || 'sem componentes'}.${sources.length ? ` Depois: ${sources.join('; ')}.` : ''} ${fifo}`;
}

/**
 * Etapa 16.2: "Quem atender primeiro". Uma linha por pedido confirmado sem cobertura, na ordem sugerida; os componentes da
 * pontuação ficam no "?". A alocação é sugestão: não reserva estoque nem altera pedidos. Sem alocação, não renderiza nada.
 */
export function AllocationBlock({ allocation }: { allocation?: AllocationSku | null }) {
  if (!allocation || allocation.orders.length === 0) return null;
  const orders = [...allocation.orders].sort((a, b) => a.rank - b.rank);
  const value = allocation.uncovered_value_at_promise === null ? (allocation.missing_price_reason ?? 'valor não calculado: sem preço') : displayCurrency(allocation.uncovered_value_at_promise);
  return <details className="detail-block" open>
    <summary>Quem atender primeiro</summary>
    <p className="fact-line"><strong>{allocation.decision_text}</strong></p>
    <div className="table-shell" tabIndex={0} role="region" aria-label="Ordem de atendimento dos pedidos"><table className="data-table">
      <thead><tr><th>Ordem</th><th>Cliente</th><th>Agora</th><th>Restante</th><th>Atraso</th></tr></thead>
      <tbody>{orders.map((order) => <tr key={`${order.order}-${order.rank}`}>
        <td>{order.rank}º</td>
        <td>{order.client}<Tooltip label={`Por que o pedido ${order.order} está nesta posição`}>{orderWhy(order)}</Tooltip></td>
        <td>{displayQuantity(order.allocated_now)} de {displayQuantity(order.quantity)}</td>
        <td>{laterText(order)}</td>
        <td>{delayText(order)}</td>
      </tr>)}</tbody>
    </table></div>
    <p className="fact-line">Descoberto na data prometida: {displayQuantity(allocation.uncovered_units_at_promise)} un. · {value}.{allocation.orders_without_date.length > 0 && ` Sem data prometida: ${allocation.orders_without_date.join(', ')}.`}
      <Tooltip label="Sobre os dados da alocação">{allocation.data_note} Distribui estoque do CD, OPs e ordens planejadas só entre pedidos confirmados; a previsão não entra.</Tooltip></p>
    <p className="fact-line">Sugestão para revisão humana: não reserva estoque nem altera pedidos.</p>
  </details>;
}
