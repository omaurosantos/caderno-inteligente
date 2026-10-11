import type { AllocationRegions, AllocationResponse } from './types-allocation';
import type { CommercialPage, CommercialRow, PartnerDetail, PartnerSummary } from './types-commercial';
import type { ChannelFinding, DirectChannelDetail, DirectChannelsOverview } from './types-channels';
import type { EventAnalysis } from './types-events';
import type { ForecastLab } from './types-forecast-lab';
import type { ModelBenchmark } from './types-model-benchmark';
import type { ProductionPlan } from './types-production';
import type { LoginResult, SessionUser, SkuFields, SkuRegistry, SkuSaved } from './types-registry';
import type { RevenueForecast } from './types-revenue';
import type { RulesCoverage } from './types-rules';
import type { RunComparison } from './types-runs';
import type { ValidationSummary } from './types-validation';
import type { SystemInfo } from './hooks/useSystemInfo';
import type {
  CapacityPlan,
  AppConfig,
  B2BVisibility,
  CaseItem,
  DashboardData,
  DataQuality,
  FeedbackItem,
  ForecastRecommendationSummary,
  Overview,
  Priority,
  Run,
  ScenarioResult,
  SkuDetail,
} from './types';

const API_ROOT = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

const FIELD_NAMES: Record<string, string> = {
  note: 'observação', user_name: 'usuário', owner: 'responsável', due_date: 'prazo', analysis_minutes: 'tempo de análise', sku: 'SKU', action: 'ação',
  produto: 'produto', familia: 'família', curva_abc: 'curva ABC', lead_time_dias: 'prazo de produção', lote_minimo: 'lote mínimo',
  estoque_atual: 'estoque atual', estoque_seguranca_dias: 'estoque de segurança', venda_media_dia: 'venda média por dia', email: 'e-mail', password: 'senha',
};

function validationMessage(item: { msg?: string; loc?: unknown[] }) {
  const field = item.loc?.[item.loc.length - 1];
  const name = typeof field === 'string' ? FIELD_NAMES[field] ?? field : null;
  const message = (item.msg ?? 'valor inválido').replace(/^Value error, /, '');
  return name ? `${name} — ${message}` : message;
}

