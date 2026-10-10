import { Link, useLocation } from 'react-router-dom';
import { Alert, Badge, EmptyState, Hint, SectionCard, Tooltip, confidenceTone } from '../components';
import { displayCurrency, displayPercent, displayPrice, displayUnits, formatMonth } from '../pages/shared';
import { CURRENCY, MonthlyBars } from './MonthlyBars';
import type { MonthBar } from './MonthlyBars';
import type { ObservedRevenue, RevenueForecast, RevenueItem } from '../types-revenue';

/** Barras: faturamento observado (cheias) e estimado (tracejadas). */
export function RevenueTrend({ observed, months, values, label }: { observed: ObservedRevenue; months: string[]; values: number[]; label: string }) {
  const bars: MonthBar[] = [
    ...observed.months.map((month, index) => ({ month, solid: observed.values[index] ?? null, dashed: null })),
    ...months.map((month, index) => ({ month, solid: null, dashed: values[index] ?? null })),
  ];
  const keys = [{ label: 'Observado', dashed: false }, ...(months.length > 0 ? [{ label: 'Estimativa', dashed: true }] : [])];
  // Valores mês a mês também no texto acessível: o eixo e a dica só existem para quem vê.
  return <MonthlyBars bars={bars} keys={keys} label={label} format={CURRENCY} describeValues />;
}

const SIGNED = (ratio: number | null) => ratio === null ? 'Não disponível' : `${ratio >= 0 ? '+' : '−'}${displayPercent(Math.abs(ratio))}`;

/** Cartão da página Faturamento previsto. Camada aditiva: se falhar, mostra o motivo e permite nova tentativa. `family` restringe as linhas de família; o total da empresa permanece como contexto. */
export function RevenueSummaryCard({ data, error, loading, refresh, family = '' }: { data: RevenueForecast | undefined; error: string; loading: boolean; refresh: () => Promise<void>; family?: string }) {
  if (!data && loading) return <SectionCard title="Faturamento estimado" subtitle="Calculando…"><div className="drawer-loading"><span /><span /></div></SectionCard>;
  if (!data) return <Alert tone="warning" title="Faturamento estimado indisponível" action={<button className="secondary-button" onClick={() => void refresh()}>Tentar novamente</button>}>{error || 'Não foi possível carregar a estimativa.'} A fila operacional, a previsão em unidades e as ações seguem válidas.</Alert>;
  const { total, families } = data;
  const rows = [total, ...families.filter((group) => !family || group.label === family)];
  return <SectionCard className="revenue-card" title="Faturamento estimado" subtitle="Unidades previstas × preço vigente, próximos três meses." action={<span className="revenue-card-tag"><Badge tone="info">Estimativa</Badge><Hint term="faturamento_estimado" /></span>}>
    <RevenueTrend observed={total.observed_revenue} months={total.by_month.map((row) => row.month)} values={total.by_month.map((row) => row.revenue)} label={`Faturamento mensal observado e estimado da empresa. Estimativa de ${displayCurrency(total.revenue_total_3m)} em três meses.`} />
    <div className="table-shell" tabIndex={0} role="region" aria-label="Faturamento estimado por família"><table className="data-table responsive-table"><caption className="sr-only">Faturamento estimado por família, em reais; estimativa, não faturamento realizado</caption><thead><tr><th>Escopo</th><th>Estimativa (três meses)</th><th>Variação sobre os três meses anteriores</th><th>Erro do teste</th></tr></thead><tbody>{rows.map((group, index) => {
      const lowConfidence = group.skus_with_estimate - group.confidence_distribution.alta;
      return <tr key={group.label} className={index === 0 ? 'revenue-total-row' : undefined}>
        <td data-label="Escopo"><strong>{group.label}</strong><small>{group.skus_with_estimate} de {group.skus_total} SKUs{group.skus_excluded.length > 0 && <Tooltip label={`SKUs fora da estimativa em ${group.label}`}>{group.skus_excluded.map((row) => `${row.sku} (${row.status === 'sem_preco' ? 'sem preço' : 'sem previsão'})`).join(', ')}. Ausência não é faturamento zero.</Tooltip>}{lowConfidence > 0 && <> · <Badge tone="medium">{lowConfidence} sem confiança alta</Badge></>}</small></td>
        <td data-label="Estimativa"><strong>{displayCurrency(group.revenue_total_3m)}</strong></td>
        <td data-label="Variação">{SIGNED(group.change_vs_last_3m)}</td>
        <td data-label="Erro do teste">{displayPercent(group.backtest_wape)}</td>
      </tr>;
    })}</tbody></table></div>
  </SectionCard>;
}

