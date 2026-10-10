import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge, SectionCard } from '../components';
import type { ProjectedStockSummary } from '../types';
import { formatDate } from '../pages/shared';
import { useWidth } from './MonthlyBars';

type Week = NonNullable<ProjectedStockSummary['weekly']>[number];

const HEIGHT = 220;
const shortDate = (value: string) => formatDate(value).slice(0, 5);
const skus = (count: number) => `${count} ${count === 1 ? 'SKU' : 'SKUs'}`;

/** As duas leituras. "Com o plano" é a que importa (azul da ação); "sem novas ordens" é o contexto (grafite). */
const SERIES = [
  { key: 'shortfall_sku_count', label: 'Sem novas ordens', className: 'chart-line-context' },
  { key: 'shortfall_with_plan_sku_count', label: 'Com o plano', className: 'chart-line-focus' },
] as const;

function WeekTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Week }> }) {
  const week = payload?.[0]?.payload;
  if (!active || !week) return null;
  return <div className="chart-tooltip">
    <strong>Semana de {shortDate(week.week_start)}</strong>
    {SERIES.map((series) => <span key={series.key}><i className={`chart-line-key ${series.className}`} />{series.label}: {skus(week[series.key])} em falta</span>)}
  </div>;
}

/**
 * Valor só no fim de cada linha (rótulo seletivo), à direita da ponta, fora da faixa das datas.
 * O plano nunca passa da base: quando os dois fins estão próximos, a base sobe e o plano fica na linha; iguais, um número só.
 */
function endOffsets(weeks: Week[]) {
  const end = weeks[weeks.length - 1];
  const max = Math.max(1, ...weeks.map((week) => week.shortfall_sku_count));
  const base = end.shortfall_sku_count, plan = end.shortfall_with_plan_sku_count;
  if (base === plan) return { base: 4, plan: null };
  return base - plan <= max * 0.12 ? { base: -10, plan: 4 } : { base: 4, plan: 4 };
}

function endLabel(last: number, dy: number | null) {
  return function EndLabel({ x, y, index, value }: { x?: number | string; y?: number | string; index?: number; value?: unknown }) {
    if (dy === null || index !== last || x === undefined || y === undefined || value === undefined) return <g />;
    return <text className="chart-end-label" x={Number(x) + 8} y={Number(y) + dy} textAnchor="start">{String(value)}</text>;
  };
}

/**
 * SKUs em falta por semana no horizonte da previsão, sem novas ordens × com o plano (fase 4, Início).
 * Vem com o /api/overview: sem a série (resposta antiga ou falha da agregação) o bloco não aparece e os números acima seguem.
 */
export function ProjectedStockChart({ summary }: { summary: ProjectedStockSummary | null }) {
  const [ref, width] = useWidth();
  const weeks = summary?.weekly ?? [];
  if (!summary || weeks.length === 0) return null;
  const peak = weeks.reduce((best, week) => (week.shortfall_sku_count > best.shortfall_sku_count ? week : best), weeks[0]);
  const peakPlan = weeks.reduce((best, week) => (week.shortfall_with_plan_sku_count > best.shortfall_with_plan_sku_count ? week : best), weeks[0]);
  const sentence = peak.shortfall_sku_count === 0
    ? 'Nenhum SKU em falta no horizonte, com ou sem novas ordens.'
    : `Pico de ${skus(peak.shortfall_sku_count)} em falta na semana de ${shortDate(peak.week_start)} sem novas ordens; com o plano, o pico é de ${skus(peakPlan.shortfall_with_plan_sku_count)}.`;
  const last = weeks.length - 1;
  const offsets = endOffsets(weeks);
  // Celular: menos datas no eixo para não sobrepor; a dica mostra todas as semanas.
  const minTickGap = width < 480 ? 24 : 12;
  return <SectionCard className="projected-chart-card" title="SKUs em falta por semana" subtitle="Semana a semana, sem novas ordens e com o plano." action={<Badge tone="info">Projeção</Badge>}>
    <figure className="revenue-trend">
      <div ref={ref} className="chart-frame" role="img" aria-label={`SKUs em falta por semana, sem novas ordens e com o plano. ${sentence}`}>
        <LineChart width={width} height={HEIGHT} data={weeks} margin={{ top: 16, right: 36, bottom: 0, left: 0 }} accessibilityLayer={false}>
          <CartesianGrid vertical={false} className="chart-grid" />
          <XAxis dataKey="week_start" tickFormatter={shortDate} tickLine={false} axisLine={{ className: 'chart-axis' }} minTickGap={minTickGap} tick={{ className: 'chart-tick' }} height={28} />
          <YAxis width={40} tickLine={false} axisLine={false} allowDecimals={false} tickCount={4} tick={{ className: 'chart-tick' }} />
          <Tooltip cursor={{ className: 'chart-cursor-line' }} isAnimationActive={false} content={<WeekTooltip />} />
          {SERIES.map((series, index) => <Line key={series.key} type="linear" dataKey={series.key} name={series.label} className={series.className}
            strokeWidth={2} dot={false} activeDot={{ r: 4, className: `chart-dot ${series.className}` }} isAnimationActive={false}
            label={endLabel(last, index === 0 ? offsets.base : offsets.plan)} />)}
        </LineChart>
      </div>
      <figcaption>{SERIES.map((series) => <span key={series.key}><i className={`chart-line-key ${series.className}`} /> {series.label}</span>)}</figcaption>
    </figure>
    <p className="fact-line">{sentence}</p>
  </SectionCard>;
}
