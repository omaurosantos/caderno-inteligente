import { Badge, Tooltip } from '../components';
import { displayNumber, formatDate } from '../pages/shared';
import type { ChallengeAction, ChallengeCode, Lever } from '../types-actions';

const TONE: Record<ChallengeCode, string> = {
  priorizar_producao: 'high', priorizar_parceiro: 'high', produzir: 'info', repor: 'info', ampliar_mix: 'info', recomendar_recompra: 'info',
  reativar: 'info', monitorar: 'neutral', investigar: 'medium', sem_acao_necessaria: 'neutral',
};

/** Etapa 16.4: nome curto da alavanca, que responde "o que decidir agora". `nenhuma` não é exibida. */
export const LEVER_LABELS: Record<Exclude<Lever, 'nenhuma'>, string> = {
  alocar: 'Alocar estoque', antecipar_op: 'Antecipar OP', produzir_agora: 'Produzir agora', renegociar: 'Renegociar prazo', produzir_futuro: 'Produzir', rever_op: 'Rever OP',
};

const evidenceValue = (value: string | number) => typeof value === 'number' ? displayNumber(value) : value;
const leverName = (action: ChallengeAction) => action.lever && action.lever !== 'nenhuma' ? LEVER_LABELS[action.lever] ?? null : null;

/** Selo do rótulo com o porquê, as evidências e a ressalva de revisão humana no "?". Sem rótulo, não renderiza nada. */
export function ChallengeBadge({ action }: { action?: ChallengeAction | null }) {
  if (!action) return null;
  const evidence = action.evidence.filter((item) => item.value !== null).map((item) => `${item.label}: ${evidenceValue(item.value as string | number)}`).join('; ');
  const lever = leverName(action);
  const leverText = lever ? ` Alavanca: ${lever}${action.decide_by ? `, decidir até ${formatDate(action.decide_by)}` : ''}.` : '';
  return <><Badge tone={TONE[action.code] ?? 'neutral'}>{action.label}</Badge><Tooltip label={`Por que: ${action.label}`}>{action.reason}{evidence ? ` Evidências: ${evidence}.` : ''}{leverText} {action.limitations[0]} Revisão humana obrigatória.</Tooltip></>;
}

/** Linha visível da alavanca e do prazo de decisão (rótulos operacionais). Sem alavanca (ou `nenhuma`), não renderiza nada. */
export function ChallengeLever({ action }: { action?: ChallengeAction | null }) {
  const lever = action ? leverName(action) : null;
  if (!action || !lever) return null;
  return <p className="answer-why">Decisão: <strong>{lever}</strong>{action.decide_by ? <> · decidir até <strong>{formatDate(action.decide_by)}</strong></> : ''}
    {action.decide_by_reason && <Tooltip label="Por que este prazo">{action.decide_by_reason}. Sugestão para revisão humana.</Tooltip>}</p>;
}
