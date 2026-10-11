import { Link } from 'react-router-dom';
import { Badge, Hint, MetricCard, PageIntro, SectionCard, Tooltip } from '../components';
import { ChannelFindings } from '../components/ChannelViews';
import type { AbcRegistryDivergenceWarning, BillingUniformSplitWarning, DemandDivergenceWarning, SellInBillingDivergenceWarning } from '../types';
import type { PageProps } from './shared';
import { displayCurrency, displayQuantity, displayShare } from './shared';

const ratioText = (ratio: number) => `×${ratio.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}`;
const plural = (count: number, one: string, many: string) => `${count.toLocaleString('pt-BR')} ${count === 1 ? one : many}`;
const ABC_VISIBLE = 10;

/** Avisos da Etapa 16 sobre fontes que não fecham entre si: cada um vira uma linha, com os itens atrás de "Ver itens". */
function ConsistencyWarnings({ abc, sellIn, split }: { abc?: AbcRegistryDivergenceWarning; sellIn?: SellInBillingDivergenceWarning; split?: BillingUniformSplitWarning }) {
  if (!abc && !sellIn && !split) return null;
  const abcItems = abc ? [...abc.items].sort((a, b) => b.revenue_12m - a.revenue_12m) : [];
  const topSellIn = sellIn?.items.find((item) => typeof item.ratio === 'number');
  return <div className="warnings-block">
    <div className="table-shell" tabIndex={0} role="region" aria-label="Avisos de consistência entre as abas da planilha"><table className="data-table warnings-table">
      <caption>Avisos de consistência entre abas</caption>
      <thead><tr><th>Aviso</th><th>Quantos</th><th>O que significa</th></tr></thead>
      <tbody>
        {abc && <tr><td><strong>Curva ABC do cadastro</strong> <Tooltip label="Aviso ABC_REGISTRY_DIVERGENCE">{abc.message}</Tooltip></td><td>{plural(abc.count, 'SKU', 'SKUs')}</td><td>O cadastro e o faturamento de 12 meses discordam; confira a classe antes de usá-la.</td></tr>}
        {sellIn && <tr><td><strong>Sell-in × faturado</strong> <Tooltip label="Aviso SELLIN_BILLING_DIVERGENCE">{sellIn.message}</Tooltip></td><td>{plural(sellIn.count, 'parceiro', 'parceiros')}</td><td>As duas fontes diferem além de {ratioText(sellIn.limit)}{topSellIn ? `; a maior é ${topSellIn.partner} (${ratioText(topSellIn.ratio)})` : ''}.</td></tr>}
        {split && <tr><td><strong>Faturamento por cliente</strong> <Tooltip label="Aviso BILLING_UNIFORM_SPLIT">{split.message}</Tooltip></td><td>{plural(split.count, 'razão', 'razões')}</td><td>Quase proporcional entre clientes ({split.min_ratio.toLocaleString('pt-BR')} a {split.max_ratio.toLocaleString('pt-BR')}): é rateio, não padrão do parceiro.</td></tr>}
      </tbody>
    </table></div>
    {(abc || sellIn) && <details className="validation-details"><summary>Ver itens dos avisos</summary>
      {abc && <div className="table-shell" tabIndex={0} role="region" aria-label="SKUs com Curva ABC divergente"><table className="data-table warnings-table">
        <caption>Maiores faturamentos entre os SKUs com classe divergente{abcItems.length > ABC_VISIBLE ? ` (${ABC_VISIBLE} de ${abcItems.length})` : ''}</caption>
        <thead><tr><th>SKU</th><th>Cadastro</th><th>Medida</th><th>Faturamento 12 meses</th></tr></thead>
        <tbody>{abcItems.slice(0, ABC_VISIBLE).map((item) => <tr key={item.sku}><td><Link to={`/skus/${encodeURIComponent(item.sku)}`}>{item.sku}</Link></td><td>{item.registry}</td><td>{item.measured}</td><td>{displayCurrency(item.revenue_12m)}</td></tr>)}</tbody>
      </table></div>}
      {sellIn && <div className="table-shell" tabIndex={0} role="region" aria-label="Parceiros com sell-in divergente do faturado"><table className="data-table warnings-table">
        <caption>Parceiros em que sell-in e faturado não fecham</caption>
        <thead><tr><th>Parceiro</th><th>Sell-in (un.)</th><th>Faturado (un.)</th><th>Razão</th></tr></thead>
        <tbody>{sellIn.items.map((item) => <tr key={item.partner}><td>{item.partner}</td><td>{displayQuantity(item.sell_in_units)}</td><td>{displayQuantity(item.billed_units)}</td><td>{typeof item.ratio === 'number' ? ratioText(item.ratio) : 'sem faturado'}</td></tr>)}</tbody>
      </table></div>}
    </details>}
  </div>;
}