/** SKUs da estimativa. Sem preço ou sem previsão aparece como motivo, nunca como R$ 0; o detalhe financeiro fica em /skus/:sku?tab=impacto. */
export function RevenueSkuTable({ items }: { items: RevenueItem[] }) {
  const location = useLocation();
  if (!items.length) return <EmptyState title="Nenhum SKU encontrado" description="Ajuste a busca ou a família." />;
  return <div className="table-shell" tabIndex={0} role="region" aria-label="Faturamento estimado por SKU; role horizontalmente para ver todas as colunas"><table className="data-table responsive-table"><caption className="sr-only">Faturamento estimado por SKU, em reais; estimativa, não faturamento realizado</caption><thead><tr><th>SKU / Produto</th><th>Família</th><th>Estimativa (três meses)</th><th>Confiança da previsão</th></tr></thead><tbody>{items.map((item) => <tr key={item.sku}>
    <td data-label="SKU"><Link className="link-button" to={`/skus/${encodeURIComponent(item.sku)}?tab=impacto`} state={{ from: `${location.pathname}${location.search}` }} aria-label={`Ver impacto financeiro de ${item.sku}`}><strong>{item.sku}</strong></Link><small>{item.product}</small></td>
    <td data-label="Família">{item.family}</td>
    <td data-label="Estimativa">{item.status === 'ok' ? <strong>{displayCurrency(item.revenue_total_3m)}</strong> : <><Badge tone="medium">{item.status === 'sem_preco' ? 'Sem preço' : 'Sem previsão'}</Badge> <span className="queue-none">Não disponível</span></>}</td>
    <td data-label="Confiança">{item.status === 'ok' ? <Badge tone={confidenceTone(item.forecast_confidence)}>{item.forecast_confidence}</Badge> : <span className="queue-none">Não disponível</span>}</td>
  </tr>)}</tbody></table></div>;
}

/** Bloco do detalhe do SKU. `undefined` = resposta antiga sem o campo; `null` = estimativa indisponível. */
export function SkuRevenueBlock({ item }: { item: RevenueItem | null | undefined }) {
  if (item === undefined) return null;
  if (item === null) return <details className="detail-block"><summary>Faturamento estimado</summary><p className="fact-line">Estimativa de faturamento indisponível no momento. A previsão em unidades segue válida.</p></details>;
  if (item.status !== 'ok') return <details className="detail-block" open><summary>Faturamento estimado</summary><p className="fact-line"><Badge tone="medium">{item.status === 'sem_preco' ? 'Sem preço' : 'Sem previsão'}</Badge> {item.reason} Não há valor em reais a exibir; ausência não é faturamento zero.</p></details>;
  const calc = item.calculation;
  return <details className="detail-block" open>
    <summary>Faturamento estimado</summary>
    <p className="fact-line">Próximos três meses <strong>{displayCurrency(item.revenue_total_3m)}</strong> <Badge tone="info">Estimativa</Badge><Hint term="faturamento_estimado" /> · confiança da previsão <Badge tone={confidenceTone(item.forecast_confidence)}>{item.forecast_confidence}</Badge> · preço unitário {displayPrice(item.unit_price)} <Badge tone="neutral">Observado</Badge> ({item.price_source})</p>
    {item.price_conflict && <p className="fact-line"><Badge tone="medium">Preço divergente</Badge> {item.reason}</p>}
    <RevenueTrend observed={item.observed_revenue} months={item.forecast_months} values={item.revenue_values} label={`Faturamento mensal de ${item.sku}, observado e estimado. Estimativa de ${displayCurrency(item.revenue_total_3m)} em 3 meses.`} />
    {calc && <div className="table-shell" tabIndex={0} role="region" aria-label="Cálculo do faturamento estimado"><table className="data-table"><caption>{calc.formula}</caption><thead><tr><th>Mês</th><th>Unidades previstas</th><th>Preço unitário</th><th>Faturamento estimado</th></tr></thead><tbody>{calc.terms.map((term) => <tr key={term.month}><td>{formatMonth(term.month)}</td><td>{displayUnits(term.units)}</td><td>{displayPrice(term.unit_price)}</td><td>{displayCurrency(term.revenue)}</td></tr>)}</tbody></table></div>}
    {item.commercial_reference && <p className="fact-line">Forecast comercial da planilha nos mesmos meses (origens: {item.commercial_reference.origins.join(', ')}): <strong>{displayCurrency(item.commercial_reference.commercial_revenue)}</strong> contra {displayCurrency(item.commercial_reference.model_revenue)} do modelo ({displayPercent(item.commercial_reference.difference_ratio)}). {item.commercial_reference.note}</p>}
  </details>;
}
