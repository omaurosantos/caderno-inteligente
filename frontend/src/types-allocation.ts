/** Etapa 16.2: alocação sugerida dos pedidos confirmados sem cobertura (estoque do CD + OPs + ordens planejadas; nunca a previsão). */
export type AllocationComponentCode = 'urgencia' | 'canal_direto' | 'cobertura_baixa_parceiro' | 'estoque_acumulando_parceiro' | 'sem_sell_out' | 'pedido_pequeno';
export type AllocationNature = 'observado' | 'cadastral' | 'estimado' | 'ausente';

export interface AllocationScoreComponent {
  component: AllocationComponentCode; points: number; value: number | string | null; nature: AllocationNature; reason: string;
}
export interface AllocationLater { quantity: number; expected_date: string; source: 'op' | 'planejada' | string; source_ref: string | null }
export interface AllocationOrder {
  order: string; client: string; client_type: string | null; region: string; quantity: number; promised_date: string | null; rank: number;
  allocation_score: number; score_components: AllocationScoreComponent[];
  /** Coberto até max(data prometida, referência). */
  allocated_now: number;
  uncovered_at_promise: number;
  allocated_later: AllocationLater[];
  /** Data em que o pedido fica 100% coberto; `null` = não cobre no horizonte. */
  expected_date: string | null; delay_days: number | null;
  /** Atraso pela regra atual (data prometida), para comparação. */
  fifo_delay_days: number | null;
  reason: string;
}
export interface AllocationSku {
  sku: string; has_shortfall: boolean; contested: boolean; clients: string[]; unit_price: number | null;
  orders: AllocationOrder[]; uncovered_units_at_promise: number;
  /** `null` quando falta preço (nunca R$ 0). */
  uncovered_value_at_promise: number | null;
  /** "Atender KA-02 (534 un.) integralmente; KA-05 recebe N un. agora e o restante em dd/mm com a OP-xxxx". */
  decision_text: string; first_client: string | null; last_client: string | null;
  orders_with_partner_data: number; data_note: string; orders_without_date: string[];
  missing_price_reason?: string;
}
export interface AllocationTotals {
  uncovered_units: number; uncovered_value: number | null; orders: number; skus: number; contested_skus: string[]; shortfall_skus: string[];
}
export interface AllocationRegion { region: string; uncovered_units: number; uncovered_value: number | null; orders: number; skus: string[] }

/** GET /api/allocation (filtros opcionais sku, regiao, cliente): só SKUs com falta ou disputados. */
export interface AllocationResponse {
  reference_date: string; total: number; items: AllocationSku[]; totals: AllocationTotals;
  field_nature: Record<string, { nature: string; origin: string }>; limitations: string[]; requires_human_review: true;
}
/** GET /api/allocation/regions: a soma das regiões é o total descoberto. */
export interface AllocationRegions {
  reference_date: string; regions: AllocationRegion[]; totals: AllocationTotals; limitations: string[]; requires_human_review: true;
}
