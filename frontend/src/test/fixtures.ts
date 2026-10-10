// Synthetic fixtures typed against the frontend contracts. Never application data: codes start with TEST/KA-T.
import type { CapacityPlan, AppConfig, B2BVisibility, CaseItem, DataQuality, FeedbackItem, ForecastRecommendationSummary, Overview, Priority, Run, SkuDetail } from '../types';
import type { CommercialPage, CommercialRow, PartnerDetail, PartnerSummary } from '../types-commercial';
import type { ChallengeAction } from '../types-actions';
import type { ChannelFinding, ChannelSkuRow, ChannelSummary, DirectChannelDetail, DirectChannelsOverview } from '../types-channels';
import type { EventAlert, EventAnalysis, EventItem, EventScenario } from '../types-events';
import type { ForecastLab, SensitivityCell } from '../types-forecast-lab';
import type { BenchmarkResult, ModelBenchmark } from '../types-model-benchmark';
import type { ProductionPlan } from '../types-production';
import type { RevenueForecast, RevenueItem } from '../types-revenue';
import type { RunComparison } from '../types-runs';
import type { ValidationSummary } from '../types-validation';
import type { SystemInfo } from '../hooks/useSystemInfo';

export const SKU_OK = 'TEST-001';
export const SKU_SHORT = 'TEST / 002'; // Needs URL encoding and has insufficient history.
export const PARTNER = 'KA T1'; // Needs URL encoding.

export function priority(sku: string, position: number, overrides: Partial<Priority> = {}): Priority {
  return {
    priority: position, sku, product: `Produto ${sku}`, family: position % 2 ? 'Família A' : 'Família B', attention_score: 30 - position,
    confidence: position % 2 ? 'média' : 'baixa', confidence_reason: 'Motivo sintético da confiança.',
    critical_date: '2026-09-15', critical_date_reason: 'first_promised_date', operational_gap_quantity: 120, projected_stock_quantity: -20,
    first_promised_date: '2026-09-15', first_production_completion: '2026-09-20', sell_in_quantity: 300, sell_out_quantity: null,
    sell_in_minus_sell_out_quantity: null, forecast_quantity: 200, analysis_scope: 'SKU global', missing_data: ['sell_out_quantity'],
    reasons: [{ code: 'RUP_LEAD_TIME', description: 'Cobertura de estoque abaixo do lead time.', severity: 'alta' }],
    evidence: [{ code: 'RUP_LEAD_TIME', values_used: { coverage_days: 5, lead_time_days: 20 }, data_origin: ['Estoque_Atual.Estoque atual'] }],
    disclaimer: 'Ordenação de atenção; não é decisão automática.', ...overrides,
  };
}

export const priorities: Priority[] = [
  priority(SKU_OK, 1),
  priority(SKU_SHORT, 2, { confidence: 'baixa', family: 'Família B' }),
  priority('TEST-003', 3, { confidence: 'média', family: 'Família A', product: 'Agenda sintética' }),
];

export const overview: Overview = {
  total_skus: 4, prioritized: 3, rupture_sku_count: 2, below_lead_time_count: 2, below_safety_stock_count: 1, rupture_signal_count: 3,
  risk_count: 2, order_without_production: 1, excess_count: 0, low_confidence: 1, decision_count: 0, partner_data_influenced_decision_count: 0,
  risk_distribution: { RUP_LEAD_TIME: 2, RUP_SAFETY_STOCK: 1 }, confidence_distribution: { média: 2, baixa: 1 },
};

export const quality: DataQuality = {
  errors: [],
  warnings: [{ code: 'REGISTERED_DEMAND_DIVERGENCE', sheet: 'Produtos', column: 'Venda média/dia', threshold: 0.2, count: 2, description: 'Cadastro distante da demanda prevista.', items: [
    { sku: 'TEST-001', registered_daily_demand: 5, reference_daily_demand: 9, ratio: 1.8, demand_source: 'previsao_3m', coverage_days_registered: 10, coverage_days_calculated: 5.6 },
    { sku: 'TEST-002', registered_daily_demand: 10, reference_daily_demand: 5, ratio: 0.5, demand_source: 'previsao_3m', coverage_days_registered: 10, coverage_days_calculated: 20 },
  ] }],
  sheets: { Produtos: { records: 4, duplicate_keys: 0, missing_columns: [], missing_values: {} } },
  foreign_keys: [{ child_sheet: 'Estoque_Atual', orphan_count: 0 }],
  sell_out_coverage: { observed_pairs: 1, possible_pairs: 4, coverage: 0.25, missing_data_is_not_zero: true },
};

export const config: AppConfig = {
  weights: { RUP_LEAD_TIME: 8, RUP_SAFETY_STOCK: 10, EXCESS_COVERAGE: 3, CAPACITY_SHORTFALL: 7 },
  thresholds: { excess_coverage_days: 90, capacity_occupation_threshold: 0.9 },
  actions: ['aceita', 'alterada', 'rejeitada', 'investigar'],
  partner_data_effects: ['nao_utilizado', 'confirmou', 'aumentou_confianca', 'alterou_decisao'],
  case_statuses: ['novo', 'em_investigacao', 'concluido'],
};

export const runs: Run[] = [
  { id: 2, created_at: '2026-10-05T12:00:00+00:00', source_hash: 'hash-test-2-0123456789', prioritized_skus: 3, comparison_schema_version: 1 },
  { id: 1, created_at: '2026-10-01T12:00:00+00:00', source_hash: 'hash-test-1-0123456789', prioritized_skus: 3, comparison_schema_version: null },
];

export const cases: CaseItem[] = [{ id: 1, sku: SKU_OK, run_id: null, status: 'em_investigacao', owner: 'PCP', due_date: '2026-10-10', action: '', note: '', created_at: '2026-10-05T12:00:00+00:00', updated_at: '2026-10-05T12:00:00+00:00' }];
export const challenge = (code: ChallengeAction['code'], label: string, source: ChallengeAction['source'], reason: string, origin_action: string | null = null): ChallengeAction => ({
  code, label, source, origin_action, reason, signals_used: [], evidence: [{ label: 'Posição na fila de atenção', value: 3, origin: 'ranking oficial' }, { label: 'Sem valor', value: null, origin: 'teste' }],
  limitations: ['Não cria nem libera ordem de produção; a quantidade oficial não muda.'], requires_human_review: true,
});
export const challengeUrgent = challenge('priorizar_producao', 'Priorizar produção', 'operational', 'Produzir com urgência: posição 3 na fila de atenção (limite 10).', 'produzir');
export const challengeInvestigate = challenge('investigar', 'Investigar', 'operational', 'Histórico insuficiente para prever; investigar e completar os dados antes de sugerir produção.', 'investigar_dados');

