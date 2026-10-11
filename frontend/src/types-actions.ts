export type ChallengeCode =
  | 'produzir' | 'repor' | 'priorizar_producao' | 'priorizar_parceiro' | 'ampliar_mix'
  | 'recomendar_recompra' | 'reativar' | 'monitorar' | 'investigar' | 'sem_acao_necessaria';

export interface ChallengeEvidence { label: string; value: string | number | null; origin: string }

/** Etapa 16.4: alavanca que responde "o que decidir agora" (rótulos operacionais). */
export type Lever = 'alocar' | 'antecipar_op' | 'produzir_agora' | 'renegociar' | 'produzir_futuro' | 'rever_op' | 'nenhuma';

/** Rótulo de ação do desafio: camada derivada dos sinais existentes; nunca substitui a ação operacional ou comercial. */
export interface ChallengeAction {
  code: ChallengeCode; label: string; source: 'operational' | 'commercial' | 'partner' | 'channel'; origin_action: string | null;
  reason: string; signals_used: string[]; evidence: ChallengeEvidence[]; limitations: string[]; requires_human_review: boolean;
  /** Etapa 16.4, só nos rótulos operacionais (ausentes nos comerciais, de parceiro e de canal). */
  lever?: Lever | null; decide_by?: string | null; decide_by_reason?: string | null;
}

/** Etapa 16.4: GET /api/overview → decisions_today (decisões com prazo até window_end). */
export interface DecisionToday { sku: string; product: string; label: string; lever: Exclude<Lever, 'nenhuma'>; decide_by: string; reason: string }
export interface DecisionsToday { window_end: string; count: number; items: DecisionToday[] }
