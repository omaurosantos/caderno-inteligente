import { useCallback, useEffect } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { startAnalysis } from '../analysisTimer';
import { AllocationBlock } from '../components/AllocationBlock';
import { PartnerSkuContext } from '../components/PartnerSkuContext';
import { ChallengeBadge, ChallengeLever } from '../components/ChallengeAction';
import { SkuEventsBlock, UrgentEventLine } from '../components/EventAlerts';
import { TabBar, TabPanel } from '../components/Tabs';
import { SkuRevenueBlock } from '../components/RevenueForecast';
import { SupplyPlanBlock } from '../components/SupplyPlan';
import { Alert, Badge, ErrorState, Hint, PageIntro, confidenceTone, severityTone } from '../components';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { displayDays, displayNumber, displayPercent, displayQuantity, displayUnits, formatDate, missingDataNames, positiveDelayDays, reasonNames } from './shared';

/** Only same-app paths: blocks '//host', backslash tricks and schemes (open-redirect hardening). */
export function isInternalPath(value: string) {
  return value.startsWith('/') && !value.startsWith('//') && !value.includes('\\') && !/[\u0000-\u001f]/.test(value);
}

type EvidenceKind = 'share' | 'days' | 'units' | 'date' | 'text' | 'count';
const evidenceFields: Record<string, [string, EvidenceKind]> = {
  family: ['Família', 'text'],
  average_occupation: ['Ocupação média da família', 'share'],
  available_capacity_average: ['Capacidade livre média (un. por semana)', 'units'],
  first_promised_date: ['Primeira data prometida', 'date'],
  first_production_completion: ['Primeira conclusão prevista', 'date'],
  delay_days: ['Atraso entre promessa e conclusão', 'days'],
  coverage_days: ['Cobertura do estoque', 'days'],
  lead_time_days: ['Prazo de produção (lead time)', 'days'],
  safety_stock_days: ['Estoque de segurança', 'days'],
  sell_out_partner_count: ['Parceiros com sell-out', 'count'],
  sell_out_visibility: ['Visibilidade de sell-out', 'text'],
  backlog_order_quantity: ['Carteira de pedidos', 'units'],
  production_order_quantity: ['Produção aberta', 'units'],
  excess_coverage_days: ['Limite de cobertura em excesso', 'days'],
};

function evidenceValue(code: string, key: string, value: unknown) {
  if (value === null || value === undefined) return 'Não disponível';
  const kind: EvidenceKind = code === 'CAPACITY_CONFLICT' && key === 'threshold' ? 'share' : evidenceFields[key]?.[1] ?? 'text';
  if (typeof value === 'number') {
    if (kind === 'share') return displayPercent(value);
    if (kind === 'days') return displayDays(value);
    if (kind === 'units') return displayUnits(value);
    return displayQuantity(value);
  }
  if (kind === 'date' && typeof value === 'string') return formatDate(value);
  return String(value);
}

const evidenceLabel = (code: string, key: string) => code === 'CAPACITY_CONFLICT' && key === 'threshold' ? 'Limite configurado de ocupação'
  : evidenceFields[key]?.[0] ?? key.split('_').join(' ').replace(/^./, (letter) => letter.toUpperCase());

function shortOrigin(origin: string) {
  if (origin.startsWith('config.')) return 'Configuração';
  return `Planilha, aba ${origin.split('.')[0].split('_').join(' ')}`;
}

const TABS = [
  { id: 'resumo', label: 'Resumo' },
  { id: 'evidencias', label: 'Evidências' },
  { id: 'parceiros', label: 'Parceiros' },
  { id: 'impacto', label: 'Impacto financeiro' },
] as const;
export type SkuTab = (typeof TABS)[number]['id'];
const isTab = (value: string | null): value is SkuTab => TABS.some((tab) => tab.id === value);

export type AnswerTone = 'info' | 'review' | 'blocked' | 'success';

/** Aparência do cartão de resposta: só reflete o que a recomendação já diz; azul é sugestão, âmbar exige revisão. Verde/vermelho não são produzidos aqui (nenhuma ação do SKU é "concluída" ou bloqueada). */
export function answerToneFor(action: string, capacityStatus: string, confidence: string, rankingConfidence: string, insufficient: boolean): AnswerTone {
  if (insufficient || action === 'investigar_dados' || action === 'produzir_validar_capacidade' || action === 'rever_op' || capacityStatus === 'requires_review'
    || confidence === 'baixa' || rankingConfidence === 'baixa') return 'review';
  return 'info';
}