export const feedback: FeedbackItem[] = [];

export const b2b: B2BVisibility = {
  reference_month: '2026-08-01', note: 'Cobertura representa observação disponível.', classification_disclaimer: 'Classificação demonstrativa.',
  partners: [{ partner: PARTNER, name: 'Parceiro sintético', observed_skus: 1, total_skus: 4, coverage: 0.25, latest_sell_out_month: '2026-08-01', months_observed: 3, level: 'Essencial', next_level: 'Conectado', next_level_required_skus: 1, next_level_requirement: 'Observar mais 1 SKU.' }],
};

const forecastOk = {
  sku: SKU_OK, reference_month: '2026-08-01', history_months: 24, model: 'moving_average_3' as const, model_label: 'Média móvel de 3 meses',
  forecast_months: ['2026-09-01', '2026-10-01', '2026-11-01'], forecast_values: [100, 110, 120], forecast_next_month: 100, forecast_total_3m: 330,
  trend: 'crescente' as const, trend_change_ratio: 0.12, backtest_wape: 0.08, forecast_confidence: 'alta', status: 'ok' as const, limitation: 'Previsão estatística sintética.',
  engine: 'v2' as const, backtest_windows: 7,
};
const forecastShort = {
  sku: SKU_SHORT, reference_month: '2026-08-01', history_months: 4, model: null, model_label: 'Não selecionado', forecast_months: [], forecast_values: [],
  forecast_next_month: null, forecast_total_3m: null, trend: 'indeterminada' as const, trend_change_ratio: null, backtest_wape: null,
  forecast_confidence: 'baixa', status: 'insufficient_data' as const, limitation: 'São necessários pelo menos 6 meses de histórico para estimar demanda.',
};

export const forecasts: ForecastRecommendationSummary[] = [
  { sku: SKU_OK, product: `Produto ${SKU_OK}`, family: 'Família A', priority: 1, attention_score: 29, confidence: 'média', confidence_reason: 'Motivo.', forecast: forecastOk, challenge_action: challengeUrgent,
    operational_recommendation: { action: 'produzir', action_label: 'Produzir', suggested_quantity: 200, minimum_lot: 100, capacity_status: 'family_context_available', confidence: 'alta', confidence_reason: 'Motivo.', requires_human_review: true,
      secondary_actions: [], planned_quantity_horizon: 600, first_shortfall_date: null } },
  { sku: SKU_SHORT, product: `Produto ${SKU_SHORT}`, family: 'Família B', priority: 2, attention_score: 28, confidence: 'baixa', confidence_reason: 'Motivo.', forecast: forecastShort, challenge_action: challengeInvestigate,
    operational_recommendation: { action: 'investigar_dados', action_label: 'Investigar dados', suggested_quantity: null, minimum_lot: 100, capacity_status: 'not_evaluated', confidence: 'baixa', confidence_reason: 'Histórico insuficiente.', requires_human_review: true } },
];

function indicator(sku: string) {
  return {
    SKU: sku, Produto: `Produto ${sku}`, family: 'Família A', current_stock: 50, coverage_days_calculated: 5, lead_time_days: 20, minimum_lot: 100,
    average_sales_per_day: 10, safety_stock_days: 10, backlog_order_quantity: 400, production_order_quantity: 0, projected_stock_quantity: -350,
    operational_gap_quantity: 350, first_promised_date: '2026-09-15', first_production_completion: null, sell_in_quantity: 300, sell_out_quantity: null,
    sell_in_minus_sell_out_quantity: null, sell_out_partner_count: 0, has_sell_out: false, forecast_quantity: null, analysis_scope: 'SKU global' as const,
    missing_data: ['sell_out_quantity', 'first_production_completion'],
    coverage_days_registered: 9, reference_daily_demand: 10, demand_source: 'previsao_3m' as const, data_quality_warnings: ['REGISTERED_DEMAND_DIVERGENCE'],
  };
}

const recommendationBase = {
  horizon: 'próximo mês', minimum_lot: 100, backlog_quantity: 400, current_stock: 50, open_production_quantity: 0,
  assumptions: ['Premissa sintética.'], limitations: ['A recomendação não cria nem libera ordem de produção.'], requires_human_review: true,
};

