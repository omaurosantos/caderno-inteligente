import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { clearAnalysis, elapsedMinutes } from '../analysisTimer';
import { Badge, EmptyState, PageIntro, SectionCard } from '../components';
import { DEFAULT_TEXT_LIMITS, useSystemInfo } from '../hooks/useSystemInfo';
import type { PageProps } from './shared';
import { CHALLENGE_NAMES, decisionActionNames, formatDateTime, partnerDataEffectNames } from './shared';

export default function FeedbackPage({ data, onRefresh }: PageProps<'feedback' | 'priorities' | 'config'>) {
  const [params] = useSearchParams();
  const requestedSku = params.get('sku') ?? '';
  const requestedLabel = params.get('rotulo') ?? '';
  const skus = data.priorities.map((item) => item.sku);
  // Um SKU que veio do detalhe pode estar fora do ranking: ele continua sendo uma opção.
  const options = requestedSku && !skus.includes(requestedSku) ? [requestedSku, ...skus] : skus;
  // Sem ?sku= o campo começa vazio: a decisão nunca usa um SKU escolhido em silêncio.
  const [sku, setSku] = useState(requestedSku);
  const [action, setAction] = useState(data.config.actions[0] ?? 'aceita');
  const [user, setUser] = useState('');
  const [note, setNote] = useState('');
  const [partnerDataEffect, setPartnerDataEffect] = useState('nao_utilizado');
  const system = useSystemInfo();
  const limits = system?.text_limits ?? DEFAULT_TEXT_LIMITS;
  // Tempo medido desde a abertura do SKU (analysisTimer); enquanto o usuário não editar, acompanha o relógio e é recalculado no envio.
  const measured = (target: string) => { const minutes = elapsedMinutes(target, Date.now(), limits.analysis_minutes); return minutes === null ? '' : String(minutes); };
  const [analysisMinutes, setAnalysisMinutes] = useState(() => measured(requestedSku));
  const [minutesEdited, setMinutesEdited] = useState(false);
  const isMeasured = !minutesEdited && analysisMinutes !== '';
  useEffect(() => {
    if (minutesEdited) return undefined;
    setAnalysisMinutes(measured(sku));
    const timer = window.setInterval(() => setAnalysisMinutes(measured(sku)), 30_000);
    return () => window.clearInterval(timer);
  }, [sku, minutesEdited, limits.analysis_minutes]);
  // O rótulo mostrado no SKU só vale para o SKU de origem; se o usuário trocar de SKU, ele não é registrado.
  const label = requestedLabel in CHALLENGE_NAMES && sku === requestedSku ? requestedLabel : '';
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const writeDisabled = system?.write_enabled === false;
  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage(''); setError('');
    if (!sku) { setError('Escolha o SKU da decisão.'); return; }
    setSaving(true);
    const minutes = minutesEdited ? analysisMinutes : measured(sku);
    try { await api.createFeedback({ sku, action, user_name: user, note, partner_data_effect: partnerDataEffect, analysis_minutes: minutes === '' ? null : Number(minutes), ...(label ? { challenge_action: label } : {}) }); clearAnalysis(sku); setNote(''); setPartnerDataEffect('nao_utilizado'); setAnalysisMinutes(''); setMinutesEdited(false); await onRefresh(); setMessage('Decisão registrada com sucesso.'); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Falha ao registrar decisão.'); }
    finally { setSaving(false); }
  }
  return <>
    <PageIntro title="Histórico de decisões" description="Decisões já registradas pelo PCP. Para registrar uma nova, escolha o SKU." action={requestedSku ? <Link className="secondary-button" to={`/skus/${encodeURIComponent(requestedSku)}`}>Voltar ao SKU {requestedSku}</Link> : undefined} />
    <div className="feedback-layout">
      <SectionCard title="Nova decisão" className="form-card"><form className="stack-form" onSubmit={submit}>
        <label>SKU<select required value={sku} onChange={(event) => { setSku(event.target.value); setMinutesEdited(false); }}><option value="" disabled>Escolha um SKU</option>{options.map((item) => <option key={item}>{item}</option>)}</select></label>
        {label && <p className="fact-line">Rótulo registrado com a decisão: <strong>{CHALLENGE_NAMES[label]}</strong></p>}
        <label>O que você decidiu?<select value={action} onChange={(event) => setAction(event.target.value)}>{data.config.actions.map((item) => <option key={item} value={item}>{decisionActionNames[item] ?? item}</option>)}</select></label>
        <label>O dado do parceiro ajudou?<select value={partnerDataEffect} onChange={(event) => setPartnerDataEffect(event.target.value)}>{data.config.partner_data_effects.map((item) => <option key={item} value={item}>{partnerDataEffectNames[item] ?? item}</option>)}</select></label>
        <label>Tempo de análise em minutos <span className="optional-label">Opcional</span><input type="number" min="0" max={limits.analysis_minutes} step="1" value={analysisMinutes} onChange={(event) => { setMinutesEdited(true); setAnalysisMinutes(event.target.value); }} placeholder="Ex.: 15" aria-describedby={isMeasured ? 'analysis-measured' : undefined} /></label>
        {isMeasured && <p className="fact-line" id="analysis-measured">Tempo medido desde que você abriu o SKU; pode corrigir.</p>}
        <label>Usuário<input value={user} maxLength={limits.user_name} onChange={(event) => setUser(event.target.value)} placeholder="Seu nome" /></label><label>Observação<textarea value={note} maxLength={limits.note} onChange={(event) => setNote(event.target.value)} placeholder="Contexto da decisão" /></label>
        <div aria-live="polite">{message && <span className="form-message">{message}</span>}</div>{error && <span className="form-message" role="alert">{error}</span>}{writeDisabled && <p className="write-disabled-note" role="note">Registro desabilitado nesta publicação (somente leitura).</p>}<button className="primary-button" disabled={saving || writeDisabled}>{saving ? 'Salvando…' : 'Registrar decisão'}</button>
      </form></SectionCard>
      <SectionCard title="Histórico recente">{data.feedback.length ? <div className="feedback-list">{data.feedback.map((item, index) => <article key={`${item.sku}-${item.created_at}-${index}`}><div className="feedback-head"><strong>{item.sku}</strong><Badge tone={item.action === 'aceita' ? 'good' : item.action === 'rejeitada' ? 'low' : 'medium'}>{decisionActionNames[item.action] ?? item.action}</Badge><Badge tone={item.partner_data_effect === 'alterou_decisao' ? 'good' : item.partner_data_effect === 'aumentou_confianca' ? 'medium' : 'neutral'}>{partnerDataEffectNames[item.partner_data_effect] ?? item.partner_data_effect}</Badge></div><p>{item.note || 'Sem observação.'}</p><div className="feedback-meta"><span>{item.analysis_minutes === null ? 'Tempo não informado' : `${item.analysis_minutes} min de análise`}</span><span>{item.user_name || 'Usuário não informado'} · {formatDateTime(item.created_at)}</span></div></article>)}</div> : <EmptyState title="Nenhuma decisão registrada" description="O feedback do PCP aparecerá aqui." />}</SectionCard>
    </div>
  </>;
}
