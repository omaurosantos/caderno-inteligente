import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../api';
import { fail, mockApi } from './utils';
import * as fx from './fixtures';
import { endpoints, keyPaths } from './contract';
import contract from './contract-keys.json';

// Same fixtures used by the page tests; tests/test_frontend_contracts.py checks the real API against the same key list.
const FIXTURES: Record<string, unknown> = {
  overview: fx.overview, priorities: fx.priorities, quality: fx.quality, config: fx.config, runs: fx.runs, b2b: fx.b2b,
  forecasts: fx.forecasts, revenueForecast: fx.revenueForecast, capacityPlan: fx.capacityPlan, productionPlan: fx.productionPlan, events: fx.eventAnalysis,
  collaboration: fx.collaboration, directChannels: fx.directChannels, directChannel: fx.directChannelDetail, channelFindings: { findings: fx.channelFindings }, skuDetail: fx.skuDetailOk, partners: fx.partnersPage, partnerDetail: fx.partnerDetail,
  partnerSkus: fx.commercialRowsEtapa16, commercial: fx.commercialRowsEtapa16, validation: fx.validationSummary, forecastLab: fx.forecastLab, modelBenchmark: fx.modelBenchmark, runComparison: fx.runComparison, system: fx.system,
  allocation: fx.allocation, allocationRegions: fx.allocationRegions, rulesCoverage: fx.rulesCoverage,
  // Upload: a prévia aplicável com o erro endereçado da outra prévia cobre errors[] e engine.after no mesmo objeto.
  dataset: fx.datasetOriginal, datasetVersions: fx.datasetVersions, datasetPreview: { ...fx.datasetPreviewOk, errors: fx.datasetPreviewError.errors },
};
/** Campos que só existem depois de um upload (D8). */
const AFTER_UPLOAD: Record<string, unknown> = { validation: fx.validationSummaryPreviousBase };
const listItems = contract.list_items as Record<string, string[]>;
const afterUpload = contract.after_upload as Record<string, string[]>;

describe('contratos críticos do frontend', () => {
  it('todo endpoint do contrato tem fixture e vice-versa', () => {
    expect(Object.keys(FIXTURES).sort()).toEqual(Object.keys(endpoints).sort());
  });

  it.each(Object.entries(endpoints))('%s: fixture contém todos os campos do contrato', (name, endpoint) => {
    const missing = endpoint.keys.filter((key) => !keyPaths(FIXTURES[name]).has(key));
    expect(missing).toEqual([]);
  });

  it.each(Object.entries(listItems))('%s: todo item da fixture tem os campos do contrato', (field, keys) => {
    const [name, ...path] = field.split('.');
    const items = path.reduce<unknown>((value, key) => (value as Record<string, unknown>)[key], FIXTURES[name]) as Array<Record<string, unknown>>;
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) expect(keys.filter((key) => !(key in item))).toEqual([]);
  });

  it.each(Object.entries(afterUpload))('%s depois do upload: fixture contém os campos do contrato', (name, keys) => {
    expect(keys.filter((key) => !keyPaths(AFTER_UPLOAD[name]).has(key))).toEqual([]);
  });

  it('valores ausentes das fixtures permanecem nulos, não zero', () => {
    expect(fx.skuDetailShort.operational_recommendation.suggested_quantity).toBeNull();
    expect(fx.forecasts[1].forecast.forecast_next_month).toBeNull();
    expect(fx.commercialRow.coverage_days).toBeNull();
    expect(fx.allocationNoPrice.uncovered_value_at_promise).toBeNull();
    expect(fx.allocation.totals.uncovered_value).toBeNull();
    expect(fx.valueAtRiskMissing.observed).toBeNull();
    expect(fx.forecasts[1].value_at_risk).toBeNull();
    expect(fx.commercialRowDirect.estimated_stock).toBeNull();
    expect(fx.rulesCoverage.sell_out_requests[1].backlog_value).toBeNull();
    expect(fx.datasetOriginal.uploaded_by).toBeNull();
    expect(fx.datasetPreviewError.engine.after).toBeNull();
    expect(fx.datasetPreviewError.reference.after).toBeNull();
    expect(fx.datasetVersions.items[1].size_bytes).toBeNull();
  });
});

