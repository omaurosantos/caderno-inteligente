import { useLayoutEffect, useRef, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts';
import { formatMonth } from '../pages/shared';

/** Uma barra por mês: parte cheia embaixo e tracejada em cima. `null` = parte sem valor (não desenhada); um número, mesmo zero, desenha ao menos 1 px. */
export interface MonthBar { month: string; solid: number | null; dashed: number | null }
export interface BarKey { label: string; dashed: boolean }
/** Como escrever um valor: `axis` curto para o eixo Y (R$ 1,2 mi), `full` para a dica e o texto acessível. */
export interface ValueFormat { axis: (value: number) => string; full: (value: number) => string }

const ptCompact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });
const ptCompactCurrency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1 });
const ptInteger = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const ptCurrency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });

export const UNITS: ValueFormat = { axis: (value) => ptCompact.format(value), full: (value) => `${ptInteger.format(value)} un.` };
export const CURRENCY: ValueFormat = { axis: (value) => ptCompactCurrency.format(value), full: (value) => ptCurrency.format(value) };

const HEIGHT = 220;
const FALLBACK_WIDTH = 560; // sem medida (testes em jsdom, primeiro quadro): desenha com uma largura fixa.
const MARGIN = { top: 8, right: 8, bottom: 0, left: 0 };

/** Largura do contêiner, acompanhando redimensionamentos. Sem ResizeObserver, mede uma vez. Usado por todos os gráficos. */
export function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setWidth(Math.floor(element.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width || FALLBACK_WIDTH] as const;
}

type Row = MonthBar & { solidValue: number | null; dashedValue: number | null };

/** Retângulo com só o topo arredondado (4 px), reto na base. O topo é a parte tracejada quando existe. */
function Segment(props: { x?: number; y?: number; width?: number; height?: number; payload?: Row; className: string; field: 'solid' | 'dashed'; top: (row: Row) => boolean }) {
  const { x = 0, y = 0, width = 0, height = 0, payload, className, field, top } = props;
  // Parte sem valor (null) não é desenhada, nem com o mínimo de 1 px: ausência nunca vira zero.
  if (!payload || payload[field] === null || height <= 0 || width <= 0) return null;
  const r = payload && top(payload) ? Math.min(4, width / 2, height) : 0;
  const d = `M${x},${y + height} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + width - r},${y} Q${x + width},${y} ${x + width},${y + r} L${x + width},${y + height} Z`;
  return <path className={className} d={d} />;
}

/** Eixo X: mês abreviado; o ano aparece embaixo no primeiro mês e em janeiro, para não repetir em toda barra. */
function MonthTick({ x = 0, y = 0, payload, months }: { x?: number; y?: number; payload?: { value: string }; months: string[] }) {
  if (!payload) return null;
  const [name, year] = formatMonth(payload.value).split('/');
  const showYear = months.indexOf(payload.value) === 0 || payload.value.slice(5, 7) === '01';
  return <text className="chart-tick" x={x} y={y + 12} textAnchor="middle">
    <tspan x={x}>{name}</tspan>
    {showYear && <tspan x={x} dy="1.25em" className="chart-tick-year">{`20${year}`}</tspan>}
  </text>;
}

function ChartTooltip({ active, payload, keys, format }: { active?: boolean; payload?: Array<{ payload: Row }>; keys: BarKey[]; format: ValueFormat }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  const parts = keys.map((key) => ({ key, value: key.dashed ? row.dashed : row.solid })).filter((part) => part.value !== null);
  return <div className="chart-tooltip">
    <strong>{formatMonth(row.month)}</strong>
    {parts.map(({ key, value }) => <span key={key.label}><i className={key.dashed ? 'revenue-key revenue-key-estimated' : 'revenue-key'} />{key.label}: {format.full(value as number)}</span>)}
  </div>;
}

/**
 * Barras mensais (cheias × tracejadas), usadas no faturamento e na produção planejada, com valores nos eixos.
 * A legenda e o texto acessível evitam depender só da cor; a dica (hover) mostra o valor exato do mês.
 */
export function MonthlyBars({ bars, keys, label, format = UNITS, describeValues = false }: { bars: MonthBar[]; keys: BarKey[]; label: string; format?: ValueFormat; describeValues?: boolean }) {
  const [ref, width] = useWidth();
  // Zero ganha 1 px (minPointSize), como antes; a parte nula é descartada no Segment.
  const data: Row[] = bars.map((bar) => ({ ...bar, solidValue: bar.solid, dashedValue: bar.dashed }));
  const months = bars.map((bar) => bar.month);
  // Celular com muitos meses: rótulo a cada 2 (ou mais) meses para os nomes não se sobreporem; a dica mostra todos.
  const slot = (width - 72) / Math.max(1, bars.length);
  const step = Math.max(1, Math.ceil(36 / slot));
  const values = describeValues ? ` ${bars.map((bar) => `${formatMonth(bar.month)}: ${format.full((bar.solid ?? 0) + (bar.dashed ?? 0))}${bar.dashed !== null && bar.solid === null ? ' (estimado)' : ''}`).join('; ')}.` : '';
  return <figure className="revenue-trend">
    <div ref={ref} className="chart-frame" role="img" aria-label={`${label}${values}`}>
      <BarChart width={width} height={HEIGHT} data={data} margin={MARGIN} barCategoryGap="28%" accessibilityLayer={false}>
        <CartesianGrid vertical={false} className="chart-grid" />
        <XAxis dataKey="month" interval={step - 1} tickLine={false} axisLine={{ className: 'chart-axis' }} height={40} tick={<MonthTick months={months} />} />
        <YAxis width={72} tickLine={false} axisLine={false} tickCount={4} allowDecimals={false} tickFormatter={format.axis} tick={{ className: 'chart-tick' }} />
        <Tooltip cursor={{ className: 'chart-cursor' }} isAnimationActive={false} content={<ChartTooltip keys={keys} format={format} />} />
        <Bar dataKey="solidValue" stackId="month" maxBarSize={28} minPointSize={1} isAnimationActive={false}
          shape={(props: object) => <Segment {...props} className="revenue-bar" field="solid" top={(row) => row.dashed === null} />} />
        <Bar dataKey="dashedValue" stackId="month" maxBarSize={28} minPointSize={1} isAnimationActive={false}
          shape={(props: object) => <Segment {...props} className="revenue-bar revenue-bar-estimated" field="dashed" top={() => true} />} />
      </BarChart>
    </div>
    <figcaption>{keys.map((key) => <span key={key.label}><i className={key.dashed ? 'revenue-key revenue-key-estimated' : 'revenue-key'} /> {key.label}</span>)}</figcaption>
  </figure>;
}
