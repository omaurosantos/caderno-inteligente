import { render } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { vi } from 'vitest';
import App from '../App';
import * as fx from './fixtures';

/** `body`: campos extras no JSON de erro (ex.: `{ preview }` no 422 da prévia de upload, `{ code }` no arquivo recusado). */
export interface Failure { __failure: true; status: number; detail: string; body?: Record<string, unknown> }
export const fail = (status: number, detail: string, body?: Record<string, unknown>): Failure => ({ __failure: true, status, detail, body });
/** A response that never resolves, to observe loading states. */
export const pending = () => new Promise<never>(() => {});

type Value = unknown | ((url: URL, init?: RequestInit) => unknown);

const ROUTES: Array<[string, RegExp]> = [
  ['users', /^\/api\/users$/],
  ['datasetVersionRestore', /^\/api\/dataset\/versions\/\d+\/restore$/],
  ['datasetVersions', /^\/api\/dataset\/versions$/],
  ['datasetPreview', /^\/api\/dataset\/preview$/],
  ['datasetApply', /^\/api\/dataset\/apply$/],
  ['datasetRestoreOriginal', /^\/api\/dataset\/restore-original$/],
  ['datasetTemplate', /^\/api\/dataset\/template$/],
  ['datasetExample', /^\/api\/dataset\/example$/],
  ['dataset', /^\/api\/dataset$/],
  ['validation', /^\/api\/validation\/summary$/],
  ['forecastLab', /^\/api\/forecast-lab$/],
  ['modelBenchmark', /^\/api\/model-benchmark$/],
  ['runComparison', /^\/api\/run-comparisons$/],
  ['partnerSkus', /^\/api\/partners\/[^/]+\/skus$/],
  ['partnerDetail', /^\/api\/partners\/[^/]+$/],
  ['partners', /^\/api\/partners$/],
  ['commercial', /^\/api\/commercial-recommendations$/],
  ['allocationRegions', /^\/api\/allocation\/regions$/],
  ['allocation', /^\/api\/allocation$/],
  ['rulesCoverage', /^\/api\/rules\/coverage$/],
  ['skuDetail', /^\/api\/priorities\/.+$/],
  ['priorities', /^\/api\/priorities$/],
  ['overview', /^\/api\/overview$/],
  ['forecasts', /^\/api\/forecasts$/],
  ['revenueForecast', /^\/api\/revenue-forecast$/],
  ['capacityPlan', /^\/api\/capacity-plan$/],
  ['productionPlan', /^\/api\/production-plan$/],
  ['events', /^\/api\/events$/],
  ['collaboration', /^\/api\/collaboration$/],
  ['directChannel', /^\/api\/direct-channels\/[^/]+$/],
  ['directChannels', /^\/api\/direct-channels$/],
  ['channelFindings', /^\/api\/data-quality\/channels$/],
  ['runs', /^\/api\/runs$/],
  ['case', /^\/api\/cases\/\d+$/],
  ['cases', /^\/api\/cases$/],
  ['feedback', /^\/api\/feedback$/],
  ['config', /^\/api\/config$/],
  ['quality', /^\/api\/data-quality$/],
  ['b2b', /^\/api\/b2b2c\/visibility$/],
  ['scenario', /^\/api\/scenarios$/],
  ['system', /^\/api\/system$/],
  ['login', /^\/api\/auth\/login$/],
  ['me', /^\/api\/auth\/me$/],
  ['skuRegistry', /^\/api\/skus\/cadastro$/],
  ['skuAction', /^\/api\/skus\/[^/]+\/(excluir|reativar)$/],
  ['sku', /^\/api\/skus\/[^/]+$/],
  ['skus', /^\/api\/skus$/],
];

