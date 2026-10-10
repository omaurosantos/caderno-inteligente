import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, Cell, LabelList, Pie, PieChart, Tooltip as ChartTooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api';
import { useApiResource } from '../hooks/useApiResource';
import { Alert, Badge, EmptyState, Hint, SectionCard } from '../components';
import type { Overview } from '../types';
import type { RevenueForecast, RevenueGroup } from '../types-revenue';
import { displayCurrency, displayNumber, displayShare, displayUnits } from '../pages/shared';
import { useWidth } from './MonthlyBars';

/** Uma leitura da API com o seu estado, para o Início carregar uma vez e repartir entre os blocos. */
export interface Resource<T> { data?: T; error: string; loading: boolean; refresh: () => Promise<void> }

function BlockLoading({ title }: { title: string }) {
  return <SectionCard title={title} subtitle="Carregando…"><div className="drawer-loading"><span /><span /></div></SectionCard>;
}

/** Bloco que falhou: explica e permite nova tentativa sem derrubar o restante do Início. */
function BlockError({ title, error, retry }: { title: string; error: string; retry: () => Promise<void> }) {
  return <Alert tone="warning" title={`${title}: indisponível`} action={<button className="secondary-button" onClick={() => void retry()}>Tentar novamente</button>}>{error || 'Não foi possível carregar este bloco.'} O restante do Início segue válido.</Alert>;
}

const ptPercent = new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 1 });
const signedPercent = (ratio: number) => `${ratio >= 0 ? '+' : '−'}${ptPercent.format(Math.abs(ratio))}`;

function KpiCard({ to, tone, label, value, detail }: { to: string; tone: 'pen' | 'urgent' | 'review' | 'neutral'; label: string; value: string; detail: ReactNode }) {
  return <li><Link className={`kpi-card kpi-${tone}`} to={to}>
    <span className="kpi-label">{label}</span>
    <strong className="kpi-value">{value}</strong>
    {detail && <span className="kpi-detail">{detail}</span>}
  </Link></li>;
}

/**
 * Quatro indicadores no topo do Início. Faturamento e produção carregam à parte:
 * enquanto carregam ou se falharem, o cartão diz isso e nunca mostra zero.
 */
export function OverviewKpis({ overview, revenue, refreshToken }: { overview: Overview; revenue: Resource<RevenueForecast>; refreshToken: number }) {
  const plan = useApiResource(api.productionPlan, refreshToken);
  const total = revenue.data?.total;
  const change = total?.change_vs_last_3m ?? null;
  const production = plan.data?.total;
  const pending = (resource: { data?: unknown; loading: boolean }) => !resource.data && resource.loading;
  return <ul className="kpi-cards" aria-label="Indicadores principais">
    <KpiCard to="/faturamento" tone="pen" label="Faturamento previsto"
      value={pending(revenue) ? 'Carregando…' : displayCurrency(total?.revenue_total_3m)}
      detail={total ? <>Próximos 3 meses{change !== null && <> · <span className="kpi-delta"><span aria-hidden="true">{change >= 0 ? '▲' : '▼'}</span> {signedPercent(change)}</span> sobre os 3 anteriores</>}</> : pending(revenue) ? null : 'Estimativa indisponível agora'} />
    <KpiCard to="/fila?sinal=ruptura" tone="urgent" label="SKUs com risco de ruptura" value={displayNumber(overview.rupture_sku_count)}
      detail={`${overview.below_lead_time_count} abaixo do prazo · ${overview.below_safety_stock_count} abaixo da segurança`} />
    <KpiCard to="/fila" tone="review" label="Produção para liberar agora"
      value={pending(plan) ? 'Carregando…' : displayUnits(production?.urgent_total)}
      detail={production ? `${displayUnits(production.horizon_total)} no horizonte` : pending(plan) ? null : 'Plano indisponível agora'} />
    <KpiCard to="/fila" tone="neutral" label="Pedidos sem ordem de produção" value={displayNumber(overview.order_without_production)}
      detail={`${overview.low_confidence} de ${overview.prioritized} SKUs com confiança baixa`} />
  </ul>;
}

/** Fatias por família: as seis maiores e o resto somado em "Outras". A cor segue a família (ordem do nome), nunca a posição. */
const MAX_SLICES = 6;
function familySlices(families: RevenueGroup[]) {
  const ranked = families.filter((group) => typeof group.revenue_total_3m === 'number' && group.revenue_total_3m > 0)
    .sort((a, b) => (b.revenue_total_3m ?? 0) - (a.revenue_total_3m ?? 0));
  const kept = ranked.length > MAX_SLICES + 1 ? ranked.slice(0, MAX_SLICES) : ranked;
  const rest = ranked.slice(kept.length);
  const series = new Map([...kept].sort((a, b) => a.label.localeCompare(b.label, 'pt-BR')).map((group, index) => [group.label, `series-${index + 1}`]));
  const slices = kept.map((group) => ({ label: group.label, value: group.revenue_total_3m as number, series: series.get(group.label) as string }));
  if (rest.length) slices.push({ label: `Outras (${rest.length})`, value: rest.reduce((sum, group) => sum + (group.revenue_total_3m ?? 0), 0), series: 'series-other' });
  return slices;
}

