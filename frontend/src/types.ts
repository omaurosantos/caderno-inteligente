import type { ChallengeAction, DecisionsToday } from './types-actions';
import type { AllocationSku } from './types-allocation';
import type { EventAlert, SkuEventScenario } from './types-events';
import type { RevenueItem } from './types-revenue';

export type PageId =
  | 'guide'
  | 'overview'
  | 'queue'
  | 'skus'
  | 'revenue'
  | 'cases'
  | 'quality'
  | 'b2b'
  | 'partners'
  | 'channels'
  | 'scenarios'
  | 'capacity'
  | 'model'
  | 'runs'
  | 'feedback'
  | 'validation'
  | 'audit';

export type Severity = 'crítica' | 'alta' | 'média' | 'baixa' | string;
export type Confidence = 'baixa' | 'média' | 'alta' | string;

export interface Reason {
  code: string;
  description: string;
  severity: Severity;
}

export interface Evidence {
  code: string;
  values_used: Record<string, unknown>;
  data_origin: string[];
}

/** Etapa 16.3: faixa de urgência (1 = pedido confirmado sem cobertura … 4 = rever OP ou excesso). */
export type UrgencyTier = 1 | 2 | 3 | 4;
export type AbcClass = 'A' | 'B' | 'C';

/** Etapa 16.3: valor em risco (R$). Ausente nunca vira zero: `null` + `missing_reason`. */
export interface ValueAtRisk {
  /** Pedidos confirmados sem cobertura na data prometida × preço vigente. */
  observed: number | null;
  /** Falta projetada só na demanda prevista × preço. */
  estimated: number | null;
  /** Excesso projetado × preço (o valor da faixa 3). */
  excess: number | null;
  /** observed + 0,5 × estimated: chave da fila oficial dentro da faixa. */
  weighted: number | null;
  unit_price: number | null;
  nature: { observed: 'observado'; estimated: 'estimado'; excess: 'calculado' };
  missing_reason: string | null;
  observed_basis?: 'alocacao' | 'pedidos_afetados';
}

/** Campos da fila oficial por faixa e valor (Etapa 16.3); ausentes em respostas antigas. */
export interface PriorityImpact {
  urgency_tier?: UrgencyTier;
  urgency_label?: string;
  urgency_reason?: string;
  urgency_nature?: 'observado' | 'estimado' | 'calculado' | string;
  value_at_risk?: ValueAtRisk;
  /** Curva ABC do cadastro (não usada no ranking) e a medida pelo faturamento dos últimos 12 meses. */
  abc_registry?: AbcClass | null;
  abc_measured?: AbcClass | null;
  /** "Pedido confirmado sem cobertura · R$ 63,9 mil em risco (KA-05, KA-02)". */
  priority_reason?: string;
}

export interface Priority extends PriorityImpact {
  priority: number;
  sku: string;
  product: string;
  family: string;
  attention_score: number;
  confidence: Confidence;
  confidence_reason: string;
  critical_date: string | null;
  critical_date_reason: 'first_promised_date' | 'first_production_completion' | null;
  operational_gap_quantity: number;
  projected_stock_quantity: number;
  first_promised_date: string | null;
  first_production_completion: string | null;
  sell_in_quantity: number | null;
  sell_out_quantity: number | null;
  sell_in_minus_sell_out_quantity: number | null;
  forecast_quantity: number | null;
  analysis_scope: 'SKU global';
  missing_data: string[];
  reasons: Reason[];
  evidence: Evidence[];
  disclaimer: string;
}

export interface SelectedSku {
  sku: string;
  product: string;
  family: string;
  priority: number | null;
  attention_score: number | null;
  confidence: Confidence;
  confidence_reason: string;
}

