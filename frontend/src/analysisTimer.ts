/**
 * Etapa 16.7: tempo de análise medido no navegador, do abrir o detalhe do SKU até registrar a decisão.
 * O início fica em `sessionStorage` (só nesta aba); sem armazenamento, vale a memória desta tela. Nada vai ao servidor
 * além do `analysis_minutes` que o formulário de decisão já envia.
 */
const PREFIX = 'caderno-inteligente.analise.';
const memory = new Map<string, number>();

function storage(): Storage | null {
  try { return window.sessionStorage ?? null; } catch { return null; }
}

function readStart(sku: string): number | null {
  let raw: string | null = null;
  try { raw = storage()?.getItem(PREFIX + sku) ?? null; } catch { /* sem armazenamento: usa a memória */ }
  const value = raw === null ? memory.get(sku) ?? null : Number(raw);
  return value !== null && Number.isFinite(value) ? value : null;
}

/** Grava o início ao abrir o SKU. Mantém o primeiro início até a decisão: ir e voltar entre telas continua contando. */
export function startAnalysis(sku: string, now: number = Date.now()) {
  if (!sku || readStart(sku) !== null) return;
  memory.set(sku, now);
  try { storage()?.setItem(PREFIX + sku, String(now)); } catch { /* sem armazenamento: a memória basta nesta tela */ }
}

/** Minutos desde que o SKU foi aberto (mínimo 1, teto `limit`); `null` quando o SKU não foi aberto nesta aba. */
export function elapsedMinutes(sku: string, now: number = Date.now(), limit = 1440): number | null {
  const start = sku ? readStart(sku) : null;
  if (start === null || now < start) return null;
  return Math.min(limit, Math.max(1, Math.round((now - start) / 60_000)));
}

/** Depois de registrar a decisão, a próxima análise do SKU começa do zero. */
export function clearAnalysis(sku: string) {
  memory.delete(sku);
  try { storage()?.removeItem(PREFIX + sku); } catch { /* nada a limpar */ }
}