type Slice = ReturnType<typeof familySlices>[number] & { share: number };

function SliceTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Slice }> }) {
  const slice = payload?.[0]?.payload;
  if (!active || !slice) return null;
  return <div className="chart-tooltip">
    <strong>{slice.label}</strong>
    <span><i className={`pie-key ${slice.series}`} />{displayCurrency(slice.value)} · {displayShare(slice.share)}</span>
  </div>;
}

/** Faturamento previsto por família (próximos 3 meses), em pizza; a tabela ao lado é a legenda e traz os valores. */
export function RevenueByFamily({ revenue }: { revenue: Resource<RevenueForecast> }) {
  const { data, error, loading, refresh } = revenue;
  const title = 'Faturamento previsto por família';
  if (!data && loading) return <BlockLoading title={title} />;
  if (!data) return <BlockError title={title} error={error} retry={refresh} />;
  const raw = familySlices(data.families);
  const sum = raw.reduce((acc, slice) => acc + slice.value, 0);
  const slices: Slice[] = raw.map((slice) => ({ ...slice, share: slice.value / sum }));
  const excluded = data.families.filter((group) => group.revenue_total_3m === null).length;
  const tag = <span className="revenue-card-tag"><Badge tone="info">Estimativa</Badge><Hint term="faturamento_estimado" /></span>;
  if (!slices.length) return <SectionCard title={title} action={tag}><EmptyState title="Nenhuma família com estimativa" description="Família sem preço ou sem previsão fica de fora; ausência não é faturamento zero." /></SectionCard>;
  return <SectionCard className="family-pie-card" title={title} subtitle={`Estimativa de ${displayCurrency(sum)} nos próximos três meses.`} action={tag}>
    <div className="family-pie">
      <div className="chart-frame family-pie-chart" role="img" aria-label={`Faturamento previsto por família nos próximos três meses. ${slices.map((slice) => `${slice.label}: ${displayCurrency(slice.value)} (${displayShare(slice.share)})`).join('; ')}.`}>
        <PieChart width={160} height={160} accessibilityLayer={false}>
          <Pie data={slices} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={76} startAngle={90} endAngle={-270} isAnimationActive={false}>
            {slices.map((slice) => <Cell key={slice.label} className={`pie-slice ${slice.series}`} />)}
          </Pie>
          <ChartTooltip isAnimationActive={false} content={<SliceTooltip />} />
        </PieChart>
      </div>
      <div className="table-shell" tabIndex={0} role="region" aria-label="Faturamento previsto por família, valores"><table className="data-table"><caption className="sr-only">Faturamento previsto por família nos próximos três meses; estimativa, não faturamento realizado</caption><thead><tr><th>Família</th><th>Estimativa</th><th>Parte</th></tr></thead><tbody>{slices.map((slice) => <tr key={slice.label}>
        <td><span className="pie-name"><i className={`pie-key ${slice.series}`} aria-hidden="true" />{slice.label}</span></td>
        <td>{displayCurrency(slice.value)}</td>
        <td>{displayShare(slice.share)}</td>
      </tr>)}</tbody></table></div>
    </div>
    {excluded > 0 && <p className="fact-line">{excluded} {excluded === 1 ? 'família sem estimativa fica' : 'famílias sem estimativa ficam'} de fora; ausência não é faturamento zero.</p>}
  </SectionCard>;
}

const ptCompactCurrency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1 });
const compactCurrency = (value: number) => ptCompactCurrency.format(value);
/** Espaço à direita para o valor no fim da barra, pelo maior rótulo (≈7 px por caractere no tamanho de meta). */
const valueRoom = (rows: RankRow[]) => Math.max(...rows.map((row) => row.valueLabel.length)) * 7 + 12;

interface RankRow { key: string; label: string; value: number; valueLabel: string; tip: string }

function RankTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: RankRow }> }) {
  const row = payload?.[0]?.payload;
  if (!active || !row) return null;
  return <div className="chart-tooltip"><strong>{row.label}</strong><span>{row.tip}</span></div>;
}

/**
 * Ranking em barras horizontais, numa cor só (a da ação): o nome à esquerda e o valor no fim de cada barra.
 * A dica mostra o detalhe; o texto acessível traz todos os valores.
 */
