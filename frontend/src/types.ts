import type { ChallengeAction } from './types-actions';
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

export interface Priority {
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
}

export interface B2BVisibility {
  reference_month: string;
  partners: PartnerVisibility[];
  note: string;
  classification_disclaimer: string;
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
  status: CapacityStatus;
  peak_months: number[];
  peak_need_units: number;
  peak_status: CapacityStatus | null;
  skus_short: string[];
  affected_orders: Array<{ order: string; sku: string; client: string; quantity: number }>;
  weeks: Array<{ week_start: string; maximum: number; available: number; allocated: number; remaining: number; occupation_base: number }>;
}
export interface CapacityPlan {
  reference_date: string;
  families: CapacityFamily[];
  skus: Record<string, { family: string; status: string; status_now: string; status_label: string; unscheduled_quantity: number; executable_quantity_now: number }>;
  status_labels: Record<string, string>;
  assumptions: string[];
  field_nature: Record<string, { nature: string; origin: string }>;
  requires_human_review: boolean;
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
    orders: Array<{ index: number; due_date: string; quantity: number; status: CapacityStatus; unscheduled: number }> } | null;
}

export interface ForecastRecommendationSummary {
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

export interface SkuDetail {
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
}

export interface ScenarioResult {
  is_simulation: boolean;
  warning: string;
  weights: Record<string, number>;
  thresholds: Record<string, number>;
  ranking: Priority[];
}