const observedMonths = ['2025-09-01', '2025-10-01', '2025-11-01', '2025-12-01', '2026-01-01', '2026-02-01', '2026-03-01', '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01'];
export const revenueOk: RevenueItem = {
  sku: SKU_OK, product: `Produto ${SKU_OK}`, family: 'Família A', status: 'ok', reason: null, unit_price: 12.5, price_source: 'Precos_Produtos', price_conflict: false,
  model_label: 'Média móvel de 3 meses', forecast_confidence: 'alta', forecast_months: ['2026-09-01', '2026-10-01', '2026-11-01'], forecast_units: [100, 110, 120],
  revenue_values: [1250, 1375, 1500], revenue_next_month: 1250, revenue_total_3m: 4125,
  commercial_reference: { months: ['2026-10-01', '2026-11-01'], commercial_units: [100, 100], model_revenue: 2875, commercial_revenue: 2500, difference_ratio: 0.15, origins: ['Consenso S&OP'], note: 'Comparação, não erro: o consenso comercial não substitui a previsão estatística.' },
  calculation: { formula: 'Faturamento estimado = previsão em unidades × preço unitário vigente', terms: [
    { month: '2026-09-01', units: 100, unit_price: 12.5, revenue: 1250 }, { month: '2026-10-01', units: 110, unit_price: 12.5, revenue: 1375 }, { month: '2026-11-01', units: 120, unit_price: 12.5, revenue: 1500 },
  ] },
  nature: 'estimado', observed_revenue: { months: observedMonths, values: observedMonths.map(() => 1000) },
};
export const revenueShort: RevenueItem = {
  sku: SKU_SHORT, product: `Produto ${SKU_SHORT}`, family: 'Família B', status: 'sem_previsao', reason: 'Sem previsão de unidades; não há como estimar faturamento.',
  unit_price: 20, price_source: 'Precos_Produtos', price_conflict: false, model_label: 'Não selecionado', forecast_confidence: 'baixa', forecast_months: [], forecast_units: [],
  revenue_values: [], revenue_next_month: null, revenue_total_3m: null, commercial_reference: null, calculation: null, nature: 'estimado',
  observed_revenue: { months: observedMonths, values: observedMonths.map(() => null) },
};
const revenueGroup = (label: string, total: number | null, withEstimate: number, size: number) => ({
  label, skus_total: size, skus_with_estimate: withEstimate,
  skus_excluded: withEstimate < size ? [{ sku: SKU_SHORT, status: 'sem_previsao' as const, reason: revenueShort.reason }] : [],
  by_month: total === null ? [] : [{ month: '2026-09-01', revenue: 1250 }, { month: '2026-10-01', revenue: 1375 }, { month: '2026-11-01', revenue: 1500 }], revenue_total_3m: total,
  confidence_distribution: { alta: withEstimate, média: 0, baixa: 0 }, backtest_wape: total === null ? null : 0.08,
  observed_revenue: { months: observedMonths, values: observedMonths.map(() => 1000) }, observed_last_3m_same_skus: total === null ? null : 3000, change_vs_last_3m: total === null ? null : 0.375,
  commercial_reference: total === null ? null : { months: ['2026-10-01', '2026-11-01'], skus_compared: 1, model_revenue: 2875, commercial_revenue: 2500, difference_ratio: 0.15 },
});
export const revenueForecast: RevenueForecast = {
  reference_month: '2026-08-01', nature: 'estimado', formula: 'Faturamento estimado = previsão em unidades × preço unitário vigente',
  items: [revenueOk, revenueShort], families: [revenueGroup('Família A', 4125, 1, 1), revenueGroup('Família B', null, 0, 1)], total: revenueGroup('Total da empresa', 4125, 1, 2),
  field_nature: { revenue_values: { nature: 'estimado', origin: 'calculado' } }, limitations: ['Estimativa, não faturamento realizado.', 'O preço é mantido constante.'],
};

const evidenceUp = { family: 'Família A', factor: 1.35, factor_raw: 1.35, capped: false, occurrences: 2, months_used: ['novembro'], evidence_status: 'aumento' as const, note: null };
const evidenceFlat = { family: 'Família A', factor: 1.0, factor_raw: 1.0, capped: false, occurrences: 4, months_used: ['janeiro', 'fevereiro'], evidence_status: 'sem_alteracao' as const, note: 'O histórico não mostra variação relevante neste período para a família; o calendário indica impacto, a evidência não.' };
const evidenceNone = { family: 'Família A', factor: null, factor_raw: null, capped: false, occurrences: 0, months_used: [], evidence_status: 'sem_historico_direto' as const, note: 'Evento sem histórico direto: apenas alerta; nenhum fator é estimado.' };
export const eventAlerts: EventAlert[] = [
  { event_id: 'lancamento', event: 'Lançamento Coleção Teste', start: '2026-10-15', end: '2026-10-31', impact: 'Alta', observation: 'Novos SKUs sem histórico direto', days_to_start: 45, decision_date: '2026-10-01', in_horizon: true, evidence: evidenceNone },
  { event_id: 'black-friday', event: 'Black Friday', start: '2026-11-20', end: '2026-11-30', impact: 'Alta', observation: 'Desconto', days_to_start: 81, decision_date: '2026-11-06', in_horizon: true, evidence: evidenceUp },
  { event_id: 'volta-as-aulas', event: 'Volta às Aulas', start: '2027-01-05', end: '2027-02-20', impact: 'Alta', observation: 'Pico', days_to_start: 127, decision_date: '2026-12-22', in_horizon: false, evidence: evidenceFlat },
];
export const eventScenario: EventScenario = {
  months: ['2026-09-01', '2026-10-01', '2026-11-01'], base_units: [100, 110, 120], factors: [null, null, 1.35], events: [null, 'Lançamento Coleção Teste', 'Black Friday'],
  scenario_units: [100, 110, 162], base_total_3m: 330, scenario_total_3m: 372, incremental_units_3m: 42, unit_price: 12.5, scenario_revenue_total_3m: 4650, base_revenue_total_3m: 4125,
  next_month_affected: false, nature: 'estimado', formula: 'Cenário = previsão base × fator do mês (histórico da família); meses sem evento ou sem evidência ficam com fator 1',
  quantity: { official: 500, with_event: 500, differs: false, note: 'A quantidade oficial cobre só o próximo mês.' },
};
export const eventItemOk: EventItem = { sku: SKU_OK, family: 'Família A', model: 'moving_average_3', lead_time_days: 14, scenario_applicable: true, scenario_note: null, alerts: eventAlerts, scenario: eventScenario };
export const eventItemShort: EventItem = { sku: SKU_SHORT, family: 'Família B', model: null, lead_time_days: 14, scenario_applicable: false, scenario_note: 'Sem previsão de unidades; não há como montar cenário.', alerts: [], scenario: null };
export const eventAnalysis: EventAnalysis = {
  reference_month: '2026-08-01', reference_date: '2026-08-31', horizon_end: '2026-11-30', settings: { maximum_factor: 3 },
  events: [
    { id: 'lancamento', name: 'Lançamento Coleção Teste', start: '2026-10-15', end: '2026-10-31', impact: 'Alta', observation: 'Novos SKUs sem histórico direto', all_families: false, families: [evidenceNone], unknown_families: [], has_history: false, days_to_start: 45, in_horizon: true, past: false, decision_date_earliest: '2026-09-29', skus_alerted: 26 },
    { id: 'black-friday', name: 'Black Friday', start: '2026-11-20', end: '2026-11-30', impact: 'Alta', observation: 'Desconto', all_families: true, families: [evidenceUp], unknown_families: [], has_history: true, days_to_start: 81, in_horizon: true, past: false, decision_date_earliest: '2026-10-24', skus_alerted: 50 },
    { id: 'passado', name: 'Evento passado', start: '2026-06-01', end: '2026-06-30', impact: 'Média', observation: null, all_families: true, families: [], unknown_families: [], has_history: true, days_to_start: -91, in_horizon: false, past: true, decision_date_earliest: null, skus_alerted: 0 },
  ],
  ignored_events: [], items: [eventItemOk, eventItemShort],
  family_factors: [{ family: 'Família A', month: 11, month_name: 'novembro', factor_raw: 1.35, factor: 1.35, capped: false }],
  field_nature: { factor: { nature: 'estimado', origin: 'histórico' } }, limitations: ['Cenário indicativo.'],
};

