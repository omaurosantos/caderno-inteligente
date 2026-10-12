import type { AllocationRegions, AllocationResponse } from './types-allocation';
import type { CommercialPage, CommercialRow, PartnerDetail, PartnerSummary } from './types-commercial';
import type { CollaborationOverview } from './types-collaboration';
import type { ChannelFinding, DirectChannelDetail, DirectChannelsOverview } from './types-channels';
import type { DatasetApplyOutcome, DatasetApplyResult, DatasetInfo, DatasetPreview, DatasetPreviewOutcome, DatasetVersions } from './types-dataset';
import type { EventAnalysis } from './types-events';
import type { ForecastLab } from './types-forecast-lab';
import type { ModelBenchmark } from './types-model-benchmark';
import type { ProductionPlan } from './types-production';
import { endSession, readSession } from './session';
import type { AppUser, LoginResult, SessionUser, SkuFields, SkuRegistry, SkuSaved } from './types-registry';
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
  /** `code`: código de recusa do servidor quando houver (ex.: FILE_TOO_LARGE, NOT_XLSX, CONFIRM_MISMATCH no upload). */
  constructor(message: string, readonly status?: number, readonly code?: string) {
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

type ErrorBody = { detail?: string | Array<{ msg?: string; loc?: unknown[] }>; code?: string; preview?: DatasetPreview };

/** Toda chamada leva o token da sessão; um 401 (fora do próprio login) encerra a sessão e o app volta para a tela de login. */
async function send(path: string, init?: RequestInit): Promise<Response> {
  const token = readSession()?.token;
  const headers = init?.headers as Record<string, string> | undefined;
  const signed: RequestInit | undefined = token && !headers?.Authorization ? { ...init, headers: { ...headers, ...bearer(token) } } : init;
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, signed);
  } catch (error) {
    if (init?.signal?.aborted) throw error;
    throw new ApiError('Não foi possível conectar ao servidor. Verifique se a API está disponível.');
  }
  if (response.status === 401 && path !== '/auth/login') endSession();
  return response;
}

function errorFrom(status: number, body: ErrorBody | null): ApiError {
  let detail = `A solicitação falhou (${status}).`;
  if (typeof body?.detail === 'string') detail = body.detail;
  else if (Array.isArray(body?.detail) && body.detail.length) detail = `Dados inválidos: ${body.detail.map(validationMessage).join('; ')}`;
  return new ApiError(detail, status, typeof body?.code === 'string' ? body.code : undefined);
}

async function errorBody(response: Response): Promise<ErrorBody | null> {
  try {
    return (await response.json()) as ErrorBody;
  } catch {
    return null; // The status code remains useful when the response has no JSON body.
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (!response.ok) throw errorFrom(response.status, await errorBody(response));

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError('O servidor retornou uma resposta inválida.', response.status);
  }
}

/**
 * Prévia e aplicação do upload: o 422 com `preview` (erro de dado na planilha) resolve em vez de lançar, para a tela listar os erros.
 * Arquivo recusado (413/422 com `code`), 401, 403, 409 e falhas de rede continuam lançando `ApiError`.
 */
async function upload<T>(path: string, init: RequestInit): Promise<{ status: number; body: T | null; preview: DatasetPreview | null; detail: string | null }> {
  const response = await send(path, init);
  if (response.ok) {
    try {
      return { status: response.status, body: (await response.json()) as T, preview: null, detail: null };
    } catch {
      throw new ApiError('O servidor retornou uma resposta inválida.', response.status);
    }
  }
  const body = await errorBody(response);
  if (response.status === 422 && body?.preview) return { status: 422, body: null, preview: body.preview, detail: errorFrom(422, body).message };
  throw errorFrom(response.status, body);
}

/** Corpo bruto do arquivo; o nome vai em X-Filename codificado (cabeçalho HTTP só aceita ASCII). */
const fileInit = (token: string, file: File, headers: Record<string, string> = {}): RequestInit => ({
  method: 'POST',
  headers: { ...bearer(token), 'Content-Type': 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name), ...headers },
  body: file,
});