function RankBars({ rows, label, labelWidth }: { rows: RankRow[]; label: string; labelWidth: number }) {
  const [ref, width] = useWidth();
  return <div ref={ref} className="chart-frame" role="img" aria-label={`${label} ${rows.map((row) => `${row.label}: ${row.tip}`).join('; ')}.`}>
    <BarChart layout="vertical" width={width} height={rows.length * 40 + 8} data={rows} margin={{ top: 4, right: valueRoom(rows), bottom: 4, left: 0 }} accessibilityLayer={false}>
      <XAxis type="number" hide domain={[0, 'dataMax']} />
      <YAxis type="category" dataKey="label" width={labelWidth} tickLine={false} axisLine={{ className: 'chart-axis' }} tick={{ className: 'chart-tick' }} />
      <ChartTooltip cursor={{ className: 'chart-cursor' }} isAnimationActive={false} content={<RankTooltip />} />
      <Bar dataKey="value" className="rank-bar" maxBarSize={20} radius={[0, 4, 4, 0]} minPointSize={1} isAnimationActive={false}>
        <LabelList dataKey="valueLabel" position="right" className="chart-end-label" />
      </Bar>
    </BarChart>
  </div>;
}

const TOP_SKUS = 5;

/** Os cinco SKUs que mais puxam o faturamento previsto (próximos 3 meses). SKU sem preço ou sem previsão fica de fora, nunca como zero. */
export function TopSkusByRevenue({ revenue }: { revenue: Resource<RevenueForecast> }) {
  const { data, error, loading, refresh } = revenue;
  const title = 'SKUs com maior faturamento previsto';
  if (!data && loading) return <BlockLoading title={title} />;
  if (!data) return <BlockError title={title} error={error} retry={refresh} />;
  const total = data.total.revenue_total_3m;
  const rows: RankRow[] = data.items.filter((item) => item.status === 'ok' && typeof item.revenue_total_3m === 'number')
    .sort((a, b) => (b.revenue_total_3m ?? 0) - (a.revenue_total_3m ?? 0)).slice(0, TOP_SKUS)
    .map((item) => {
      const value = item.revenue_total_3m as number;
      const share = total ? ` · ${displayShare(value / total)} do total` : '';
      return { key: item.sku, label: item.sku, value, valueLabel: compactCurrency(value), tip: `${item.product ?? item.family}: ${displayCurrency(value)}${share}` };
    });
  const tag = <span className="revenue-card-tag"><Badge tone="info">Estimativa</Badge><Hint term="faturamento_estimado" /></span>;
  return <SectionCard title={title} subtitle={`Os ${TOP_SKUS} maiores nos próximos três meses.`} action={tag}>
    {rows.length ? <RankBars rows={rows} labelWidth={72} label={`Os ${rows.length} SKUs com maior faturamento previsto nos próximos três meses.`} />
      : <EmptyState title="Nenhum SKU com estimativa" description="SKU sem preço ou sem previsão fica de fora; ausência não é faturamento zero." />}
    <Link className="secondary-button" to="/faturamento">Ver o financeiro</Link>
  </SectionCard>;
}

/** Faturamento observado dos canais diretos (24 meses), do maior para o menor, com a parte de cada um no faturamento total. */
export function DirectChannelsRevenue({ refreshToken }: { refreshToken: number }) {
  const { data, error, loading, refresh } = useApiResource(api.directChannels, refreshToken);
  const title = 'Faturamento por canal direto';
  if (!data && loading) return <BlockLoading title={title} />;
  if (!data) return <BlockError title={title} error={error} retry={refresh} />;
  const known = data.channels.filter((channel) => typeof channel.revenue_24m === 'number');
  const missing = data.channels.length - known.length;
  const rows: RankRow[] = [...known].sort((a, b) => (b.revenue_24m ?? 0) - (a.revenue_24m ?? 0)).map((channel) => {
    const value = channel.revenue_24m as number;
    const share = channel.share_of_revenue === null ? '' : displayShare(channel.share_of_revenue);
    return { key: channel.code, label: channel.name ?? channel.code, value, valueLabel: share ? `${compactCurrency(value)} · ${share}` : compactCurrency(value),
      tip: `${displayCurrency(value)} em 24 meses${share ? ` · ${share} do faturamento total` : ''}` };
  });
  return <SectionCard title={title} subtitle="Observado nos últimos 24 meses e a parte de cada canal no faturamento total." action={<Hint term="canais_diretos" />}>
    {rows.length ? <RankBars rows={rows} labelWidth={140} label="Faturamento observado dos canais diretos nos últimos 24 meses." />
      : <EmptyState title="Nenhum canal direto com faturamento" description="Canal sem faturamento observado não aparece como zero." />}
    {missing > 0 && <p className="fact-line">{missing} {missing === 1 ? 'canal sem faturamento observado fica' : 'canais sem faturamento observado ficam'} de fora.</p>}
    <Link className="secondary-button" to="/canais">Ver os canais</Link>
  </SectionCard>;
}