describe('api do upload (corpo bruto, cabeçalhos e 422 com prévia)', () => {
  afterEach(() => vi.unstubAllGlobals());
  const file = new File(['conteúdo'], 'atualização de teste.xlsx');

  it('prévia envia o arquivo bruto com X-Filename codificado e o token', async () => {
    const { calls } = mockApi();
    const outcome = await api.previewDataset('tok', file);
    expect(outcome).toEqual({ status: 200, preview: fx.datasetPreviewOk, detail: null });
    expect(calls[0]).toMatchObject({ method: 'POST', path: '/api/dataset/preview', body: file,
      headers: { Authorization: 'Bearer tok', 'Content-Type': 'application/octet-stream', 'X-Filename': 'atualiza%C3%A7%C3%A3o%20de%20teste.xlsx' } });
  });

  it('422 com prévia resolve com os erros; arquivo recusado lança ApiError com o código', async () => {
    mockApi({ 'POST datasetPreview': fail(422, 'A planilha tem 1 erro que bloqueia a aplicação.', { preview: fx.datasetPreviewError }) });
    expect(await api.previewDataset('tok', file)).toEqual({ status: 422, preview: fx.datasetPreviewError, detail: 'A planilha tem 1 erro que bloqueia a aplicação.' });
    mockApi({ 'POST datasetPreview': fail(422, 'O arquivo não é uma planilha .xlsx ou .xlsm válida.', { code: 'NOT_XLSX' }) });
    await expect(api.previewDataset('tok', file)).rejects.toMatchObject({ name: 'ApiError', status: 422, code: 'NOT_XLSX' });
  });

  it('aplicação manda sha256 e versão da prévia; 409 lança ApiError', async () => {
    const { calls } = mockApi();
    const outcome = await api.applyDataset('tok', file, 'abc', 7);
    expect(outcome).toEqual({ status: 200, result: fx.datasetApplyResult, preview: fx.datasetPreviewOk, detail: null });
    expect(calls[0].headers).toMatchObject({ 'X-Confirm-Sha256': 'abc', 'X-Expected-Version': '7' });
    mockApi({ 'POST datasetApply': fail(409, 'Outra pessoa atualizou a base; refaça a prévia.') });
    await expect(api.applyDataset('tok', file, 'abc', 7)).rejects.toEqual(new ApiError('Outra pessoa atualizou a base; refaça a prévia.', 409));
  });

  it('base ativa, versões, restaurações e modelo', async () => {
    const { calls } = mockApi();
    expect(await api.dataset('tok')).toEqual(fx.datasetOriginal);
    expect(await api.datasetVersions()).toEqual(fx.datasetVersions);
    expect((await api.restoreDatasetVersion('tok', 1, 5)).restored_from).toBe(1);
    expect((await api.restoreOriginalDataset('tok', 5)).reference_date).toBe('2026-09-14');
    const template = await api.downloadDatasetTemplate();
    expect(template.filename).toBe('modelo-caderno-inteligente-2026-09-14.xlsx');
    expect(template.blob.size).toBeGreaterThan(0);
    expect(calls.map((call) => `${call.method} ${call.path}`)).toEqual([
      'GET /api/dataset', 'GET /api/dataset/versions', 'POST /api/dataset/versions/1/restore', 'POST /api/dataset/restore-original', 'GET /api/dataset/template']);
    expect(calls[0].headers).toEqual({ Authorization: 'Bearer tok' });
    expect(calls[2].headers['X-Expected-Version']).toBe('5');
    expect(calls[3].headers['X-Expected-Version']).toBe('5');
  });
});