export interface Overview {
  total_skus: number;
  prioritized: number;
  rupture_sku_count: number;
  below_lead_time_count: number;
  below_safety_stock_count: number;
  rupture_signal_count: number;
  /** @deprecated Use rupture_sku_count. */
  risk_count: number;
  order_without_production: number;
  excess_count: number;
  low_confidence: number;
  decision_count: number;
  partner_data_influenced_decision_count: number;
  risk_distribution: Record<string, number>;
  confidence_distribution: Record<string, number>;
  /** Agregado do plano de suprimento (fase 2); `null` se a agregação falhar, sem afetar os demais indicadores. */
  projected_stock: ProjectedStockSummary | null;
  /** Etapa 16.4: decisões com prazo nos próximos 7 dias; `null` se o cálculo falhar, ausente em respostas antigas. */
  decisions_today?: DecisionsToday | null;
}

export interface ProjectedStockReading {
  shortfall_sku_count: number;
  /** Abaixo da segurança inclui os SKUs com falta. */
  below_safety_sku_count: number;
  first_shortfall_week: string | null;
}

export interface ProjectedStockSummary {
  reference_date: string | null;
  horizon_end: string | null;
  skus_evaluated: number;
  /** Só estoque atual e OPs abertas. */
  without_new_orders: ProjectedStockReading;
  /** Somando as ordens planejadas; a falta que sobra chega antes de qualquer reposição nova. */
  with_planned_orders: ProjectedStockReading;
  shortfall_skus: { sku: string; product: string | null; family: string | null; first_shortfall_date: string | null; first_shortfall_week: string; shortfall_with_plan: boolean }[];
  planned_production: { urgent_total: number; horizon_total: number; urgent_window_end: string | null };
  /** SKUs em falta em cada semana do horizonte, sem novas ordens e com o plano (gráfico do Início). Ausente em respostas antigas. */
  weekly?: { week_start: string; shortfall_sku_count: number; shortfall_with_plan_sku_count: number }[];
  excluded_skus: { sku: string; reason: string }[];
  limitations: string[];
  requires_human_review: true;
}

export interface Run {
  id: number;
  created_at: string;
  source_hash: string;
  prioritized_skus: number;
  /** Absent in APIs older than Etapa 6; null for snapshots without the extended payload. */
  comparison_schema_version?: number | null;
}