/** Sem token (cadastro liberado, AUTH_REQUIRED=false), nenhum cabeçalho de login é enviado. */
const bearer = (token: string): Record<string, string> => token ? { Authorization: `Bearer ${token}` } : {};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, init);
  } catch (error) {
    if (init?.signal?.aborted) throw error;
    throw new ApiError('Não foi possível conectar ao servidor. Verifique se a API está disponível.');
  }

  if (!response.ok) {
    let detail = `A solicitação falhou (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg?: string; loc?: unknown[] }> };
      if (typeof body.detail === 'string') detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail.length) detail = `Dados inválidos: ${body.detail.map(validationMessage).join('; ')}`;
    } catch {
      // The status code remains useful when the response has no JSON body.
    }
    throw new ApiError(detail, response.status);
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('O servidor retornou uma resposta inválida.', response.status);
  }
}

export async function loadDashboard(): Promise<DashboardData> {
  const [overview, priorities, runs, cases, b2b, config, feedback, quality] = await Promise.all([
    request<Overview>('/overview'),
    request<Priority[]>('/priorities'),
    request<Run[]>('/runs'),
    request<CaseItem[]>('/cases'),
    request<B2BVisibility>('/b2b2c/visibility'),
    request<AppConfig>('/config'),
    request<FeedbackItem[]>('/feedback'),
    request<DataQuality>('/data-quality'),
  ]);
  return { overview, priorities, runs, cases, b2b, config, feedback, quality };
}

export const api = {
  partners: (query: URLSearchParams, signal?: AbortSignal) => request<CommercialPage<PartnerSummary>>(`/partners?${query}`, { signal }),
  partnerDetail: (code: string, signal?: AbortSignal) => request<PartnerDetail>(`/partners/${encodeURIComponent(code)}`, { signal }),
  partnerSkus: (code: string, query: URLSearchParams, signal?: AbortSignal) => request<CommercialPage<CommercialRow>>(`/partners/${encodeURIComponent(code)}/skus?${query}`, { signal }),
  commercialRecommendations: (query: URLSearchParams, signal?: AbortSignal) => request<CommercialPage<CommercialRow>>(`/commercial-recommendations?${query}`, { signal }),
  forecasts: (signal?: AbortSignal) => request<ForecastRecommendationSummary[]>('/forecasts', { signal }),
  directChannels: (signal?: AbortSignal) => request<DirectChannelsOverview>('/direct-channels', { signal }),
  directChannel: (code: string, query: URLSearchParams, signal?: AbortSignal) => request<DirectChannelDetail>(`/direct-channels/${encodeURIComponent(code)}?${query}`, { signal }),
  channelFindings: (signal?: AbortSignal) => request<{ findings: ChannelFinding[] }>('/data-quality/channels', { signal }),
  events: (signal?: AbortSignal) => request<EventAnalysis>('/events', { signal }),
  revenueForecast: (signal?: AbortSignal) => request<RevenueForecast>('/revenue-forecast', { signal }),
  capacityPlan: (signal?: AbortSignal) => request<CapacityPlan>('/capacity-plan', { signal }),
  productionPlan: (signal?: AbortSignal) => request<ProductionPlan>('/production-plan', { signal }),
  skuDetail: (sku: string, signal?: AbortSignal) => request<SkuDetail>(`/priorities/${encodeURIComponent(sku)}`, { signal }),
  system: (signal?: AbortSignal) => request<SystemInfo>('/system', { signal }),
  /** Etapa 16.2: alocação sugerida; filtros opcionais `sku`, `regiao`, `cliente` (sku sem pedido aberto → 404). */
  allocation: (query: URLSearchParams = new URLSearchParams(), signal?: AbortSignal) => request<AllocationResponse>(`/allocation${String(query) ? `?${query}` : ''}`, { signal }),
  allocationRegions: (signal?: AbortSignal) => request<AllocationRegions>('/allocation/regions', { signal }),
  rulesCoverage: (signal?: AbortSignal) => request<RulesCoverage>('/rules/coverage', { signal }),
  validationSummary: (signal?: AbortSignal) => request<ValidationSummary>('/validation/summary', { signal }),
  forecastLab: (signal?: AbortSignal) => request<ForecastLab>('/forecast-lab', { signal }),
  modelBenchmark: (signal?: AbortSignal) => request<ModelBenchmark>('/model-benchmark', { signal }),
  runComparison: (base: number, target: number, signal?: AbortSignal) => request<RunComparison>(`/run-comparisons?${new URLSearchParams({ base: String(base), target: String(target) })}`, { signal }),
  createRun: () => request<{ id: number }>('/runs', { method: 'POST' }),
  createCase: (body: Record<string, unknown>) =>
    request<{ id: number }>('/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  updateCase: (id: number, body: Record<string, unknown>) =>
    request<{ status: string }>(`/cases/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  createFeedback: (body: Record<string, unknown>) =>
    request<{ status: string }>('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  login: (email: string, password: string) =>
    request<LoginResult>('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) }),
  me: (token: string, signal?: AbortSignal) => request<{ user: SessionUser }>('/auth/me', { headers: bearer(token), signal }),
  skuRegistry: (token: string, signal?: AbortSignal) => request<SkuRegistry>('/skus/cadastro', { headers: bearer(token), signal }),
  createSku: (token: string, body: SkuFields & { sku: string }) =>
    request<SkuSaved>('/skus', { method: 'POST', headers: { ...bearer(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  updateSku: (token: string, sku: string, body: SkuFields) =>
    request<SkuSaved>(`/skus/${encodeURIComponent(sku)}`, { method: 'PUT', headers: { ...bearer(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  deleteSku: (token: string, sku: string) => request<SkuSaved>(`/skus/${encodeURIComponent(sku)}/excluir`, { method: 'POST', headers: bearer(token) }),
  reactivateSku: (token: string, sku: string) => request<SkuSaved>(`/skus/${encodeURIComponent(sku)}/reativar`, { method: 'POST', headers: bearer(token) }),
  scenario: (body: Record<string, unknown>) =>
    request<ScenarioResult>('/scenarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
};

/** Typed, route-scoped reads. Legacy loadDashboard remains available, but is not used by the shell. */
export const dashboardReaders = {
  overview: (signal: AbortSignal) => request<Overview>('/overview', { signal }),
  priorities: (signal: AbortSignal) => request<Priority[]>('/priorities', { signal }),
  runs: (signal: AbortSignal) => request<Run[]>('/runs', { signal }),
  cases: (signal: AbortSignal) => request<CaseItem[]>('/cases', { signal }),
  b2b: (signal: AbortSignal) => request<B2BVisibility>('/b2b2c/visibility', { signal }),
  config: (signal: AbortSignal) => request<AppConfig>('/config', { signal }),
  feedback: (signal: AbortSignal) => request<FeedbackItem[]>('/feedback', { signal }),
  quality: (signal: AbortSignal) => request<DataQuality>('/data-quality', { signal }),
};
export async function loadPageData<K extends keyof DashboardData>(keys: readonly K[], signal: AbortSignal): Promise<Pick<DashboardData, K>> {
  const pairs = await Promise.all(keys.map(async key => [key, await dashboardReaders[key](signal)] as const));
  return Object.fromEntries(pairs) as Pick<DashboardData, K>;
}