export default function SkuDetailPage({ refreshToken }: { refreshToken: number }) {
  const { sku = '' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requestedTab = params.get('tab');
  const tab: SkuTab = isTab(requestedTab) ? requestedTab : 'resumo';
  // Troca de aba mantém o estado de origem do "Voltar" e não empilha histórico.
  const selectTab = (next: SkuTab) => { const query = new URLSearchParams(params); if (next === 'resumo') query.delete('tab'); else query.set('tab', next); setParams(query, { replace: true, state: location.state }); };
  const loader = useCallback((signal: AbortSignal) => api.skuDetail(sku, signal), [sku]);
  const { data: detail, error, loading, loadedAt, refresh: load } = useApiResource(loader, refreshToken);
  usePageLoadStatus(loading, error, loadedAt);
  // Etapa 16.7: o tempo de análise conta a partir da abertura do detalhe (só no navegador; o formulário de decisão o pré-preenche).
  useEffect(() => { startAnalysis(sku); }, [sku]);
  const backTarget = typeof location.state === 'object' && location.state && 'from' in location.state && typeof location.state.from === 'string' && isInternalPath(location.state.from) ? location.state.from : '/fila';

  if (error && !detail) return <div className="sku-detail-page"><PageIntro title={sku || 'SKU não informado'} description="Não foi possível carregar as evidências deste item." action={<button className="secondary-button" onClick={() => navigate(backTarget)}>Voltar</button>} /><ErrorState message={error} onRetry={() => void load()} /></div>;
  if (!detail) return <div className="sku-detail-page"><PageIntro title={sku || 'Detalhe do SKU'} description="Buscando indicadores, previsão, recomendação e evidências." action={<button className="secondary-button" onClick={() => navigate(backTarget)}>Voltar</button>} /><div className="drawer-loading"><span /><span /><span /></div></div>;

  const indicator = detail.indicator;
  const forecast = detail.forecast;
  const recommendation = detail.operational_recommendation;
  const calc = recommendation.calculation;
  const rankedPriority = detail.priority[0];
  const priorityNumber = rankedPriority?.priority ?? null;
  const attentionScore = rankedPriority?.attention_score ?? null;
  const rankingConfidence = rankedPriority?.confidence ?? recommendation.confidence;
  const delayDays = positiveDelayDays(indicator.first_promised_date, indicator.first_production_completion);
  const insufficient = forecast.status === 'insufficient_data';
  const quantity = recommendation.suggested_quantity;
  const answerTone = answerToneFor(recommendation.action, recommendation.capacity_status, recommendation.confidence, rankingConfidence, insufficient);
  const answer = insufficient ? `${recommendation.action_label}: sem histórico suficiente para sugerir quantidade.`
    : `${recommendation.action_label}${quantity && quantity > 0 ? ` · ${displayQuantity(quantity)} un.` : ''}`;
  const why = `Necessidade: ${displayQuantity(calc.demand_to_cover)} a cobrir + ${displayQuantity(calc.safety_stock_quantity)} de segurança − ${displayQuantity(calc.current_stock)} em estoque − ${displayQuantity(calc.open_production_quantity)} em produção${recommendation.raw_quantity === null ? '' : ` = ${displayQuantity(recommendation.raw_quantity)} un.`}${quantity && quantity > 0 ? `; arredondada ao lote mínimo de ${displayQuantity(recommendation.minimum_lot)}.` : '.'}`;
  const contributions = [...detail.score_contributions].sort((a, b) => b.weight - a.weight);

  return <div className="sku-detail-page">
    <PageIntro title={indicator.SKU} description={`${priorityNumber === null ? 'Fora do ranking oficial' : `Posição ${priorityNumber} na fila de atenção`} · ${indicator.Produto} · ${indicator.family}`} action={<button className="secondary-button" onClick={() => navigate(backTarget)}>Voltar</button>} />
    {error && <Alert title="Não foi possível atualizar o SKU" tone="warning" action={<button className="secondary-button" onClick={() => void load()}>Tentar novamente</button>}>{error} A última carga permanece exibida.</Alert>}
    <section className={`answer-card answer-card-${answerTone}`} data-tone={answerTone} aria-labelledby="answer-title">
      <div className="answer-main">
        <span className="eyebrow" id="answer-title">Ação operacional sugerida</span>
        <p className="answer-sentence">{answer}</p>
        {insufficient ? <p className="answer-why">{forecast.limitation}</p> : recommendation.planned_orders ? recommendation.rationale.map((line) => <p key={line} className="answer-why">{line}</p>) : <p className="answer-why">{why}</p>}
        {recommendation.action === 'sem_acao_necessaria' && <p className="answer-why">Sem produção neste horizonte; os riscos abaixo continuam.</p>}
        <ChallengeLever action={detail.challenge_action} />
        <div className="answer-badges"><ChallengeBadge action={detail.challenge_action} />{recommendation.capacity_status === 'requires_review' && <Badge tone="medium">Validar capacidade</Badge>}{insufficient ? <><Badge tone="medium">Dados insuficientes</Badge><Badge tone="medium">{recommendation.action_label}</Badge></> : <Badge tone="info">previsto</Badge>}</div>
        <div className="answer-actions">
          <Link className="primary-button" to={`/decisoes?sku=${encodeURIComponent(sku)}${detail.challenge_action ? `&rotulo=${detail.challenge_action.code}` : ''}`}>Registrar decisão</Link>
          <Link className="secondary-button" to={`/casos?sku=${encodeURIComponent(sku)}`}>Criar caso</Link>
        </div>
      </div>
      <div className="answer-figures">
        {!insufficient && <>
          <div className={quantity && quantity > 0 ? 'metric-recommendation' : ''}><span>Quantidade sugerida</span><strong>{displayQuantity(quantity)}</strong><small>unidades</small></div>
          <div><span>Previsão do próximo mês</span><strong>{displayQuantity(forecast.forecast_next_month)}</strong><small>unidades previstas</small></div>
        </>}
        <div><span>Confiança <Hint term="confianca_previsao" /></span><strong className="answer-confidence"><Badge tone={confidenceTone(recommendation.confidence)}>previsão {recommendation.confidence}</Badge><Badge tone={confidenceTone(rankingConfidence)}>dados {rankingConfidence}</Badge></strong><small>{rankedPriority?.confidence_reason ?? recommendation.confidence_reason}</small></div>
      </div>
      <p className="human-review-line"><strong>Revisão humana obrigatória</strong>{insufficient ? '. Sem histórico suficiente não há quantidade sugerida; ausência de previsão não equivale a demanda zero.' : '. A sugestão não cria nem libera ordem de produção.'}</p>
    </section>

    <TabBar tabs={TABS} active={tab} onChange={selectTab} label="Detalhes do SKU" prefix="sku" className="sku-tabs" />

    <TabPanel id="resumo" active={tab === 'resumo'} prefix="sku">
      <UrgentEventLine alerts={detail.event_alerts} onOpen={() => selectTab('evidencias')} />
      <AllocationBlock allocation={detail.allocation} />
      <p className="fact-line">{indicator.missing_data.length > 0 ? <><strong>Dados ausentes:</strong> {indicator.missing_data.map((field) => missingDataNames[field] ?? field.split('_').join(' ')).join(', ')} (ausência não é zero).</> : <><strong>Dados ausentes:</strong> nenhum nos campos desta análise.</>}</p>
      {recommendation.capacity_status === 'requires_review' && <p className="fact-line"><strong>Capacidade:</strong> {recommendation.capacity?.status === 'insuficiente' ? <>{displayQuantity(recommendation.capacity.unscheduled_quantity)} un. planejadas não cabem na linha até a data de necessidade. <Link to="/capacidade">Ver capacidade</Link>.</> : 'valide a capacidade da família antes de produzir.'}</p>}
      {recommendation.planned_orders && <p className="fact-line">Plano datado, ordens e projeção semanal em <button type="button" className="link-button" onClick={() => selectTab('evidencias')}>Evidências</button>.</p>}
      <p className="fact-line">Cálculo, riscos e origem dos dados estão em <button type="button" className="link-button" onClick={() => selectTab('evidencias')}>Evidências</button>.</p>
    </TabPanel>

    <TabPanel id="evidencias" active={tab === 'evidencias'} prefix="sku">
      {insufficient && <SkuEventsBlock alerts={detail.event_alerts} scenario={detail.event_scenario} />}
      {!insufficient && <details className="detail-block" open>
        <summary>Sobre a previsão</summary>
        <p className="fact-line">Tendência <strong className={`trend-${forecast.trend}`}>{forecast.trend}</strong>{forecast.trend_change_ratio === null ? '' : ` (${displayPercent(forecast.trend_change_ratio)})`} · modelo {forecast.model_label} · previsão de 3 meses <strong>{displayUnits(forecast.forecast_total_3m)}</strong> <Badge tone="info">previsto</Badge> · erro médio de {displayPercent(forecast.backtest_wape)} {forecast.engine === 'v2' ? `em ${forecast.backtest_windows} testes com meses de pico` : 'no teste dos últimos 3 meses'} <Hint term="wape" /></p>
        <SkuEventsBlock embedded alerts={detail.event_alerts} scenario={detail.event_scenario} />
      </details>}
      {!insufficient && recommendation.planned_orders && <SupplyPlanBlock recommendation={recommendation} allocated={Boolean(detail.allocation?.orders.length)} />}
    <details className="detail-block">
      <summary>Dados do SKU</summary>
      <dl className="fact-list">
        <div><dt>Estoque atual</dt><dd>{displayUnits(indicator.current_stock)}</dd></div>
        <div><dt>Carteira de pedidos</dt><dd>{displayUnits(indicator.backlog_order_quantity)}</dd></div>
        <div><dt>Produção aberta</dt><dd>{displayUnits(indicator.production_order_quantity)}</dd></div>
        <div><dt>Cobertura do estoque <Hint term="cobertura" /></dt><dd>{displayDays(indicator.coverage_days_calculated)}{indicator.data_quality_warnings?.includes('REGISTERED_DEMAND_DIVERGENCE') && <small> · cadastro: {displayDays(indicator.coverage_days_registered)}</small>}</dd></div>
        <div><dt>Prazo de produção <Hint term="leadtime" /></dt><dd>{displayDays(indicator.lead_time_days)}</dd></div>
        <div><dt>Vendido pelos parceiros (sell-out)</dt><dd>{displayUnits(indicator.sell_out_quantity)}</dd></div>
        <div><dt>Parceiros com sell-out</dt><dd>{displayNumber(indicator.sell_out_partner_count)}</dd></div>
        <div><dt>Previsão comercial (planilha)</dt><dd>{displayUnits(indicator.forecast_quantity)} <Badge tone="info">previsto</Badge></dd></div>
      </dl>
      <p className="fact-line">{indicator.first_promised_date ? `Prometido para ${formatDate(indicator.first_promised_date)}` : 'Sem data prometida'} · {indicator.first_production_completion ? `produção prevista para ${formatDate(indicator.first_production_completion)}${delayDays !== null ? ` (${delayDays} ${delayDays === 1 ? 'dia' : 'dias'} depois)` : ''}` : 'sem conclusão de produção prevista'}</p>
    </details>

    <details className="detail-block" open>
      <summary>Riscos e evidências</summary>
      <p className="score-sum">{attentionScore === null ? 'SKU fora do ranking oficial.' : <>Pontos de atenção <Hint term="score" />: <strong>{attentionScore}</strong>{contributions.length > 0 && <> = {contributions.map((item, index) => <span key={item.code}>{index > 0 && ' + '}<strong>{item.weight}</strong> ({reasonNames[item.code] ?? item.code})</span>)}</>}</>}</p>
      {detail.issues.map((issue) => <article className="issue-card" key={issue.code}><div><Badge tone={severityTone(issue.severity)}>{issue.severity}</Badge><strong>{reasonNames[issue.code] ?? issue.code}</strong></div><dl>{Object.entries(issue.values_used).map(([key, value]) => <div key={key}><dt>{evidenceLabel(issue.code, key)}</dt><dd>{evidenceValue(issue.code, key, value)}</dd></div>)}</dl><small>Origem: {[...new Set(issue.data_origin.map(shortOrigin))].join(' · ')}</small></article>)}
    </details>
    </TabPanel>

    <TabPanel id="parceiros" active={tab === 'parceiros'} prefix="sku">
      <PartnerSkuContext sku={sku} refreshToken={refreshToken} />
    </TabPanel>

    <TabPanel id="impacto" active={tab === 'impacto'} prefix="sku">
      <SkuRevenueBlock item={detail.revenue_forecast} />
    </TabPanel>
  </div>;
}
