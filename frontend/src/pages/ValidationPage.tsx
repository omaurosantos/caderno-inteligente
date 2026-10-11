import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { Alert, Badge, ErrorState, Hint, LoadingState, MetricCard, PageIntro, SectionCard, Tooltip } from '../components';
import { ForecastLabSection } from '../components/ForecastLab';
import type { AddressedValue, CaseCheck, FrozenCase, MeasuredValue, SafeBehaviorCheck, SopDivergence, ValidationSummary } from '../types-validation';
import { validationCsv } from '../validation-export';
import { displayCurrency, displayNumber, displayPercent, displayShare, formatDate, formatMonth } from './shared';

const fieldNames: Record<string, string> = {
  signals: 'Sinais', action: 'Ação', suggested_quantity: 'Quantidade sugerida', requires_human_review: 'Revisão humana',
  ranked: 'No ranking', priority: 'Prioridade', capacity_status: 'Capacidade', confidence: 'Confiança',
  forecast_status: 'Status da previsão', data_quality: 'Qualidade do dado', missing_months: 'Meses ausentes',
  estimated_stock: 'Estoque estimado', coverage_days: 'Cobertura (dias)',
};
const inputNames: Record<string, string> = {
  current_stock: 'Estoque atual', coverage_days_calculated: 'Cobertura calculada (dias)', lead_time_days: 'Prazo de produção (dias)',
  safety_stock_days: 'Segurança (dias)', backlog_order_quantity: 'Carteira', production_order_quantity: 'Produção aberta',
  first_promised_date: 'Primeira promessa', first_production_completion: 'Primeira conclusão prevista',
  capacity_occupation_average: 'Ocupação média da família', has_sell_out: 'Sell-out observado', forecast_status: 'Status da previsão',
  forecast_next_month: 'Previsão do próximo mês', sell_out_months: 'Meses com sell-out', missing_months: 'Meses ausentes',
  estimated_stock: 'Estoque estimado do parceiro', average_monthly_sell_out: 'Sell-out médio mensal', coverage_days: 'Cobertura no parceiro (dias)',
  age_months: 'Idade do dado (meses)', backlog_quantity: 'Carteira do par',
};
const resultLabel: Record<FrozenCase['result'], string> = { passou: 'Passou', falhou: 'Falhou', nao_encontrado: 'Não encontrado', pendente: 'Pendente' };
const resultTone: Record<FrozenCase['result'], string> = { passou: 'good', falhou: 'critical', nao_encontrado: 'medium', pendente: 'neutral' };
const safeLabel: Record<SafeBehaviorCheck['status'], string> = { aprovado: 'Aprovado', reprovado: 'Reprovado', coberto_por_teste: 'Coberto por teste' };
const safeTone: Record<SafeBehaviorCheck['status'], string> = { aprovado: 'good', reprovado: 'critical', coberto_por_teste: 'neutral' };
const roleTone: Record<string, string> = { candidato: 'neutral', selecionado: 'good', baseline: 'medium' };
const roleLabel: Record<string, string> = { candidato: 'candidato', selecionado: 'selecionado', baseline: 'previsão simples (baseline)' };

const isRatio = (unit: string | null) => !!unit && (unit === 'percentual' || unit === 'MAPE' || unit.startsWith('WAPE'));
const ratioText = (value: number, unit: string | null) => unit?.startsWith('WAPE') ? displayPercent(value) : displayShare(value);
const unitLabel = (unit: string | null) => unit === 'MAPE' ? 'MAPE (erro percentual médio informado)' : unit?.startsWith('WAPE') ? unit.replace('WAPE', 'erro médio (WAPE)') : unit;
function measured(value: MeasuredValue | null) {
  if (!value || value.value === null) return <span className="validation-muted">Não disponível</span>;
  return <><strong>{isRatio(value.unit) ? ratioText(value.value, value.unit) : `${displayNumber(value.value)} ${value.unit ?? ''}`}</strong>{isRatio(value.unit) && value.unit !== 'percentual' && <small>{unitLabel(value.unit)}</small>}</>;
}

function plain(value: unknown): string {
  if (value === null || value === undefined) return 'não disponível';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'vazio';
  if (typeof value === 'boolean') return value ? 'sim' : 'não';
  if (typeof value === 'number') return displayNumber(value);
  return String(value);
}

