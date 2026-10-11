import { describe, expect, it } from 'vitest';
import * as fx from './fixtures';
import { endpoints, keyPaths } from './contract';

// Same fixtures used by the page tests; tests/test_frontend_contracts.py checks the real API against the same key list.
const FIXTURES: Record<string, unknown> = {
  overview: fx.overview, priorities: fx.priorities, quality: fx.quality, config: fx.config, runs: fx.runs, b2b: fx.b2b,
  forecasts: fx.forecasts, revenueForecast: fx.revenueForecast, capacityPlan: fx.capacityPlan, productionPlan: fx.productionPlan, events: fx.eventAnalysis,
  directChannels: fx.directChannels, directChannel: fx.directChannelDetail, channelFindings: { findings: fx.channelFindings }, skuDetail: fx.skuDetailOk, partners: fx.partnersPage, partnerDetail: fx.partnerDetail,
  partnerSkus: fx.commercialRowsEtapa16, commercial: fx.commercialRowsEtapa16, validation: fx.validationSummary, forecastLab: fx.forecastLab, modelBenchmark: fx.modelBenchmark, runComparison: fx.runComparison, system: fx.system,
  allocation: fx.allocation, allocationRegions: fx.allocationRegions, rulesCoverage: fx.rulesCoverage,
};

describe('contratos críticos do frontend', () => {
  it('todo endpoint do contrato tem fixture e vice-versa', () => {
    expect(Object.keys(FIXTURES).sort()).toEqual(Object.keys(endpoints).sort());
  });

  it.each(Object.entries(endpoints))('%s: fixture contém todos os campos do contrato', (name, endpoint) => {
    const missing = endpoint.keys.filter((key) => !keyPaths(FIXTURES[name]).has(key));
    expect(missing).toEqual([]);
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
  });
});
