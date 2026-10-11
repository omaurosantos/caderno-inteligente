import { Link } from 'react-router-dom';
import { SectionCard, Tooltip } from '../components';
import { formatDate } from '../pages/shared';
import type { DecisionsToday as DecisionsTodayData } from '../types-actions';
import { LEVER_LABELS } from './ChallengeAction';

/** Nome curto da alavanca: o mesmo mapa do selo da ação, para os nomes não divergirem. */
export const LEVER_NAMES = LEVER_LABELS;

/** Quantas decisões o Início mostra; o resto fica na fila (orçamento de volume da rota). */
const SHOWN = 5;

/**
 * Etapa 16.4: "Decisões de hoje". Cada linha diz o que decidir, até quando e em qual SKU; o motivo fica no "?".
 * Sugestão para revisão humana: nada aqui reserva estoque ou altera pedido. Sem dado (`null`), o bloco não aparece.
 */
export function DecisionsToday({ data }: { data?: DecisionsTodayData | null }) {
  if (!data) return null;
  const items = [...data.items].sort((a, b) => a.decide_by.localeCompare(b.decide_by)).slice(0, SHOWN);
  return <SectionCard className="decisions-today" title="Decisões de hoje"
    subtitle={data.count > 0 ? `Prazo até ${formatDate(data.window_end)} · ${data.count} no total` : undefined}
    action={<Link className="secondary-button" to="/fila">Ver a fila</Link>}>
    {items.length === 0
      ? <p className="queue-none">Nenhuma decisão com prazo até {formatDate(data.window_end)}.</p>
      : <div className="table-shell" tabIndex={0} role="region" aria-label="Decisões de hoje; role horizontalmente para ver todas as colunas">
        <table className="data-table responsive-table">
          <caption className="sr-only">Decisões com prazo na janela, da mais próxima para a mais distante; cada sugestão exige revisão humana</caption>
          <thead><tr><th>Decidir até</th><th>SKU</th><th>Decisão</th></tr></thead>
          <tbody>{items.map((item) => <tr key={`${item.sku}-${item.lever}`}>
            <td data-label="Decidir até">{formatDate(item.decide_by)}</td>
            <td data-label="SKU"><Link className="link-button" to={`/skus/${encodeURIComponent(item.sku)}`} state={{ from: '/' }}><strong>{item.sku}</strong></Link> <small>{item.product}</small></td>
            <td data-label="Decisão">{item.label} · {LEVER_NAMES[item.lever] ?? item.lever} <Tooltip label={`Motivo da decisão em ${item.sku}`}>{item.reason}</Tooltip></td>
          </tr>)}</tbody>
        </table>
      </div>}
  </SectionCard>;
}