const DEFAULTS: Record<string, Value> = {
  allocation: fx.allocation, allocationRegions: fx.allocationRegions, rulesCoverage: fx.rulesCoverage,
  validation: fx.validationSummary, forecastLab: fx.forecastLab, modelBenchmark: fx.modelBenchmark, runComparison: fx.runComparison, partnerSkus: fx.partnerRows, partnerDetail: fx.partnerDetail,
  partners: fx.partnersPage, commercial: fx.partnerRows, priorities: fx.priorities, overview: fx.overview, forecasts: fx.forecasts, revenueForecast: fx.revenueForecast, capacityPlan: fx.capacityPlan, productionPlan: fx.productionPlan, events: fx.eventAnalysis,
  collaboration: fx.collaboration, directChannels: fx.directChannels, directChannel: fx.directChannelDetail, channelFindings: { findings: fx.channelFindings },
  runs: fx.runs, system: fx.system, cases: fx.cases, feedback: fx.feedback, config: fx.config, quality: fx.quality, b2b: fx.b2b,
  skuDetail: (url: URL) => decodeURIComponent(url.pathname.split('/').pop() ?? '') === fx.SKU_SHORT ? fx.skuDetailShort : fx.skuDetailOk,
  skuRegistry: fx.skuRegistry, me: { user: fx.sessionUser },
  'POST login': { token: 'token-sintetico', expires_at: 4_102_444_800, user: fx.sessionUser },
  'POST skus': (_url: URL, init?: RequestInit) => ({ sku: String(JSON.parse(String(init?.body)).sku), version: 2 }),
  'PUT sku': (url: URL) => ({ sku: decodeURIComponent(url.pathname.split('/').pop() ?? ''), version: 2 }),
  // Sem .at(): o tsconfig usa lib ES2020, e .at() só passava localmente por tipos de outros pacotes.
  'POST skuAction': (url: URL) => { const parts = url.pathname.split('/'); return { sku: decodeURIComponent(parts[parts.length - 2] ?? ''), version: 2 }; },
  users: { items: [] }, 'POST users': { email: 'novo@exemplo.test', name: 'Novo' },
  dataset: fx.datasetOriginal, datasetVersions: fx.datasetVersions,
  datasetExample: () => new Response(new Blob(['exemplo sintético']), { headers: { 'Content-Disposition': 'attachment; filename="atualizacao-2026-10.xlsx"' } }),
  datasetTemplate: () => new Response(new Blob(['modelo sintético']), { headers: { 'Content-Disposition': 'attachment; filename="modelo-caderno-inteligente-2026-09-14.xlsx"' } }),
  'POST datasetPreview': fx.datasetPreviewOk, 'POST datasetApply': fx.datasetApplyResult,
  'POST datasetVersionRestore': (url: URL) => ({ ...fx.datasetApplyResult, version: 3, version_id: 3, restored_from: Number(url.pathname.split('/')[4]) }),
  'POST datasetRestoreOriginal': { ...fx.datasetApplyResult, version: 3, version_id: 3, reference_date: '2026-09-14', sales_last_month: '2026-08', content_sha256: fx.datasetOriginal.content_sha256, restored_from: null },
  'POST runs': { id: 3 }, 'PUT case': { status: 'updated' }, 'POST cases': { id: 1 }, 'POST feedback': { status: 'created' },
  'POST scenario': { is_simulation: true, warning: 'Cenário hipotético.', weights: fx.config.weights, thresholds: fx.config.thresholds, ranking: fx.priorities },
};

export interface ApiCall { method: string; path: string; body: unknown; headers: Record<string, string> }

/** Routes fetch to synthetic fixtures by endpoint; override a key with a value, Failure, pending() or function. */
export function mockApi(overrides: Record<string, Value> = {}) {
  const calls: ApiCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost');
    const method = (init?.method ?? 'GET').toUpperCase();
    // Corpo JSON vira objeto; corpo bruto (File do upload) fica como veio.
    calls.push({ method, path: `${url.pathname}${url.search}`, body: typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body ?? undefined, headers: { ...(init?.headers as Record<string, string> | undefined) } });
    const name = ROUTES.find(([, pattern]) => pattern.test(url.pathname))?.[0];
    if (!name) return { ok: false, status: 404, json: async () => ({ detail: `Rota não simulada: ${url.pathname}` }) };
    const key = method === 'GET' ? name : `${method} ${name}`;
    const entry = key in overrides ? overrides[key] : DEFAULTS[key];
    const value = typeof entry === 'function' ? await (entry as (url: URL, init?: RequestInit) => unknown)(url, init) : await entry;
    if (value && typeof value === 'object' && '__failure' in value) {
      const failure = value as Failure;
      return { ok: false, status: failure.status, json: async () => ({ ...structuredClone(failure.body), detail: failure.detail }) };
    }
    if (value instanceof Response) return value; // download (blob + cabeçalhos)
    return { ok: true, status: 200, json: async () => structuredClone(value) };
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock, gets: () => calls.filter((call) => call.method === 'GET').map((call) => call.path) };
}

function LocationProbe() {
  const location = useLocation();
  return <output hidden data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

export const currentLocation = () => document.querySelector('[data-testid="location"]')?.textContent ?? '';

const SESSION_KEY = 'caderno-inteligente.sessao';
/** O app só abre depois do login: por padrão os testes já entram (token-padrao); `{ signedIn: false }` mostra a tela de login. */
export function renderApp(path = '/', { signedIn = true }: { signedIn?: boolean } = {}) {
  if (signedIn && !window.localStorage.getItem(SESSION_KEY)) window.localStorage.setItem(SESSION_KEY, JSON.stringify({ token: 'token-padrao', expiresAt: 4_102_444_800, user: fx.sessionUser }));
  return render(<MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /><LocationProbe /></MemoryRouter>);
}