const channelMonths = ['2025-09-01', '2025-10-01', '2025-11-01', '2025-12-01', '2026-01-01', '2026-02-01', '2026-03-01', '2026-04-01', '2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01'];
const channelSummary = (code: string, name: string, revenue: number, share: number): ChannelSummary => ({
  code, name, region: 'Nacional', declared_coverage: 'Completo', declared_skus: 50, sell_out_rows: 0, observed_skus: 49, catalog_skus: 50,
  revenue_24m: revenue, units_24m: 180000, share_of_revenue: share, share_of_units: share, revenue_recent: 1376541, revenue_previous: 1361604, trend: 'estável', change_ratio: 0.011, yoy_ratio: 0.04,
  monthly: { months: channelMonths, revenue: channelMonths.map(() => 450000), units: channelMonths.map(() => 6000) },
  concentration: { top5_share: 0.27, skus_for_target_share: 25, target_share: 0.8 },
  backlog: { open_orders: 7, open_quantity: 2464, skus: 6 }, signal_counts: { GROWING: 1, NOT_SOLD: 1, OPEN_BACKLOG: 1 }, suggestion_counts: { acompanhar_crescimento: 1, avaliar_ampliacao_mix: 1, sem_acao_necessaria: 1 },
});
export const CHANNEL = 'Loja própria';
const channelMeta: Pick<DirectChannelDetail, 'reference_month' | 'signal_labels' | 'suggestion_labels' | 'field_nature' | 'limitations' | 'settings'> = {
  reference_month: '2026-08-01',
  signal_labels: { NOT_SOLD: 'Sem faturamento no canal', STOPPED: 'Parou de vender no canal', DECLINING: 'Em queda', GROWING: 'Em crescimento', DISCONTINUING_PRODUCT: 'Produto em descontinuação', OPEN_BACKLOG: 'Pedido em carteira' },
  suggestion_labels: { avaliar_ampliacao_mix: 'Avaliar ampliação de mix', avaliar_reativacao: 'Avaliar reativação', investigar_queda: 'Investigar queda', monitorar_saida_de_linha: 'Monitorar saída de linha', acompanhar_crescimento: 'Acompanhar crescimento', sem_acao_necessaria: 'Sem ação necessária' },
  field_nature: { stock: { nature: 'ausente', origin: 'Estoque_Atual só tem o CD Central' } }, limitations: ['Visibilidade vem do faturamento.'], settings: { trend_months: 3 },
};
const channelRow = (sku: string, over: Partial<ChannelSkuRow>): ChannelSkuRow => ({
  sku, product: `Produto ${sku}`, family: 'Família A', product_status: 'Ativo', months_sold: 24, first_month: '2024-09-01', last_month: '2026-08-01', units_24m: 9000, revenue_24m: 770000,
  share_in_channel: 0.066, rank: 1, cumulative_share: 0.066, units_recent: 1048, units_previous: 1072, trend: 'estável', change_ratio: -0.02, yoy_ratio: 0.24, partners_units_recent: 1195,
  direct_share_of_sku_recent: 0.28, backlog_open_quantity: null, backlog_open_orders: 0, signals: [],
  suggestion: { code: 'sem_acao_necessaria', label: 'Sem ação necessária', reason: 'Sem sinal de queda, parada, crescimento relevante ou lacuna de mix.', requires_human_review: true }, ...over,
});
export const channelRows: ChannelSkuRow[] = [
  channelRow('CH-001', { challenge_action: challenge('sem_acao_necessaria', 'Sem ação necessária', 'channel', 'Sem sinal de queda, parada, crescimento relevante ou lacuna de mix.', 'sem_acao_necessaria') }),
  channelRow('CH-002', { challenge_action: challenge('monitorar', 'Monitorar', 'channel', 'Média mensal recente acima da faixa neutra.', 'acompanhar_crescimento'), rank: 2, trend: 'crescente', change_ratio: 0.15, signals: ['GROWING', 'OPEN_BACKLOG'], backlog_open_quantity: 300, backlog_open_orders: 1, suggestion: { code: 'acompanhar_crescimento', label: 'Acompanhar crescimento', reason: 'Média mensal recente acima da faixa neutra.', requires_human_review: true } }),
  channelRow('CH-003', { challenge_action: challenge('ampliar_mix', 'Ampliar mix', 'channel', 'Produto ativo sem nenhum faturamento neste canal nos 24 meses.', 'avaliar_ampliacao_mix'), months_sold: 0, first_month: null, last_month: null, units_24m: null, revenue_24m: null, share_in_channel: null, rank: null, cumulative_share: null, units_recent: null, units_previous: null, trend: 'indeterminada', change_ratio: null, yoy_ratio: null, partners_units_recent: null, direct_share_of_sku_recent: null, signals: ['NOT_SOLD'], suggestion: { code: 'avaliar_ampliacao_mix', label: 'Avaliar ampliação de mix', reason: 'Produto ativo sem nenhum faturamento neste canal nos 24 meses.', requires_human_review: true } }),
];
export const channelFindings: ChannelFinding[] = [
  { code: 'DIRECT_COVERAGE_NOT_IN_SELL_OUT', severity: 'atenção', affects: ['E-commerce', CHANNEL], title: 'Cobertura dos canais diretos sem Sell_Out', summary: 'O cadastro declara cobertura completa.', treatment_label: 'Usa Vendas_24m',
    evidence: [{ channel: 'E-commerce', declared_coverage: 'Completo', declared_skus: 50, sell_out_rows: 0, billing_observed_skus: 50 }, { channel: CHANNEL, declared_coverage: 'Completo', declared_skus: 50, sell_out_rows: 0, billing_observed_skus: 49 }],
    treatment: 'A visão dos canais diretos usa o faturamento de Vendas_24m.' },
  { code: 'KA_SELL_IN_DIFFERS_FROM_BILLING', severity: 'atenção', affects: ['KA-01'], title: 'Sell_In difere do faturado', summary: 'As quantidades diferem.', treatment_label: 'Não reconciliado',
    evidence: { overlapping_pairs: 600, equal_pairs: 0, median_sell_in_over_billing: 2.79, billing_skus_per_partner: 50, sell_in_skus_per_partner: 10, billing_months: 24, sell_in_months: 12 }, treatment: 'Não reconciliado.' },
];
export const directChannels: DirectChannelsOverview = {
  ...channelMeta, totals: { direct_revenue_24m: 28164228, total_revenue_24m: 41288943, direct_share_of_revenue: 0.6821, direct_share_of_units: 0.6822 },
  channels: [channelSummary('E-commerce', 'E-commerce próprio', 11606120, 0.2811), channelSummary(CHANNEL, 'Loja própria', 7447799, 0.1804)], findings: channelFindings,
};
export const directChannelDetail: DirectChannelDetail = { ...channelMeta, challenge_labels: { ampliar_mix: 'Ampliar mix', monitorar: 'Monitorar' }, channel: channelSummary(CHANNEL, 'Loja própria', 7447799, 0.1804), total: channelRows.length, items: channelRows };

