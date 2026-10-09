/** GET /api/model-benchmark: cartão do modelo oficial e histórico do benchmark de modelos. */
export interface ModelCardModel {
  model: string;
  label: string;
  description: string;
  min_history_months: number;
  skus: number;
}

export interface ModelCardEvaluation {
  origins: string[];
  horizon_months: number;
  peak_months: number[];
  wape: number | null;
  peak_wape: number | null;
  normal_wape: number | null;
  bias: number | null;
  evaluated_points: number;
  metric: string;
}

export interface ModelCard {
  engine: 'v1' | 'v2';
  engine_label: string;
  target: { what: string; source: string; granularity: string };
  horizon_months: number;
  models: ModelCardModel[];
  data: { skus: number; skus_with_forecast: number; history_months_max: number | null; history_months_min: number | null };
  assumptions: string[];
  evaluation: ModelCardEvaluation | null;
  confidence: { rule: string; skus: Record<string, number> };
  limitations: string[];
  nature: string;
}

export type BenchmarkResultStatus = 'ok' | 'unavailable' | 'failed';

export interface BenchmarkResult {
  model: string;
  label: string;
  library: string;
  library_version: string | null;
  status: BenchmarkResultStatus;
  error_message: string | null;
  wape: number | null;
  peak_wape: number | null;
  normal_wape: number | null;
  bias: number | null;
  evaluated_points: number;
  fallback_points: number;
  duration_seconds: number;
  is_official: boolean;
  beats_official: boolean | null;
}

export interface BenchmarkRun {
  id: number;
  created_at: string;
  source_hash: string;
  official_model: string | null;
  note: string | null;
  results: BenchmarkResult[];
}

export interface BenchmarkRunSummary {
  id: number;
  created_at: string;
  models: number;
  best_model: string | null;
  best_wape: number | null;
}

export type ModelBenchmarkSection =
  | { status: 'no_run'; stale: null; note: string; run: null; history: [] }
  | { status: 'ok'; stale: boolean; note: string | null; run: BenchmarkRun; history: BenchmarkRunSummary[] };

export interface ModelBenchmark {
  official: ModelCard;
  benchmark: ModelBenchmarkSection;
}
