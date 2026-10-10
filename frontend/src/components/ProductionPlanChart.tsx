import { Alert, Badge, Hint, SectionCard, Tooltip } from '../components';
import { displayUnits, formatMonth } from '../pages/shared';
import type { ProductionPlan } from '../types-production';
import { MonthlyBars } from './MonthlyBars';

const KEYS = [{ label: 'Liberar agora', dashed: false }, { label: 'Liberar depois', dashed: true }];

/**
 * Produção planejada por mês de liberação, no total ou na família filtrada da fila.
 * Camada aditiva: carrega à parte e, se falhar, a fila continua. Plano sugerido, não ordem liberada; a capacidade fica no botão da página.
 */
export function ProductionPlanChart({ data, error, loading, refresh, family = '', totals = true }: { data: ProductionPlan | undefined; error: string; loading: boolean; refresh: () => Promise<void>; family?: string; /** false no Início: os totais já estão nos indicadores logo acima. */ totals?: boolean }) {
  if (!data && loading) return <SectionCard title="Produção planejada por mês" subtitle="Calculando…"><div className="drawer-loading"><span /><span /></div></SectionCard>;
  if (!data) return <Alert tone="warning" title="Produção planejada indisponível" action={<button className="secondary-button" onClick={() => void refresh()}>Tentar novamente</button>}>{error || 'Não foi possível carregar o plano.'} A fila, as ações e as quantidades seguem válidas.</Alert>;

  const block = family ? data.families.find((item) => item.family === family) : data.total;
  const scope = family || 'Empresa';
  const tag = <span className="revenue-card-tag"><Badge tone="info">Plano sugerido</Badge><Hint term="producao_planejada" /></span>;
  if (!block || block.months.length === 0) {
    return <SectionCard title="Produção planejada por mês" action={tag}><p className="fact-line">Sem ordens planejadas para {scope} no horizonte da previsão.</p></SectionCard>;
  }

  const bars = block.months.map((row) => ({ month: row.month, solid: row.urgent > 0 ? row.urgent : null, dashed: row.later > 0 ? row.later : null }));
  const byMonth = block.months.map((row) => `${formatMonth(row.month)}: ${displayUnits(row.urgent + row.later)}${row.urgent > 0 ? ` (${displayUnits(row.urgent)} agora)` : ''}`).join('; ');
  // Só o nome do mês, como no eixo: num horizonte de 6 meses não há ambiguidade, e o ano viraria mais um número na tela.
  const omitted = data.omitted_months.map((month) => formatMonth(month).split('/')[0]).join(', ');
  const excluded = data.excluded_skus.length;
  return <SectionCard className="production-plan-card" title="Produção planejada por mês" action={tag}>
    <MonthlyBars bars={bars} keys={KEYS} label={`Unidades a liberar para produção por mês, ${scope}. ${byMonth}. Plano sugerido, não ordem liberada.`} />
    {totals ? <p className="fact-line">
      <strong>{displayUnits(block.urgent_total)}</strong> para liberar agora · {displayUnits(block.horizon_total)} no horizonte
      <Tooltip label="Unidades por mês de liberação">{byMonth}.{omitted && ` ${omitted} fora do gráfico: o prazo de produção passa do fim da previsão.`}{excluded > 0 && ` ${excluded} SKU${excluded > 1 ? 's' : ''} sem previsão fora da soma.`}</Tooltip>
      {omitted && <> · {omitted} fora do gráfico</>}
    </p> : omitted && <p className="fact-line">{omitted} fora do gráfico: o prazo de produção passa do fim da previsão.</p>}
  </SectionCard>;
}