export const skuDetailOk: SkuDetail = {
  indicator: indicator(SKU_OK),
  issues: [{ sku: SKU_OK, product: `Produto ${SKU_OK}`, family: 'Família A', code: 'RUP_LEAD_TIME', description: 'Cobertura de estoque abaixo do lead time.', severity: 'alta', values_used: { coverage_days: 5 }, data_origin: ['Estoque_Atual.Estoque atual'] }],
  priority: [priorities[0]],
  score_contributions: [{ code: 'RUP_LEAD_TIME', weight: 8, description: 'Cobertura abaixo do lead time.' }],
  forecast: forecastOk,
  revenue_forecast: revenueOk,
  challenge_action: challengeUrgent,
  event_alerts: eventAlerts,
  event_scenario: { applicable: true, note: null, scenario: eventScenario },
  operational_recommendation: { ...recommendationBase, action: 'produzir', action_label: 'Produzir', suggested_quantity: 500, raw_quantity: 450, forecast_next_month: 100, safety_stock_quantity: 100, capacity_status: 'family_context_available', confidence: 'baixa', confidence_reason: 'Sell-out não observado.', rationale: ['Ordem planejada de 500 un. para chegar em 05/10, liberando até 15/09.'], calculation: { cover_end: '2026-11-02', demand_to_cover: 400, safety_stock_quantity: 100, current_stock: 50, open_production_quantity: 0, raw_quantity: 450 },
    planned_orders: [{ due_date: '2026-10-05', release_date: '2026-09-15', quantity: 500, urgent: true }], secondary_actions: [], earliest_arrival: '2026-10-05', first_shortfall_date: '2026-09-20',
    op_adjustments: [{ order: 'OP-T1', quantity: 800, finish: '2026-10-20', adjustment: 'reduzir', suggested_quantity: 300, reason: 'Excesso projetado.' }],
    affected_orders: [{ order: 'PED-T1', client: 'KA-T', quantity: 120, promised_date: '2026-10-01', expected_date: '2026-10-05', delay_days: 4 }],
    projection: [
      { week_start: '2026-09-14', carteira: 0, forecast_demand: 70, op_receipts: 0, planned_receipts: 0, projected_end: -20, projected_end_with_plan: -20, below_safety: true, shortfall: true, shortfall_with_plan: true },
      { week_start: '2026-09-21', carteira: 120, forecast_demand: 70, op_receipts: 0, planned_receipts: 500, projected_end: -210, projected_end_with_plan: 290, below_safety: false, shortfall: true, shortfall_with_plan: false },
    ],
    capacity: { status: 'insuficiente', status_now: 'insuficiente', unscheduled_quantity: 200, family: 'Família A', orders: [{ index: 0, due_date: '2026-10-05', quantity: 500, status: 'insuficiente', unscheduled: 200 }] } },
  limitation: 'A base não vincula pedidos a OPs por semana.',
};

export const skuDetailShort: SkuDetail = {
  ...skuDetailOk,
  indicator: indicator(SKU_SHORT),
  priority: [priorities[1]],
  forecast: forecastShort,
  revenue_forecast: revenueShort,
  challenge_action: challengeInvestigate,
  event_alerts: [],
  event_scenario: { applicable: false, note: eventItemShort.scenario_note, scenario: null },
  operational_recommendation: { ...recommendationBase, action: 'investigar_dados', action_label: 'Investigar dados', suggested_quantity: null, raw_quantity: null, forecast_next_month: null, safety_stock_quantity: null, capacity_status: 'not_evaluated', confidence: 'baixa', confidence_reason: 'Histórico insuficiente para produzir uma previsão quantitativa.', rationale: ['Investigar e completar o histórico antes de sugerir produção.'], calculation: {} },
};

const metadata = { challenge_labels: { repor: 'Repor', priorizar_parceiro: 'Priorizar parceiro' }, reference_month: '2026-08', limitation: 'Recomendação comercial demonstrativa.', thresholds: { recent_months: 3 }, field_nature: { estimated_stock: { nature: 'estimado na fonte', origin: 'Sell_Out' } } };

export const partnerSummary: PartnerSummary = {
  code: PARTNER, name: 'Parceiro sintético', type: 'Key account', region: 'Sudeste', channel: 'Varejo', state: 'SP', city: 'Cidade', observed_skus: 1,
  linked_skus: 2, total_catalog_skus: 4, coverage: 0.25, latest_sell_out_month: '2026-08', backlog_quantity: 120,
  action_counts: { avaliar_reposicao: 1, monitorar_estoque: 0, investigar_divergencia: 0, solicitar_atualizacao: 0, dados_insuficientes: 1, conter_reposicao: 0, monitorar_excesso_parceiro: 0 },
  quality_counts: { sufficient: 1, stale: 0, insufficient: 1 },
  challenge_action: challenge('priorizar_parceiro', 'Priorizar parceiro', 'partner', '2 pares com oportunidade de reposição, incluindo SKU entre os 10 primeiros.', 'avaliar_reposicao'),
};

