export interface MeasuredValue {
  value: number | null;
  unit: string | null;
  nature: 'informado' | 'recalculado' | 'meta';
  source?: string;
  comparable?: boolean;
  reason?: string;
}

export interface ProcessComparisonRow {
  id: string;
  label: string;
  informed: MeasuredValue;
  recalculated: MeasuredValue;
  target: MeasuredValue | null;
}

export interface AnalysisTime {
  feedback_count: number;
  records_with_minutes: number;
  total_minutes: number | null;
  average_minutes_per_decision: number | null;
  median_minutes_per_decision: number | null;
  minimum_sample: number;
  sample_status: 'suficiente' | 'insuficiente';
  comparison_allowed: boolean;
  note: string;
}

export interface ModelPerformance {
  model: string;
  label: string;
  role: 'candidato' | 'selecionado' | 'baseline';
  selected_skus: number;
  evaluated_skus: number;
  wape_defined_skus: number;
  median_wape: number | null;
  weighted_wape: number | null;
  peak_weighted_wape?: number | null;
  normal_weighted_wape?: number | null;
}

export interface ForecastEvaluationItem {
  sku: string;
  selected_model: string;
  selected_model_label: string;
  selected_wape: number | null;
  baseline_wape: number | null;
  candidate_wapes: Record<string, number | null>;
  outcome: 'superou' | 'nao_superou' | 'nao_comparavel';
  holdout_actual_total: number;
}

export interface ForecastEvaluation {
  /** 'rolante' no motor v2: origens rolantes com meses de pico; ausente no v1 (holdout dos últimos 3 meses). */
  method?: 'rolante';
  origins?: string[];
  holdout_months: number;
  total_skus: number;
  eligible_skus: number;
  insufficient_skus: number;
  insufficient_sku_list: string[];
  zero_demand_holdout_skus: number;
  baseline: { model: string; label: string; description: string };
  models: ModelPerformance[];
  beat_baseline_skus: number;
  did_not_beat_baseline_skus: number;
  not_comparable_skus: number;
  items: ForecastEvaluationItem[];
  limitations: string[];
}

export interface CaseCheck {
  field: string;
  expected: unknown;
  obtained: unknown;
  passed: boolean;
}

export interface FrozenCase {
  id: string;
  title: string;
  kind: 'operational' | 'commercial';
  origin: 'base' | 'synthetic';
  origin_reason: string | null;
  sku: string | null;
  partner: string | null;
  limitation: string;
  input: Record<string, unknown> | null;
  expected: Record<string, unknown>;
  obtained: Record<string, unknown> | null;
  checks: CaseCheck[];
  result: 'passou' | 'falhou' | 'nao_encontrado' | 'pendente';
  pending_until?: string | null;
  adjustment: string;
}

export interface FrozenCases {
  frozen_at: string;
  frozen_source_sha256: string;
  source_matches_frozen: boolean;
  source_note: string | null;
  policy: string;
  total: number;
  passed: number;
  failed: number;
  not_found: number;
  pending?: number;
  synthetic: number;
  items: FrozenCase[];
}

export interface SafeBehaviorCheck {
  id: string;
  label: string;
  status: 'aprovado' | 'reprovado' | 'coberto_por_teste';
  method: string;
  evidence: string;
}

export interface Adjustment {
  date: string;
  change: string;
  reason: string;
  evidence: string;
  changed_weights_or_models: boolean;
}

/** Etapa 16.7: soma do valor observado em risco dos SKUs com decisão registrada (valor sob decisão, não recuperado). */
export interface AddressedValue {
  /** `null` + `missing_reason` quando a persistência falha ou não há decisões registradas: ausente nunca vira zero. */
  observed_total: number | null;
  missing_reason?: string | null;
  sku_count: number;
  decided_skus: string[];
  /** Decididos sem valor observado calculado: ficam fora da soma. */
  skus_without_value: string[];
  nature: 'observado';
  note: string;
}

/** Etapa 16.7: pauta modelo × consenso S&OP (divergência acima do limite; não é erro de nenhum dos lados). */
export interface SopDivergence {
  months: string[];
  threshold: number;
  count: number;
  compared_pairs: number;
  items: Array<{ sku: string; month: string; model: number; sop: number; ratio: number }>;
  nature: 'calculado';
  note: string;
}

export interface ValidationSummary {
  generated_at: string;
  source: { sha256: string; sales_reference_month: string | null };
  process_comparison: ProcessComparisonRow[];
  analysis_time: AnalysisTime;
  forecast_evaluation: ForecastEvaluation;
  frozen_cases: FrozenCases;
  safe_behavior: SafeBehaviorCheck[];
  known_failures: Array<{ area: string; description: string }>;
  known_limitations: string[];
  adjustments: Adjustment[];
  requires_human_review: boolean;
  /** Etapa 16.7; ausentes em respostas antigas. */
  addressed_value?: AddressedValue;
  sop_divergence?: SopDivergence;
}