export default function QualityPage({ data }: PageProps<'quality'>) {
  const sheets = Object.entries(data.quality.sheets);
  const orphanCount = data.quality.foreign_keys.reduce((sum, item) => sum + item.orphan_count, 0);
  const toReview = sheets.filter(([, sheet]) => sheet.duplicate_keys || sheet.missing_columns.length);
  const noErrors = !data.quality.errors.length && !orphanCount;
  const coverage = data.quality.sell_out_coverage;
  const demand = data.quality.warnings.find((item) => item.code === 'REGISTERED_DEMAND_DIVERGENCE') as DemandDivergenceWarning | undefined;
  const abc = data.quality.warnings.find((item) => item.code === 'ABC_REGISTRY_DIVERGENCE') as AbcRegistryDivergenceWarning | undefined;
  const sellIn = data.quality.warnings.find((item) => item.code === 'SELLIN_BILLING_DIVERGENCE') as SellInBillingDivergenceWarning | undefined;
  const split = data.quality.warnings.find((item) => item.code === 'BILLING_UNIFORM_SPLIT') as BillingUniformSplitWarning | undefined;
  return <>
    <PageIntro title="Posso confiar na planilha?" description={noErrors ? `Sem erros bloqueantes e sem registros sem vínculo. O principal limite é a cobertura de sell-out: ${displayShare(coverage.coverage)}.` : 'Há itens para revisar antes de decidir.'} />
    <div className="quality-summary"><div className="metrics-grid quality-metrics">
      <MetricCard label="Situação da base" value={noErrors ? 'Sem erros' : `${data.quality.errors.length + orphanCount} a revisar`} detail={`${sheets.length - toReview.length} de ${sheets.length} abas íntegras`} tone={noErrors ? 'green' : 'amber'} icon="quality" />
      <MetricCard label={<>Cobertura de sell-out <Hint term="ausente" /></>} value={displayShare(coverage.coverage)} detail={`${coverage.observed_pairs} de ${coverage.possible_pairs} combinações parceiro–SKU com venda informada`} tone="slate" icon="b2b" />
      {demand && <MetricCard label={<>Venda média cadastrada <Tooltip label="SKUs com maior diferença">A cobertura usa a demanda prevista, não o cadastro. Maiores diferenças (prevista ÷ cadastrada): {demand.items.slice(0, 5).map((item) => `${item.sku} ${ratioText(item.ratio)}`).join('; ')}.</Tooltip></>} value={`${demand.count} SKUs`} detail="distantes da demanda prevista" tone="amber" icon="quality" />}
    </div>
    <ConsistencyWarnings abc={abc} sellIn={sellIn} split={split} /></div>
    <ChannelFindings />
    {toReview.length > 0 && <SectionCard title="Abas para revisar">
      <div className="table-shell" tabIndex={0} role="region" aria-label="Abas da planilha; role horizontalmente para ver todas as colunas"><table className="data-table"><thead><tr><th>Aba</th><th>Registros</th><th>Duplicidades</th><th>Colunas ausentes</th><th>Situação</th></tr></thead><tbody>{toReview.map(([name, sheet]) => <tr key={name}><td><strong>{name.split('_').join(' ')}</strong></td><td>{sheet.records.toLocaleString('pt-BR')}</td><td>{sheet.duplicate_keys}</td><td>{sheet.missing_columns.length}</td><td><Badge tone="medium">Revisar</Badge></td></tr>)}</tbody></table></div>
    </SectionCard>}
  </>;
}