export const commercialRow: CommercialRow = {
  partner: PARTNER, partner_name: 'Parceiro sintético', sku: SKU_OK, product: `Produto ${SKU_OK}`, region: 'Sudeste', channel: 'Varejo', reference_month: '2026-08',
  window_months: ['2026-06', '2026-07', '2026-08'], sell_in_recent: 90, sell_out_recent: 0, sell_in_months: ['2026-06', '2026-07', '2026-08'],
  sell_out_months: ['2026-06', '2026-07', '2026-08'], comparable_months: ['2026-06', '2026-07', '2026-08'], comparable_sell_in: 90, comparable_sell_out: 0,
  comparable_difference: 90, divergence_ratio: null, estimated_stock: null, stock_month: null, data_nature: 'Real', average_monthly_sell_out: 0,
  coverage_days: null, age_months: 0, missing_months: [], data_quality: 'insufficient', backlog_quantity: 120, backlog_order_count: 1,
  orders: [{ order: 'PED-T1', quantity: 120, promised_date: '2026-10-01', status: 'Confirmado' }],
  signals: [{ code: 'INSUFFICIENT_PARTNER_DATA', label: 'Dados insuficientes para recomendar' }], action: 'dados_insuficientes',
  action_label: 'Sem recomendação por dados insuficientes', requires_human_review: true, recommendation_reason: 'Sem estoque estimado.',
  buildup_window_months: 6, sell_through_window: null, stock_start: null, stock_growth: null, stock_identity_consistent: null,
  periods: [{ month: '2026-08', sell_in_quantity: 30, sell_out_quantity: 0, estimated_stock: null, data_nature: 'Real' }],
  challenge_action: challenge('repor', 'Repor', 'commercial', 'Cobertura estimada baixa para o giro observado; avaliar reposição.', 'avaliar_reposicao'),
};

export const partnersPage: CommercialPage<PartnerSummary> = { ...metadata, items: [partnerSummary], total: 1, offset: 0, limit: 200 };
export const partnerRows: CommercialPage<CommercialRow> = { ...metadata, items: [commercialRow], total: 1, offset: 0, limit: 50 };
export const partnerDetail: PartnerDetail = { ...metadata, partner: partnerSummary, decisions: { attribution_available: false, items: null, reason: 'O feedback não registra o código do parceiro.' } };

export const validationSummary: ValidationSummary = {
  generated_at: '2026-10-05T12:00:00+00:00',
  source: { sha256: 'abc123abc123abc123', sales_reference_month: '2026-08-01' },
  process_comparison: [{ id: 'analysis_time', label: 'Tempo de análise do PCP', informed: { value: 22, unit: 'horas/semana', nature: 'informado', source: 'Fonte sintética' }, recalculated: { value: null, unit: 'horas/semana', nature: 'recalculado', comparable: false, reason: 'Amostra insuficiente.' }, target: { value: 8, unit: 'horas/semana', nature: 'meta' } }],
  analysis_time: { feedback_count: 0, records_with_minutes: 0, total_minutes: null, average_minutes_per_decision: null, median_minutes_per_decision: null, minimum_sample: 20, sample_status: 'insuficiente', comparison_allowed: false, note: 'Amostra insuficiente.' },
  forecast_evaluation: {
    method: 'rolante', holdout_months: 3, total_skus: 2, eligible_skus: 1, insufficient_skus: 1, insufficient_sku_list: [SKU_SHORT], zero_demand_holdout_skus: 0,
    baseline: { model: 'naive_last', label: 'Baseline', description: 'Último mês.' },
    models: [
      { model: 'selected', label: 'Selecionado', role: 'selecionado', selected_skus: 1, evaluated_skus: 1, wape_defined_skus: 1, median_wape: 0.1, weighted_wape: 0.1, peak_weighted_wape: 0.12, normal_weighted_wape: 0.09 },
      { model: 'naive_last', label: 'Baseline', role: 'baseline', selected_skus: 0, evaluated_skus: 1, wape_defined_skus: 1, median_wape: 0.2, weighted_wape: 0.2, peak_weighted_wape: 0.3, normal_weighted_wape: 0.15 },
    ],
    beat_baseline_skus: 1, did_not_beat_baseline_skus: 0, not_comparable_skus: 0, items: [], limitations: ['Holdout otimista.'],
  },
  frozen_cases: { frozen_at: '2026-10-05', frozen_source_sha256: 'abc', source_matches_frozen: true, source_note: null, policy: 'Política.', total: 0, passed: 0, failed: 0, not_found: 0, pending: 0, synthetic: 0, items: [] },
  safe_behavior: [{ id: 'a', label: 'Verificação', status: 'aprovado', method: 'executado', evidence: 'ok' }],
  known_failures: [], known_limitations: ['Limitação.'], adjustments: [], requires_human_review: true,
};

function labCell(outer: number, minimum: number, overrides: Partial<SensitivityCell> = {}): SensitivityCell {
  const lengths = [15, 18, 21].slice(3 - outer);
  return {
    outer_windows: outer, minimum_windows: minimum, is_default: false, outer_train_lengths: lengths, skus: 2,
    v1_wape: 0.09, rolling_wape: 0.07, baseline_wape: 0.17, v1_bias: -0.043, rolling_bias: -0.019,
    rolling_better_skus: 1, equal_skus: 1, rolling_worse_skus: 0, relative_wape_gain: 0.22, wape_criterion_met: true,
    bias_worsening_pp: -2.4, bias_criterion_met: true, skus_beating_baseline_rolling: 2, skus_beating_baseline_v1: 1,
    baseline_criterion_met: true, all_met: true, ...overrides,
  };
}