export interface CaseItem {
  id: number;
  sku: string;
  run_id: number | null;
  status: string;
  owner: string;
  due_date: string;
  action: string;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface PartnerVisibility {
  partner: string;
  name: string;
  observed_skus: number;
  total_skus: number;
  coverage: number;
  latest_sell_out_month: string | null;
  months_observed: number;
  level: 'Sem visibilidade' | 'Essencial' | 'Conectado' | 'Estratégico';
  next_level: 'Essencial' | 'Conectado' | 'Estratégico' | null;
  next_level_required_skus: number;
  next_level_requirement: string;
  /** Etapa 16.1: canais diretos entram com a visibilidade do faturamento (não com 0% de sell-out). */
  type?: string | null;
  visibility_source?: VisibilitySource;
}

/** De onde vem a visão da venda ao consumidor. */
export type VisibilitySource = 'sell_out_parceiro' | 'faturamento_direto';

export interface JourneyChannelType {
  type: string;
  visibility_source: VisibilitySource;
  billed_units: number;
  observed_consumer_units: number;
  /** Antes do teto pelo faturado (o sell-out de KA pode passar do faturado). */
  observed_consumer_units_raw: number;
  exceeds_billing: boolean;
  share_observed: number;
  without_visibility_units: number;
}

/** Etapa 16.1: jornada faturado → venda ao consumidor observada, por tipo de canal. */
export interface VisibilityJourney {
  window_months: string[];
  total_units: number;
  observed_consumer_units: number;
  without_visibility_units: number;
  observed_share: number;
  by_channel_type: JourneyChannelType[];
  nature: Record<string, string>;
  note: string;
}

export interface B2BVisibility {
  reference_month: string;
  partners: PartnerVisibility[];
  note: string;
  classification_disclaimer: string;
  journey?: VisibilityJourney | null;
}

export interface AppConfig {
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  actions: string[];
  partner_data_effects: string[];
  case_statuses: string[];
}

export interface FeedbackItem {
  sku: string;
  action: string;
  note: string;
  user_name: string;
  partner_data_effect: 'nao_utilizado' | 'confirmou' | 'aumentou_confianca' | 'alterou_decisao';
  analysis_minutes: number | null;
  created_at: string;
  challenge_action?: string | null;
}

export interface SheetQuality {
  records: number;
  duplicate_keys: number;
  missing_columns: string[];
  missing_values: Record<string, number>;
}

export interface DemandDivergenceItem {
  sku: string;
  registered_daily_demand: number;
  reference_daily_demand: number;
  ratio: number;
  demand_source: string;
  coverage_days_registered: number | null;
  coverage_days_calculated: number | null;
}

export interface DemandDivergenceWarning {
  code: 'REGISTERED_DEMAND_DIVERGENCE';
  threshold: number;
  count: number;
  items: DemandDivergenceItem[];
}

/** Etapa 16.1: Sell_In do KA difere do faturado em Vendas_24m acima do limite. */
export interface SellInBillingDivergenceWarning {
  code: 'SELLIN_BILLING_DIVERGENCE';
  sheet: string;
  count: number;
  limit: number;
  items: Array<{ partner: string; sell_in_units: number; billed_units: number; ratio: number }>;
  message: string;
}

/** Etapa 16.1: faturamento por cliente quase proporcional (rateio): não serve para padrões por parceiro. */
export interface BillingUniformSplitWarning {
  code: 'BILLING_UNIFORM_SPLIT';
  sheet: string;
  count: number;
  min_ratio: number;
  max_ratio: number;
  band: number;
  message: string;
}

/** Etapa 16.3: Curva ABC do cadastro diferente da medida pelo faturamento de 12 meses. */
export interface AbcRegistryDivergenceWarning {
  code: 'ABC_REGISTRY_DIVERGENCE';
  count: number;
  items: Array<{ sku: string; registry: AbcClass; measured: AbcClass; revenue_12m: number }>;
  message: string;
}

/** Avisos conhecidos de `DataQuality.warnings`; filtre por `code` antes de converter. */
export type KnownDataQualityWarning = DemandDivergenceWarning | SellInBillingDivergenceWarning | BillingUniformSplitWarning | AbcRegistryDivergenceWarning;

export interface DataQuality {
  errors: Array<Record<string, unknown>>;
  warnings: Array<Record<string, unknown>>;
  sheets: Record<string, SheetQuality>;
  foreign_keys: Array<{ child_sheet: string; orphan_count: number }>;
  sell_out_coverage: {
    observed_pairs: number;
    possible_pairs: number;
    coverage: number;
    missing_data_is_not_zero: boolean;
  };
}

export interface DashboardData {
  overview: Overview;
  priorities: Priority[];
  runs: Run[];
  cases: CaseItem[];
  b2b: B2BVisibility;
  config: AppConfig;
  feedback: FeedbackItem[];
  quality: DataQuality;
}

export interface SkuIssue extends Reason {
  sku: string;
  product: string;
  family: string;
  values_used: Record<string, unknown>;
  data_origin: string[];
}

export interface SkuIndicator {
  SKU: string;
  Produto: string;
  family: string;
  current_stock: number;
  coverage_days_calculated: number;
  /** Etapa 15.2: cobertura pelo campo cadastrado (Venda média/dia), mantida para comparação. */
  coverage_days_registered?: number | null;
  reference_daily_demand?: number | null;
  demand_source?: 'previsao_3m' | 'vendas_3m' | 'cadastro' | null;
  data_quality_warnings?: string[];
  lead_time_days: number;
  minimum_lot: number;
  average_sales_per_day: number;
  safety_stock_days: number;
  backlog_order_quantity: number;
  production_order_quantity: number;
  projected_stock_quantity: number;
  operational_gap_quantity: number;
  first_promised_date: string | null;
  first_production_completion: string | null;
  sell_in_quantity: number | null;
  sell_out_quantity: number | null;
  sell_in_minus_sell_out_quantity: number | null;
  sell_out_partner_count: number;
  has_sell_out: boolean;
  forecast_quantity: number | null;
  analysis_scope: 'SKU global';
  missing_data: string[];
}

export interface DemandForecast {
  sku: string;
  reference_month: string | null;
  history_months: number;
  model: string | null;
  model_label: string;
  forecast_months: string[];
  forecast_values: number[];
  forecast_next_month: number | null;
  forecast_total_3m: number | null;
  trend: 'crescente' | 'estável' | 'decrescente' | 'indeterminada';
  trend_change_ratio: number | null;
  backtest_wape: number | null;
  /** Motor v2 (Etapa 15.1): erro medido em origens rolantes que incluem meses de pico. */
  engine?: 'v1' | 'v2';
  forecast_total_6m?: number | null;
  backtest_windows?: number;
  backtest_peak_wape?: number | null;
  forecast_confidence: Confidence;
  status: 'ok' | 'insufficient_data';
  limitation: string;
}

export type OperationalAction = 'investigar_dados' | 'atraso_inevitavel' | 'antecipar_op' | 'produzir_validar_capacidade' | 'produzir'
  | 'rever_op' | 'monitorar_excesso' | 'sem_acao_necessaria';

/** Etapa 15.3: plano datado do SKU. */
export interface PlannedOrder { due_date: string; release_date: string; quantity: number; urgent: boolean; late?: boolean }
export interface OpAdjustment { order: string; quantity: number; finish: string | null; adjustment: 'antecipar' | 'reduzir' | 'cancelar'; suggested_quantity: number; suggested_finish?: string; reason: string }
export interface AffectedOrder { order: string; client: string; quantity: number; promised_date: string; expected_date: string | null; delay_days: number | null }

/** Etapa 15.4: capacidade semanal finita por família. */
export type CapacityStatus = 'ok' | 'pre_producao' | 'a_confirmar' | 'insuficiente';
/** Etapa 16.5: status sobre semanas estimadas além do calendário da base. */
export type EstimatedCapacityStatus = 'ok_estimado' | 'insuficiente_estimado';
export type CapacityFamilyStatus = CapacityStatus | EstimatedCapacityStatus;
export interface CapacityScenario { peak_status: CapacityFamilyStatus | null; unscheduled_quantity: number }
export interface CapacityFamily {
  family: string;
  line: string;
  calendar_start: string | null;
  calendar_end: string | null;
  available_until_calendar_end: number;
  planned_in_calendar: number;
  planned_after_calendar: number;
  unscheduled_quantity: number;
  first_shortfall_due: string | null;
  /** Etapa 16.5: pode ser um status estimado ('ok_estimado', 'insuficiente_estimado'). */
  status: CapacityFamilyStatus;
  peak_months: number[];
  peak_need_units: number;
  /** Idem. */
  peak_status: CapacityFamilyStatus | null;
  skus_short: string[];
  affected_orders: Array<{ order: string; sku: string; client: string; quantity: number }>;
  /** Etapa 16.5: semanas 'estimada' (além do calendário) trazem `method`; `occupation_base` pode ser nulo. */
  weeks: Array<{ week_start: string; maximum: number; available: number; allocated: number; remaining: number; occupation_base: number | null;
    nature?: 'observada' | 'estimada'; method?: string | null }>;
  /** Etapa 16.5: primeira semana estimada; ausente em respostas antigas. */
  estimated_from?: string | null;
  planned_in_estimated?: number;
  /** Central = capacidade máxima − média dos compromissos das últimas N semanas; conservador = menor disponível observada. */
  scenarios?: { central: CapacityScenario; conservador: CapacityScenario };
}
export interface CapacityPlan {
  reference_date: string;
  families: CapacityFamily[];
  skus: Record<string, { family: string; status: string; status_now: string; status_label: string; unscheduled_quantity: number; executable_quantity_now: number }>;
  status_labels: Record<string, string>;
  assumptions: string[];
  field_nature: Record<string, { nature: string; origin: string }>;
  requires_human_review: boolean;
  /** Etapa 16.5: parâmetros da capacidade estimada; ausente em respostas antigas. */
  extension?: { enabled: boolean; method: string | null; lookback_weeks: number | null; scenario: string | null };
}

export interface OperationalRecommendation {
  action: OperationalAction;
  action_label: string;
  horizon: string;
  suggested_quantity: number | null;
  raw_quantity: number | null;
  minimum_lot: number;
  forecast_next_month: number | null;
  backlog_quantity: number;
  safety_stock_quantity: number | null;
  current_stock: number;
  open_production_quantity: number;
  capacity_status: 'not_evaluated' | 'requires_review' | 'family_context_available';
  confidence: Confidence;
  confidence_reason: string;
  rationale: string[];
  calculation: Record<string, number | string | null>;
  assumptions: string[];
  limitations: string[];
  requires_human_review: boolean;
  secondary_actions?: OperationalAction[];
  planned_quantity_horizon?: number;
  planned_orders?: PlannedOrder[];
  op_adjustments?: OpAdjustment[];
  affected_orders?: AffectedOrder[];
  earliest_arrival?: string;
  first_shortfall_date?: string | null;
  projection?: Array<{ week_start: string; carteira: number; forecast_demand: number; op_receipts: number; planned_receipts: number;
    projected_end: number; projected_end_with_plan: number; below_safety: boolean; shortfall: boolean; shortfall_with_plan?: boolean }>;
  capacity?: { status: string; status_now: string; unscheduled_quantity: number; family: string;
    orders: Array<{ index: number; due_date: string; quantity: number; status: CapacityFamilyStatus; unscheduled: number }> } | null;
}

/** Em /api/forecasts os campos de impacto são `null` para SKU fora do ranking. */
export interface ForecastImpact {
  urgency_tier?: UrgencyTier | null;
  urgency_label?: string | null;
  value_at_risk?: ValueAtRisk | null;
  abc_registry?: AbcClass | null;
  abc_measured?: AbcClass | null;
  priority_reason?: string | null;
}

export interface ForecastRecommendationSummary extends ForecastImpact {
  sku: string;
  product: string;
  family: string;
  priority: number | null;
  attention_score: number | null;
  confidence: Confidence;
  confidence_reason: string;
  forecast: DemandForecast;
  /** Camada aditiva: rótulo de ação do desafio; ausente em respostas antigas. */
  challenge_action?: ChallengeAction;
  operational_recommendation: Pick<
    OperationalRecommendation,
    | 'secondary_actions'
    | 'planned_quantity_horizon'
    | 'first_shortfall_date'
    | 'action'
    | 'action_label'
    | 'suggested_quantity'
    | 'minimum_lot'
    | 'capacity_status'
    | 'confidence'
    | 'confidence_reason'
    | 'requires_human_review'
  >;
}

export interface SkuDetail extends ForecastImpact {
  indicator: SkuIndicator;
  issues: SkuIssue[];
  priority: Priority[];
  score_contributions: Array<{ code: string; weight: number; description: string }>;
  forecast: DemandForecast;
  /** Camada aditiva: ausente em respostas antigas e nula quando a estimativa falha. */
  revenue_forecast?: RevenueItem | null;
  challenge_action?: ChallengeAction;
  /** Camadas aditivas de eventos: ausentes em respostas antigas, nulas quando a análise falha. */
  event_alerts?: EventAlert[] | null;
  event_scenario?: SkuEventScenario | null;
  operational_recommendation: OperationalRecommendation;
  limitation: string;
  /** Etapa 16.2: "Quem atender primeiro" — bloco da alocação do SKU; `null` sem pedido aberto, ausente em respostas antigas. */
  allocation?: AllocationSku | null;
}

export interface ScenarioResult {
  is_simulation: boolean;
  warning: string;
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  ranking: Priority[];
}
