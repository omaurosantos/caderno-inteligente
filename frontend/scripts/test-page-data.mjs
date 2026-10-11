// Uses only Node and the existing TypeScript dependency; no DOM or new packages.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import ts from 'typescript';

const options = { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } };
const dataUrl = (code) => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
// api.ts importa a sessão de login; uma URL data: não resolve import relativo, então a sessão vai compilada à parte.
const session = ts.transpileModule(await readFile(new URL('../src/session.ts', import.meta.url), 'utf8'), options).outputText;
const source = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source.replace('import.meta.env.VITE_API_URL', 'undefined'), options).outputText
  .replaceAll("'./session'", JSON.stringify(dataUrl(session)));
const { loadPageData, api } = await import(dataUrl(compiled));

async function mockedFetch(handler, run) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  try { await run(); } finally { globalThis.fetch = original; }
}
const ok = (body) => ({ ok: true, json: async () => body });

test('overview reads only its dependencies despite unavailable persistence endpoints', async () => {
  const calls = [];
  await mockedFetch(async (url) => {
    calls.push(url);
    if (['/api/feedback', '/api/runs', '/api/cases'].includes(url)) throw Error('offline');
    return ok({ endpoint: url });
  }, async () => {
    const result = await loadPageData(['overview', 'priorities', 'quality'], new AbortController().signal);
    assert.deepEqual(Object.keys(result), ['overview', 'priorities', 'quality']);
    assert.deepEqual(calls, ['/api/overview', '/api/priorities', '/api/data-quality']);
  });
});
test('single-page query does not load dashboard, forecasts or detail', async () => {
  const calls = [];
  await mockedFetch(async (url) => { calls.push(url); return ok([]); }, async () => {
    assert.deepEqual(await loadPageData(['runs'], new AbortController().signal), { runs: [] });
    assert.deepEqual(calls, ['/api/runs']);
  });
});
test('HTTP errors keep detail and allow a later retry', async () => {
  let failed = true;
  await mockedFetch(async () => failed ? { ok: false, status: 503, json: async () => ({ detail: 'Execuções indisponíveis' }) } : ok([]), async () => {
    await assert.rejects(loadPageData(['runs'], new AbortController().signal), { message: 'Execuções indisponíveis', status: 503 });
    failed = false;
    assert.deepEqual(await loadPageData(['runs'], new AbortController().signal), { runs: [] });
  });
});
test('route reads forward AbortSignal and preserve abort rather than a network error', async () => {
  const controller = new AbortController();
  await mockedFetch((_url, { signal }) => new Promise((_resolve, reject) => {
    assert.equal(signal, controller.signal);
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }), async () => {
    const pending = loadPageData(['priorities'], controller.signal);
    controller.abort();
    await assert.rejects(pending, { name: 'AbortError' });
  });
});
test('forecasts and SKU detail remain dedicated reads with encoded SKU', async () => {
  const calls = [];
  const signal = new AbortController().signal;
  await mockedFetch(async (url, init) => { calls.push(url); assert.equal(init.signal, signal); return ok({}); }, async () => {
    await api.forecasts(signal);
    await api.skuDetail('SKU / 1', signal);
    assert.deepEqual(calls, ['/api/forecasts', '/api/priorities/SKU%20%2F%201']);
  });
});
test('validation summary is a dedicated read that does not load the dashboard', async () => {
  const calls = [];
  const signal = new AbortController().signal;
  await mockedFetch(async (url, init) => { calls.push(url); assert.equal(init.signal, signal); return ok({}); }, async () => {
    await api.validationSummary(signal);
    assert.deepEqual(calls, ['/api/validation/summary']);
  });
});
test('run comparison is a dedicated read with explicit base and target', async () => {
  const calls = [];
  const signal = new AbortController().signal;
  await mockedFetch(async (url, init) => { calls.push(url); assert.equal(init.signal, signal); return ok({}); }, async () => {
    await api.runComparison(3, 7, signal);
    assert.deepEqual(calls, ['/api/run-comparisons?base=3&target=7']);
  });
});
