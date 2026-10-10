import type { ReactNode } from 'react';
import { api } from '../api';
import { Badge, LoadingState, PageIntro, SectionCard, Tooltip } from '../components';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import type { BenchmarkResult, ModelBenchmarkSection, ModelCard } from '../types-model-benchmark';
import { displayPercent, formatDateTime } from './shared';

const MONTHS = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const signed = (value: number | null) => value === null ? 'Não disponível' : `${value > 0 ? '+' : ''}${displayPercent(value)}`;

function Table({ label, children }: { label: string; children: ReactNode }) {
  return <div className="table-shell" tabIndex={0} role="region" aria-label={label}><table className="data-table validation-table">{children}</table></div>;
}

/** Situação de cada modelo da rodada frente ao oficial; indisponível e falha nunca viram erro zero. */
export function resultBadge(result: BenchmarkResult) {
  if (result.status === 'unavailable') return <Badge tone="neutral">Não rodou</Badge>;
  if (result.status === 'failed') return <Badge tone="critical">Falhou</Badge>;
  if (result.is_official) return <Badge tone="info">Em uso</Badge>;
  if (result.beats_official === null) return <Badge tone="neutral">Sem comparação</Badge>;
  return result.beats_official ? <Badge tone="good">Erra menos que o oficial</Badge> : <Badge tone="medium">Erra mais que o oficial</Badge>;
}

function resultNote(result: BenchmarkResult) {
  const parts = [`Biblioteca: ${result.library}${result.library_version ? ` ${result.library_version}` : ''}.`, `Tempo da rodada: ${result.duration_seconds.toLocaleString('pt-BR')} s.`];
  if (result.fallback_points) parts.push(`Em ${result.fallback_points} de ${result.evaluated_points} pontos o modelo não previu e valeu a previsão oficial.`);
  if (result.error_message) parts.push(result.error_message);
  return parts.join(' ');
}

function OfficialModel({ card }: { card: ModelCard }) {
  const evaluation = card.evaluation;
  const peaks = evaluation ? evaluation.peak_months.map((month) => MONTHS[month - 1]).join(', ') : '';
  return <SectionCard title="Modelo em uso">
    <p className="fact-line"><strong>{card.target.what}</strong>, {card.horizon_months} meses à frente, para {card.data.skus_with_forecast} de {card.data.skus} SKUs. Fonte: {card.target.source}.</p>
    <Table label="Modelos da previsão oficial, na ordem em que são tentados">
      <thead><tr><th>Modelo</th><th>Histórico mínimo</th><th>SKUs</th></tr></thead>
      <tbody>{card.models.map((model) => <tr key={model.model}>
        <td><strong>{model.label}</strong> <Tooltip label={`Sobre: ${model.label}`}>{model.description}</Tooltip></td>
        <td>{model.min_history_months} meses</td>
        <td>{model.skus}</td>
      </tr>)}</tbody>
    </Table>
    {evaluation
      ? <p className="fact-line">Erro medido: <strong>{displayPercent(evaluation.wape)}</strong> no total e {displayPercent(evaluation.peak_wape)} nos picos ({peaks}); viés {signed(evaluation.bias)}. <Tooltip label="Como o erro é medido">{`Em cada uma das ${evaluation.origins.length} datas passadas (${evaluation.origins[0]} a ${evaluation.origins[evaluation.origins.length - 1]}), o modelo usa só os meses até ela e prevê os ${evaluation.horizon_months} seguintes. ${evaluation.metric}. Viés negativo: a previsão ficou abaixo do vendido.`}</Tooltip></p>
      : <p className="fact-line">O motor em uso não tem a avaliação rolante.</p>}
    <p className="fact-line">Confiança por SKU: {card.confidence.skus['alta'] ?? 0} alta, {card.confidence.skus['média'] ?? 0} média, {card.confidence.skus['baixa'] ?? 0} baixa. <Tooltip label="Regra de confiança">{card.confidence.rule}</Tooltip></p>
  </SectionCard>;
}

function Benchmark({ benchmark }: { benchmark: ModelBenchmarkSection }) {
  if (benchmark.status === 'no_run') {
    return <SectionCard title="Modelos comparados"><p className="fact-line">{benchmark.note}</p></SectionCard>;
  }
  const { run } = benchmark;
  return <SectionCard title="Modelos comparados">
    {benchmark.stale && <div className="ui-alert ui-alert-warning" role="status"><div>{benchmark.note}</div></div>}
    <Table label="Modelos comparados com o oficial nas mesmas datas">
      <thead><tr><th>Modelo</th><th>Erro total · nos picos</th><th>Viés</th><th>Situação</th></tr></thead>
      <tbody>{run.results.map((result) => <tr key={result.model}>
        <td><strong>{result.label}</strong> <Tooltip label={`Detalhes: ${result.label}`}>{resultNote(result)}</Tooltip></td>
        <td>{displayPercent(result.wape)} · {displayPercent(result.peak_wape)}</td>
        <td>{signed(result.bias)}</td>
        <td>{resultBadge(result)}</td>
      </tr>)}</tbody>
    </Table>
    <p className="fact-line">Rodada de {formatDateTime(run.created_at)}. Trocar o modelo oficial exige os critérios de promoção; esta tabela é só evidência.</p>
    {benchmark.history.length > 1 && <details className="validation-details"><summary>Rodadas anteriores</summary>
      <Table label="Histórico de rodadas do benchmark">
        <thead><tr><th>Rodada</th><th>Data</th><th>Modelos</th><th>Menor erro</th></tr></thead>
        <tbody>{benchmark.history.map((item) => <tr key={item.id}>
          <td>{item.id}</td><td>{formatDateTime(item.created_at)}</td><td>{item.models}</td>
          <td>{item.best_model ?? 'Não disponível'} · {displayPercent(item.best_wape)}</td>
        </tr>)}</tbody>
      </Table>
    </details>}
  </SectionCard>;
}

/** Confiança › Modelo de previsão: o que o modelo prevê, sob quais premissas, e como se compara a outros modelos. */
export default function ModelPage({ refreshToken }: { refreshToken: number }) {
  const { data, error, loading, loadedAt } = useApiResource(api.modelBenchmark, refreshToken);
  usePageLoadStatus(loading, data ? '' : error, loadedAt);
  if (!data && loading) return <LoadingState />;
  if (!data) return <p className="fact-line">Informações do modelo indisponíveis no momento.</p>;
  const card = data.official;

  return <div className="revenue-page">
    <PageIntro title="O que o modelo prevê e quanto erra" description={card.engine_label} />
    <OfficialModel card={card} />
    <SectionCard title="Premissas">
      <ul className="validation-list">{card.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
    </SectionCard>
    <Benchmark benchmark={data.benchmark} />
    <details className="validation-details"><summary>Limitações</summary>
      <ul className="validation-list">{card.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
    </details>
  </div>;
}
