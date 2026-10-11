/** Etapa 16.6: GET /api/rules/coverage — quantas vezes cada regra e cada rótulo disparam na base atual. */
export interface RuleCoverage {
  rule: string; kind: 'operational' | 'label'; label: string; condition: string; fires: number;
  /** Só regras operacionais (peso do ranking). */
  weight?: number;
  /** Só rótulos: disparos por nível. */
  fires_by_level?: { sku: number; commercial: number; partner: number; channel: number };
  /** Por que a regra não disparou (só quando fires = 0 e a base explica). */
  zero_reason: string | null; evidence_number: number | null; data_needed: string | null;
  reference_case: { case: string; origin: 'synthetic' | 'base' | string; title: string } | null;
}
export interface PrecedenceLine { level: 'operational' | 'commercial' | 'partner' | 'channel'; position: number; line: string; code: string; code_fires: number }
/** Pares KA sem sell-out suficiente com pedido em carteira: pedir o sell-out ao parceiro. */
export interface SellOutRequest { partner: string; sku: string; product: string; backlog_quantity: number; backlog_value: number | null; orders: string[] }
export interface RulesCoverage {
  rules: RuleCoverage[]; precedence: PrecedenceLine[]; sell_out_requests: SellOutRequest[];
  field_nature: Record<string, string>; limitations: string[]; requires_human_review: boolean;
}