export const forecastLab: ForecastLab = {
  generated_at: '2026-10-07T12:00:00+00:00',
  source: { sha256: 'abc123abc123abc123' },
  engine: 'v1',
  official_engine_label: 'Motor atual sintético.',
  promotion_status: 'pendente',
  promotion_note: 'Nada foi promovido: as previsões oficiais seguem o motor atual.',
  baseline: { model: 'naive_last', label: 'Baseline' },
  selection: {
    skus: 2, skipped_skus: 0, changed_skus: 1,
    models: [
      { model: 'moving_average_3', label: 'Média móvel de 3 meses', description: 'Média dos últimos 3 meses.', complexity: 1, min_history_months: 3, official_selected_skus: 2, rolling_selected_skus: 1, evaluated_skus: 2, median_wape: 0.104 },
      { model: 'ses', label: 'Suavização exponencial simples', description: 'Nível que pesa mais o recente.', complexity: 3, min_history_months: 6, official_selected_skus: 0, rolling_selected_skus: 1, evaluated_skus: 2, median_wape: 0.081 },
    ],
    changed: [{ sku: SKU_OK, official_model: 'moving_average_3', official_model_label: 'Média móvel de 3 meses', rolling_model: 'ses', rolling_model_label: 'Suavização exponencial simples', rolling_wape: 0.067 }],
  },
  nested: {
    outer_windows: 2, outer_train_lengths: [18, 21], skus: 2,
    aggregate: {
      v1: { weighted_wape: 0.0899, weighted_bias: -0.0429, skus_beating_baseline: 1 },
      rolling: { weighted_wape: 0.0705, weighted_bias: -0.019, skus_beating_baseline: 2 },
      baseline: { weighted_wape: 0.1702, weighted_bias: 0.0854, skus_beating_baseline: 0 },
    },
    rolling_vs_v1: { rolling_better: 1, equal: 1, rolling_worse: 0 },
    criteria: {
      relative_wape_gain: 0.2162, min_relative_wape_gain: 0.05, wape_criterion_met: true, bias_worsening_pp: -2.3833, max_bias_worsening_pp: 2,
      bias_criterion_met: true, skus_beating_baseline_rolling: 2, skus_beating_baseline_v1: 1, baseline_criterion_met: true, all_met: true,
    },
  },
  peak_evaluation: {
    origins: ['2025-11', '2025-12', '2026-01'], horizon_months: 3, peak_months: [11, 1, 2], skus: 2,
    procedures: {
      v1: { label: 'Motor v1', weighted_wape: 0.1007, weighted_bias: -0.0402, peak_wape: 0.1322, peak_bias: -0.053, normal_wape: 0.0889, normal_bias: -0.0354, skus_beating_baseline: 1 },
      v2: { label: 'Motor v2', weighted_wape: 0.0798, weighted_bias: 0.001, peak_wape: 0.0787, peak_bias: 0.0073, normal_wape: 0.0802, normal_bias: -0.0014, skus_beating_baseline: 2 },
      v2_ratio_2: { label: 'Motor v2 com teto 2,0', weighted_wape: 0.0836, weighted_bias: -0.0056, peak_wape: 0.0924, peak_bias: -0.0169, normal_wape: 0.0802, normal_bias: -0.0014, skus_beating_baseline: 2 },
      baseline: { label: 'Baseline', weighted_wape: 0.1887, weighted_bias: 0.0566, peak_wape: 0.2682, peak_bias: -0.0094, normal_wape: 0.1588, normal_bias: 0.0815, skus_beating_baseline: 0 },
    },
    criteria: { relative_wape_gain: 0.2075, peak_bias: 0.0073, max_abs_peak_bias: 0.1, bias_worsening_pp: -3.92, skus_beating_baseline_v2: 2, skus_beating_baseline_v1: 1, all_met: true },
  },
  sensitivity: {
    cells: [
      labCell(1, 1, { relative_wape_gain: 0.2264 }),
      labCell(2, 1, { is_default: true, relative_wape_gain: 0.2162 }),
      labCell(3, 2, { relative_wape_gain: -0.2673, wape_criterion_met: false, all_met: false, baseline_criterion_met: false }),
    ],
    summary: { cells: 3, cells_all_met: 2, robust: false, default_all_met: true, min_relative_wape_gain: -0.2673, max_relative_wape_gain: 0.2264 },
  },
  intervals: {
    lower_quantile: 0.1, upper_quantile: 0.9, level: 0.8, minimum_residuals: 6, skus_with_band: 1, skus_without_band: 1,
    calibration: { nominal_level: 0.8, tested_months: 150, hits: 72, coverage: 0.48, skus_tested: 50, origin_train_lengths: [21], median_relative_width: 0.131 },
    items: [{ sku: SKU_OK, model: 'ses', model_label: 'Suavização exponencial simples', month: '2026-09-01', point: 211.7, lower: 197.8, upper: 215.9, residuals: 9 }],
    status: 'calibrada', status_note: null,
  },
  limitations: ['Laboratório sintético.'],
  field_nature: { nested: { nature: 'calculado', origin: 'Vendas_24m sintético' } },
  requires_human_review: true,
};

export const runComparison: RunComparison = {
  base: { ...runs[1], comparison_schema_version: null }, target: { ...runs[0], comparison_schema_version: 1 },
  context: { source_changed: false, weights_changes: [], thresholds_changes: [], commercial_thresholds: { available: false, reason: 'Não preservado.' } },
  comparable: true,
  ranking: { available: true, entered: [], exited: [], changed: [], unchanged_count: 3, summary: { entered: 0, exited: 0, changed: 0, unchanged: 3, moved_up: 0, moved_down: 0, score_changed: 0, confidence_changed: 0, with_new_signals: 0, unexplained: 0 } },
  forecasts: { available: false, reason: 'Execução #1 foi registrada antes da comparação ampliada.' },
  b2b_coverage: { available: false, reason: 'Execução #1 foi registrada antes da comparação ampliada.' },
  notes: [], limitations: ['Limitação.'],
};

export const system: SystemInfo = {
  environment: 'development', demo_mode: false, write_enabled: true, notice: null,
  text_limits: { note: 2000, user_name: 80, owner: 80, case_action: 200, analysis_minutes: 1440 },
};

