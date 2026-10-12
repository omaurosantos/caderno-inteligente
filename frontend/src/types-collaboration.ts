export interface CollaborationGap { criterion: string; current: number | null; required: number | boolean; text: string }

export interface CollaborationDimension { key: string; label: string; value: number; weight: number; basis: string; nature: string }

export interface CollaborationScenario {
  level: number; name: string; gives: string; gaps: CollaborationGap[]; additional_skus: number; rows_with_estimated_stock: number;
  unlocked: {
    rows_without_data_now: number; covered_backlog_quantity: number; covered_orders: number;
    candidate_skus: Array<{ sku: string; product: string | null; backlog_quantity: number | null; orders: number | null }>;
  };
  nature: string;
}

export interface CollaborationPartner {
  code: string; name: string; type: string; region: string | null; size: string | null; level: number; level_name: string; index: number | null;
  stock_position: string; observed_skus: number; total_skus: number; dimensions: CollaborationDimension[] | null; gaps: CollaborationGap[];
  next_level: string | null; scenarios: CollaborationScenario[]; insufficient_rows: number;
}

export interface CollaborationProgram {
  eligible_partners: number; participating_partners: number; adhesion: number | null; matrix_pairs_observed: number; matrix_pairs_total: number;
  matrix_coverage: number; mean_index: number | null; by_level: Array<{ level: number; name: string; partners: number }>;
  unit_visibility_share: number | null; reconciliation: string; evolution: null; evolution_reason: string;
  decisions: { available: boolean; reason: string };
}

export interface CollaborationOverview {
  reference_month: string; status: string | null; note: string | null;
  levels: Array<{ level: number; name: string; gives: string; min_completeness: number; min_frequency: number; min_index: number; requires_stock_position: boolean }>;
  weights: Record<string, number>; partners: CollaborationPartner[]; program: CollaborationProgram;
  field_nature: Record<string, string>; limitations: string[]; requires_human_review: boolean;
}