function CheckList({ checks }: { checks: CaseCheck[] }) {
  return <ul className="validation-checks">{checks.map((check) => <li key={check.field} className={check.passed ? 'is-passed' : 'is-failed'}>
    <span aria-hidden="true">{check.passed ? '✓' : '✗'}</span>
    <span><strong>{fieldNames[check.field] ?? check.field}</strong> — esperado: {plain(check.expected)} · obtido: {plain(check.obtained)}<span className="sr-only">{check.passed ? ' (atendido)' : ' (não atendido)'}</span></span>
  </li>)}</ul>;
}

function InputList({ input }: { input: Record<string, unknown> | null }) {
  if (!input) return <span className="validation-muted">Caso não encontrado na base atual.</span>;
  return <dl className="validation-input">{Object.entries(input).map(([key, value]) => <div key={key}><dt>{inputNames[key] ?? key}</dt><dd>{plain(value)}</dd></div>)}</dl>;
}

function download(summary: ValidationSummary) {
  const blob = new Blob([validationCsv(summary)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `validacao-caderno-inteligente-${summary.generated_at.slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

const signedPercent = (ratio: number) => `${ratio > 0 ? '+' : ''}${displayPercent(ratio)}`;
const SOP_VISIBLE = 10;

/** Cartão do valor observado em risco dos SKUs com decisão registrada: valor sob decisão, não valor recuperado. */
function AddressedValueCard({ value }: { value: AddressedValue }) {
  const label = <>Valor em risco endereçado <Tooltip label="Como ler o valor endereçado">{value.note} Natureza: {value.nature}; não é dinheiro recuperado.{value.skus_without_value.length ? ` Sem valor calculado: ${value.skus_without_value.join(', ')}.` : ''}{value.observed_total === null && value.missing_reason ? ` Indisponível: ${value.missing_reason}` : ''}</Tooltip></>;
  return <MetricCard label={label} value={value.observed_total === null ? 'Não disponível' : displayCurrency(value.observed_total)} detail={value.decided_skus.length ? 'em SKUs com decisão registrada' : 'nenhuma decisão registrada ainda'} tone="green" icon="validation" />;
}

function SopRow({ item }: { item: SopDivergence['items'][number] }) {
  return <tr><td><Link to={`/skus/${encodeURIComponent(item.sku)}`}>{item.sku}</Link><small>{formatMonth(`${item.month}-01`)}</small></td><td>{displayNumber(item.model)}</td><td>{displayNumber(item.sop)}</td><td>{signedPercent(item.ratio)}</td></tr>;
}

/** Pauta de revisão: onde o modelo e o consenso do S&OP se afastam além do limite. Nenhum dos lados é tratado como o certo. */
function SopDivergenceSection({ value }: { value: SopDivergence }) {
  const sorted = [...value.items].sort((a, b) => Math.abs(b.ratio) - Math.abs(a.ratio));
  const head = sorted.slice(0, SOP_VISIBLE);
  const rest = sorted.slice(SOP_VISIBLE);
  const tableHead = <thead><tr><th>SKU e mês</th><th>Modelo</th><th>S&amp;OP</th><th>Diferença</th></tr></thead>;
  return <SectionCard title="Modelo × S&OP: pauta de revisão" action={<Badge tone="neutral">{value.nature}</Badge>}>
    <p className="fact-line">{value.note}</p>
    {value.items.length ? <div className="table-shell" tabIndex={0} role="region" aria-label="Divergências entre modelo e S&OP; role horizontalmente para ver todas as colunas"><table className="data-table validation-table sop-table">
      <caption>{value.count} divergências acima de {displayShare(value.threshold)} em {new Set(value.items.map((item) => item.sku)).size} SKUs, entre {value.compared_pairs} pares comparados; maiores primeiro (diferença do modelo sobre o S&amp;OP)</caption>
      {tableHead}<tbody>{head.map((item) => <SopRow key={`${item.sku}-${item.month}`} item={item} />)}</tbody>
    </table></div> : <p className="validation-muted">Nenhuma divergência acima do limite nos meses comparados.</p>}
    {rest.length > 0 && <details className="validation-details"><summary>Ver as demais</summary>
      <div className="table-shell" tabIndex={0} role="region" aria-label="Demais divergências entre modelo e S&OP"><table className="data-table validation-table sop-table">{tableHead}<tbody>{rest.map((item) => <SopRow key={`${item.sku}-${item.month}`} item={item} />)}</tbody></table></div>
    </details>}
  </SectionCard>;
}

export default function ValidationPage({ refreshToken }: { refreshToken: number }) {
  const { data, error, loading, loadedAt, refresh } = useApiResource(api.validationSummary, refreshToken);
  usePageLoadStatus(loading, error, loadedAt);
  if (!data && error) return <ErrorState message={error} onRetry={() => void refresh()} />;
  if (!data) return <LoadingState />;
  return <ValidationContent data={data} error={error} onRetry={() => void refresh()} refreshToken={refreshToken} />;
}

const tabs = [
  { id: 'processo', label: 'Processo atual' },
  { id: 'modelos', label: 'Modelos de previsão' },
] as const;

/** Pure rendering of a loaded summary; kept separate so it can be tested without the API. Os dois painéis ficam no HTML (impressão e exportação); só o ativo fica visível. */
export function ValidationContent({ data, error = '', onRetry, refreshToken = 0 }: { data: ValidationSummary; error?: string; onRetry: () => void; refreshToken?: number }) {
  const [tab, setTab] = useState<(typeof tabs)[number]['id']>('processo');
  const { forecast_evaluation: forecast, frozen_cases: cases, analysis_time: time } = data;
  const selected = forecast.models.find((model) => model.role === 'selecionado');
  const baseline = forecast.models.find((model) => model.role === 'baseline');
  const safeExecuted = data.safe_behavior.filter((check) => check.status !== 'coberto_por_teste');
  const safeFailed = safeExecuted.filter((check) => check.status === 'reprovado').length;
  const notBeating = forecast.items.filter((item) => item.outcome !== 'superou');
  const casesOk = cases.failed === 0 && cases.not_found === 0;
  const rolling = forecast.method === 'rolante';
  // Os avisos de "caso com entrada sintética" são um só fato: viram uma linha.
  const syntheticNotes = data.known_failures.filter((item) => item.area === 'cobertura dos casos');
  const failures = data.known_failures.filter((item) => item.area !== 'cobertura dos casos');

  return <div className="validation-page">
    <PageIntro title="Quanto confiar nas recomendações" action={<div className="validation-actions"><button className="secondary-button" onClick={() => download(data)}>Exportar CSV</button><button className="secondary-button" onClick={() => window.print()}>Imprimir resumo</button></div>} />
    {error && <Alert tone="warning" title="Falha ao atualizar a validação" action={<button className="secondary-button" onClick={onRetry}>Tentar novamente</button>}>{error} A última carga permanece exibida.</Alert>}
    {!cases.source_matches_frozen && <Alert tone="warning" title="Base alterada desde o congelamento">{cases.source_note}</Alert>}

    <section className="verdict" aria-labelledby="verdict-title">
      <h3 id="verdict-title">Em resumo</h3>
      <p>Em <strong>{forecast.did_not_beat_baseline_skus} de {forecast.eligible_skus} SKUs</strong> a previsão do modelo não foi melhor do que repetir o último mês. No conjunto, o erro médio é de {displayPercent(selected?.weighted_wape)} contra {displayPercent(baseline?.weighted_wape)} da previsão simples{rolling ? <>; nos meses de pico, <strong>{displayPercent(selected?.peak_weighted_wape)}</strong> contra {displayPercent(baseline?.peak_weighted_wape)}</> : null}.</p>
    </section>

    <div className="metrics-grid">
      <MetricCard label="Casos de teste aprovados" value={`${cases.passed} de ${cases.total - (cases.pending ?? 0)}`} detail={`${cases.synthetic} com entrada sintética${cases.pending ? ` · ${cases.pending} pendentes` : ''}`} tone={casesOk ? 'green' : 'red'} icon="validation" />
      <MetricCard label="Erro médio da previsão (WAPE)" value={displayPercent(selected?.weighted_wape)} detail={rolling ? `normais ${displayPercent(selected?.normal_weighted_wape)} · pico ${displayPercent(selected?.peak_weighted_wape)}` : `previsão simples: ${displayPercent(baseline?.weighted_wape)}`} tone="blue" icon="forecasts" />
      <MetricCard label="Modelo pior que a baseline" value={`${forecast.did_not_beat_baseline_skus} de ${forecast.eligible_skus}`} detail={`SKUs · melhor em ${forecast.beat_baseline_skus}`} tone={forecast.did_not_beat_baseline_skus ? 'amber' : 'green'} icon="forecasts" />
      {data.addressed_value && <AddressedValueCard value={data.addressed_value} />}
    </div>

    <SectionCard title="Falhas conhecidas" action={<Link className="secondary-button" to="/auditoria">Auditoria completa</Link>}>
      {failures.length || syntheticNotes.length ? <ul className="validation-list">{failures.map((item) => <li key={item.description}><Badge tone="medium">{item.area}</Badge> {item.description}</li>)}{syntheticNotes.length > 0 && <li><Badge tone="medium">cobertura dos casos</Badge> {syntheticNotes.length} {syntheticNotes.length === 1 ? 'caso de teste usa' : 'casos de teste usam'} entrada sintética (a planilha não tem esse exemplo).</li>}</ul> : <p className="validation-muted">Nenhuma falha detectada nesta consulta.</p>}
      <p className="fact-line">Verificações de segurança: {safeExecuted.length - safeFailed} de {safeExecuted.length} {safeFailed ? `passaram; ${safeFailed} reprovada(s)` : 'passaram'}.</p>
    </SectionCard>

    <div className="tab-list" role="tablist" aria-label="Detalhes da validação">{tabs.map((item) => <button key={item.id} id={`tab-${item.id}`} role="tab" type="button" aria-selected={tab === item.id} aria-controls={`panel-${item.id}`} className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}>{item.label}</button>)}</div>

    <div role="tabpanel" id="panel-processo" aria-labelledby="tab-processo" hidden={tab !== 'processo'} className="tab-panel">
      <SectionCard title="Comparação com o processo atual">
        <div className="table-shell" tabIndex={0} role="region" aria-label="Comparação com o processo atual; role horizontalmente para ver todas as colunas"><table className="data-table validation-table validation-comparison">
          <thead><tr><th>Indicador</th><th>Informado pela empresa</th><th>Recalculado no protótipo</th><th>Meta</th></tr></thead>
          <tbody>{data.process_comparison.map((row) => <tr key={row.id}>
            <td><strong>{row.label}</strong></td>
            <td><div className="validation-value"><Badge tone="neutral">informado</Badge>{measured(row.informed)}</div></td>
            <td><div className="validation-value"><Badge tone="medium">recalculado</Badge>{measured(row.recalculated)}{row.recalculated.value !== null && !row.recalculated.comparable && <small>não comparável diretamente</small>}{row.recalculated.reason && <Tooltip label={`Por que: ${row.label}`}>{row.recalculated.reason}</Tooltip>}</div></td>
            <td>{row.target ? <div className="validation-value"><Badge tone="good">meta</Badge>{measured(row.target)}</div> : <span className="validation-muted">Sem meta informada</span>}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="fact-line">Tempo de análise registrado: {time.comparison_allowed ? `média de ${displayNumber(time.average_minutes_per_decision)} min por decisão (${time.records_with_minutes} decisões)` : `sem dados suficientes (${time.records_with_minutes} de ${time.minimum_sample} decisões com tempo informado)`}. <Link to="/decisoes">Registrar decisão</Link></p>
      </SectionCard>
    </div>

    <div role="tabpanel" id="panel-modelos" aria-labelledby="tab-modelos" hidden={tab !== 'modelos'} className="tab-panel">
      {data.sop_divergence && <SopDivergenceSection value={data.sop_divergence} />}
      <SectionCard title="Desempenho dos modelos">
        <div className="table-shell" tabIndex={0} role="region" aria-label="Desempenho dos modelos; role horizontalmente para ver todas as colunas"><table className="data-table validation-table">
          <thead><tr><th>Modelo</th><th>Erro ponderado (WAPE) <Hint term="wape" /></th><th>Escolhido em</th></tr></thead>
          <tbody>{forecast.models.map((model) => <tr key={model.model}>
            <td><strong>{model.label}</strong> <Badge tone={roleTone[model.role]}>{roleLabel[model.role] ?? model.role}</Badge></td>
            <td>{displayPercent(model.weighted_wape)}</td>
            <td>{model.role === 'candidato' ? `${model.selected_skus} SKU(s)` : '—'}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="fact-line">O modelo foi melhor em <strong>{forecast.beat_baseline_skus}</strong> SKUs e não superou a baseline em <strong>{forecast.did_not_beat_baseline_skus}</strong> de {forecast.eligible_skus} (empate conta como não superou).</p>
        {notBeating.length > 0 && <details className="validation-details"><summary>Ver os {notBeating.length} SKU(s) em que o modelo não superou a baseline</summary>
          <div className="table-shell" tabIndex={0} role="region" aria-label="SKUs sem ganho sobre a baseline"><table className="data-table validation-table"><thead><tr><th>SKU</th><th>Erro do modelo</th><th>Erro da previsão simples</th></tr></thead>
            <tbody>{notBeating.map((item) => <tr key={item.sku}><td><Link to={`/skus/${encodeURIComponent(item.sku)}`}>{item.sku}</Link></td><td>{displayPercent(item.selected_wape)}</td><td>{displayPercent(item.baseline_wape)}</td></tr>)}</tbody></table></div>
        </details>}
      </SectionCard>
      <ForecastLabSection refreshToken={refreshToken} />
    </div>
  </div>;
}

/** Bloco recolhido da Auditoria: o título e uma nota curta ficam visíveis; o conteúdo abre sob demanda. */
function AuditBlock({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return <details className="detail-block audit-block"><summary>{title}<small>{note}</small></summary>{children}</details>;
}

/** Material de auditoria (não é tela de decisão): casos congelados, verificações, limitações, ajustes e origem dos dados. */
export function AuditoriaContent({ data, method, coverage }: { data: ValidationSummary; method?: ReactNode; coverage?: ReactNode }) {
  const { frozen_cases: cases, forecast_evaluation: forecast } = data;
  return <div className="validation-page">
    <PageIntro title="Auditoria: como os resultados foram testados" />
    {coverage}
    <AuditBlock title="Casos de teste congelados" note={`${cases.total} casos, congelados em ${formatDate(cases.frozen_at)}`}>
      <p className="fact-line">{cases.policy}</p>
      <div className="validation-cases">{cases.items.map((item) => <details key={item.id} className={`validation-case is-${item.result}`} open={item.result === 'falhou' || item.result === 'nao_encontrado'}>
        <summary><span className="validation-case-title"><span className="eyebrow">{item.id} · {item.kind === 'commercial' ? 'comercial' : 'operacional'}</span><strong>{item.title}</strong></span>
          <span className="validation-case-badges">{item.origin === 'synthetic' ? <Badge tone="medium">entrada sintética</Badge> : <Badge tone="neutral">base real</Badge>}<Badge tone={resultTone[item.result]}>{resultLabel[item.result]}</Badge></span></summary>
        <p className="validation-case-origin">{item.origin === 'synthetic' ? item.origin_reason : <>{item.partner ? `${item.partner} · ` : ''}{item.sku && <Link to={`/skus/${encodeURIComponent(item.sku)}`}>{item.sku}</Link>}</>}</p>
        <div className="validation-case-body">
          <div><h5>Entrada</h5><InputList input={item.input} /></div>
          <div><h5>Esperado × obtido</h5>{item.checks.length ? <CheckList checks={item.checks} /> : <span className="validation-muted">Sem saída obtida.</span>}</div>
        </div>
        <footer><p><strong>Limitação:</strong> {item.limitation}</p><p><strong>Ajuste realizado:</strong> {item.adjustment}</p></footer>
      </details>)}</div>
    </AuditBlock>
    <AuditBlock title="Comportamento seguro" note={`${data.safe_behavior.length} verificações`}>
      <p className="fact-line">Verificações executadas a cada consulta com entradas controladas, além das cobertas por testes automatizados.</p>
      <ul className="validation-safe">{data.safe_behavior.map((check) => <li key={check.id}><Badge tone={safeTone[check.status]}>{safeLabel[check.status]}</Badge><div><strong>{check.label}</strong><small>{check.evidence}</small></div></li>)}</ul>
    </AuditBlock>
    <div className="validation-two-columns">
      <AuditBlock title="Limitações" note={`${forecast.limitations.length + data.known_limitations.length} itens`}>
        <ul className="validation-list">{[...forecast.limitations, ...data.known_limitations].map((item) => <li key={item}>{item}</li>)}</ul>
      </AuditBlock>
      <AuditBlock title="Histórico de ajustes" note={`${data.adjustments.length} ajustes`}>
        <p className="fact-line">Mudanças feitas após testes e revisões. Nenhuma alterou pesos ou modelos.</p>
        <ol className="validation-timeline">{data.adjustments.map((entry) => <li key={`${entry.date}-${entry.change}`}><time>{formatDate(entry.date)}</time><strong>{entry.change}</strong><small>{entry.reason}</small><small>Evidência: {entry.evidence} · {entry.changed_weights_or_models ? 'alterou pesos/modelos' : 'não alterou pesos nem modelos'}</small></li>)}</ol>
      </AuditBlock>
    </div>
    {method && <AuditBlock title="Método comercial" note="natureza dos campos e limites configurados">{method}</AuditBlock>}
    <p className="validation-source">Planilha SHA-256 {data.source.sha256.slice(0, 12)}… · Referência de vendas: {formatDate(data.source.sales_reference_month)} · Gerado em {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date(data.generated_at))} (Brasília)</p>
  </div>;
}