/** Modelo .xlsx (base ativa, 13 abas) e exemplo fictício: baixados com fetch, porque um link simples não leva o login. */
export const DATASET_TEMPLATE_PATH = '/dataset/template';
export const DATASET_EXAMPLE_PATH = '/dataset/example';

export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const response = await send(path);
  if (!response.ok) throw errorFrom(response.status, await errorBody(response));
  const named = /filename="?([^";]+)"?/.exec(response.headers.get('Content-Disposition') ?? '');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = named?.[1] ?? fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function previewDataset(token: string, file: File): Promise<DatasetPreviewOutcome> {
  const outcome = await upload<DatasetPreview>('/dataset/preview', fileInit(token, file));
  return { status: outcome.status, preview: (outcome.body ?? outcome.preview) as DatasetPreview, detail: outcome.detail };
}

/** `sha256` e `expectedVersion` vêm da prévia (`preview.file.sha256`, `preview.expected_version`): outro arquivo → 422 CONFIRM_MISMATCH; base alterada → 409. */
export async function applyDataset(token: string, file: File, sha256: string, expectedVersion: number): Promise<DatasetApplyOutcome> {
  const outcome = await upload<DatasetApplyResult>('/dataset/apply', fileInit(token, file, { 'X-Confirm-Sha256': sha256, 'X-Expected-Version': String(expectedVersion) }));
  return { status: outcome.status, result: outcome.body, preview: (outcome.body?.preview ?? outcome.preview) as DatasetPreview, detail: outcome.detail };
}

/** `expectedVersion` é a versão ativa que a tela mostra (X-Expected-Version); outra pessoa ter mudado a base vira 409. */
export const restoreDatasetVersion = (token: string, id: number, expectedVersion: number) =>
  request<DatasetApplyResult>(`/dataset/versions/${encodeURIComponent(String(id))}/restore`, { method: 'POST', headers: { ...bearer(token), 'X-Expected-Version': String(expectedVersion) } });

export const restoreOriginalDataset = (token: string, expectedVersion: number) =>
  request<DatasetApplyResult>('/dataset/restore-original', { method: 'POST', headers: { ...bearer(token), 'X-Expected-Version': String(expectedVersion) } });

/** Baixa o modelo; o nome sai do Content-Disposition (modelo-caderno-inteligente-AAAA-MM-DD.xlsx). */
export async function downloadDatasetTemplate(signal?: AbortSignal): Promise<{ blob: Blob; filename: string }> {
  const response = await send('/dataset/template', { signal });
  if (!response.ok) throw errorFrom(response.status, await errorBody(response));
  const match = /filename="?([^";]+)"?/i.exec(response.headers.get('Content-Disposition') ?? '');
  return { blob: await response.blob(), filename: match?.[1] ?? 'modelo-caderno-inteligente.xlsx' };
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
  collaboration: (signal?: AbortSignal) => request<CollaborationOverview>('/collaboration', { signal }),
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
  /** Upload: base ativa; com token, `upload_enabled` reflete o login (sem token o motivo pode ser "login"). */
  dataset: (token?: string, signal?: AbortSignal) => request<DatasetInfo>('/dataset', { headers: bearer(token ?? ''), signal }),
  datasetVersions: (signal?: AbortSignal) => request<DatasetVersions>('/dataset/versions', { signal }),
  previewDataset,
  applyDataset,
  restoreDatasetVersion,
  restoreOriginalDataset,
  downloadDatasetTemplate,
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
  users: (token: string, signal?: AbortSignal) => request<{ items: AppUser[] }>('/users', { headers: bearer(token), signal }),
  createUser: (token: string, body: { email: string; name: string; password: string }) =>
    request<{ email: string; name: string }>('/users', { method: 'POST', headers: { ...bearer(token), 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
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