export const capacityPlan: CapacityPlan = {
  reference_date: '2026-09-14',
  families: [
    { family: 'Escolar', line: 'Linha Escolar', calendar_start: '2026-09-14', calendar_end: '2026-10-04', available_until_calendar_end: 1680, planned_in_calendar: 1600,
      planned_after_calendar: 400, unscheduled_quantity: 800, first_shortfall_due: '2026-10-05', status: 'insuficiente', peak_months: [11, 1, 2], peak_need_units: 1200,
      peak_status: 'insuficiente', skus_short: [SKU_OK], affected_orders: [{ order: 'PED-1', sku: SKU_OK, client: 'KA-01', quantity: 400 }],
      weeks: [{ week_start: '2026-09-14', maximum: 1000, available: 960, allocated: 960, remaining: 0, occupation_base: 0.92 },
        { week_start: '2026-09-21', maximum: 1000, available: 720, allocated: 640, remaining: 80, occupation_base: 0.94 }] },
    { family: 'Refis', line: 'Linha Refis', calendar_start: '2026-09-14', calendar_end: '2026-10-04', available_until_calendar_end: 8400, planned_in_calendar: 500,
      planned_after_calendar: 0, unscheduled_quantity: 0, first_shortfall_due: null, status: 'ok', peak_months: [11, 1, 2], peak_need_units: 0, peak_status: null,
      skus_short: [], affected_orders: [], weeks: [{ week_start: '2026-09-14', maximum: 10000, available: 8400, allocated: 500, remaining: 7900, occupation_base: 0.76 }] },
  ],
  skus: { [SKU_OK]: { family: 'Escolar', status: 'insuficiente', status_now: 'insuficiente', status_label: 'Não cabe até a data de necessidade', unscheduled_quantity: 800, executable_quantity_now: 200 } },
  status_labels: { ok: 'Cabe na semana planejada', insuficiente: 'Não cabe até a data de necessidade' },
  assumptions: ['Premissa sintética.'],
  field_nature: { allocated: { nature: 'calculado', origin: 'sintético' } },
  requires_human_review: true,
};

// Coerente com `forecasts`: TEST-001 (Família A) tem 200 un. sugeridas agora e 600 no horizonte; TEST-002 não tem previsão.
export const productionPlan: ProductionPlan = {
  reference_date: '2026-09-14', horizon_end: '2027-02-28', urgent_window_end: '2026-10-12', max_lead_time_days: 20,
  total: { months: [{ month: '2026-09', urgent: 200, later: 0 }, { month: '2026-10', urgent: 0, later: 300 }, { month: '2026-11', urgent: 0, later: 0 }, { month: '2026-12', urgent: 0, later: 100 }], urgent_total: 200, horizon_total: 600 },
  families: [{ family: 'Família A', months: [{ month: '2026-09', urgent: 200, later: 0 }, { month: '2026-10', urgent: 0, later: 300 }, { month: '2026-11', urgent: 0, later: 0 }, { month: '2026-12', urgent: 0, later: 100 }], urgent_total: 200, horizon_total: 600 }],
  excluded_skus: [{ sku: SKU_SHORT, reason: 'sem_previsao' }],
  omitted_months: ['2027-01', '2027-02'],
  field_nature: { urgent: { nature: 'estimado', origin: 'ordens planejadas com liberação dentro da janela de decisão' }, later: { nature: 'estimado', origin: 'ordens planejadas com liberação depois da janela de decisão' } },
  limitations: ['Plano sugerido, não ordem liberada: cada ordem exige revisão humana antes de virar OP.'],
  requires_human_review: true,
};

const benchmarkResult = (model: string, label: string, wape: number | null, extra: Partial<BenchmarkResult> = {}): BenchmarkResult => ({
  model, label, library: 'teste', library_version: '1.0', status: 'ok', error_message: null,
  wape, peak_wape: wape === null ? null : wape + 0.01, normal_wape: wape, bias: wape === null ? null : -0.012,
  evaluated_points: 30, fallback_points: 0, duration_seconds: 1.5, is_official: false, beats_official: wape === null ? null : wape < 0.08, ...extra,
});

export const modelBenchmark: ModelBenchmark = {
  official: {
    engine: 'v2',
    engine_label: 'Motor sintético: mês do ano anterior ajustado pelo nível',
    target: { what: 'Unidades faturadas por SKU e mês', source: 'Vendas sintéticas somadas entre canais', granularity: 'SKU × mês' },
    horizon_months: 6,
    models: [
      { model: 'seasonal_level', label: 'Mês do ano anterior ajustado pelo nível', description: 'Mesmo mês do ano anterior, ajustado pelo nível.', min_history_months: 15, skus: 2 },
      { model: 'moving_average_3', label: 'Média móvel de 3 meses', description: 'Média dos últimos 3 meses.', min_history_months: 3, skus: 0 },
    ],
    data: { skus: 3, skus_with_forecast: 2, history_months_max: 24, history_months_min: 4 },
    assumptions: ['Premissa sintética do nível.', 'Previsão nunca negativa.'],
    evaluation: { origins: ['2025-11', '2025-12'], horizon_months: 3, peak_months: [11, 1], wape: 0.08, peak_wape: 0.079, normal_wape: 0.081, bias: 0.001, evaluated_points: 12, metric: 'WAPE agrupado' },
    confidence: { rule: 'Regra sintética de confiança.', skus: { alta: 2, 'média': 0, baixa: 1 } },
    limitations: ['Limitação sintética.'],
    nature: 'calculado',
  },
  benchmark: {
    status: 'ok', stale: false, note: null,
    run: {
      id: 2, created_at: '2026-10-09T12:00:00+00:00', source_hash: 'abc', official_model: 'seasonal_level', note: null,
      results: [
        benchmarkResult('official', 'Motor oficial', 0.08, { is_official: true, beats_official: null }),
        benchmarkResult('auto_arima', 'AutoARIMA sintético', 0.133, { fallback_points: 3 }),
        benchmarkResult('prophet', 'Prophet sintético', 0.364),
        benchmarkResult('lightgbm', 'LightGBM sintético', null, { status: 'unavailable', error_message: 'Biblioteca ausente: lightgbm' }),
      ],
    },
    history: [
      { id: 2, created_at: '2026-10-09T12:00:00+00:00', models: 4, best_model: 'official', best_wape: 0.08 },
      { id: 1, created_at: '2026-10-08T12:00:00+00:00', models: 2, best_model: 'official', best_wape: 0.08 },
    ],
  },
};
