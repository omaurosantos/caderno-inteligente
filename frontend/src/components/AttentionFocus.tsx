import { useState } from 'react';
import { Badge, Icon, confidenceTone, mainReason, severityTone } from '../components';
import { formatDate, positiveDelayDays, reasonNames, sortReasons } from '../pages/shared';
import type { Priority, SelectedSku } from '../types';

/** O cartão navega entre os primeiros da fila; a ordem é a da fila de atenção. */
const FOCUS_COUNT = 3;

/**
 * Cartão "Primeiro da fila" (Planejamento): o SKU que pede atenção primeiro, com setas entre os três primeiros.
 * Sem prioridades, não aparece; a lista abaixo dele explica o que falta.
 */
export function AttentionFocus({ priorities, weights, onSelect }: { priorities: Priority[]; weights?: Record<string, number>; onSelect: (item: SelectedSku) => void }) {
  const top = priorities.slice(0, FOCUS_COUNT);
  const [index, setIndex] = useState(0);
  // Circular (3 → 1): o botão em foco nunca fica desabilitado, então quem usa teclado não perde o lugar.
  const go = (step: number) => setIndex((current) => (current + step + top.length) % top.length);
  const first = top[Math.min(index, top.length - 1)];
  if (!first) return null;
  const main = mainReason(first.reasons, weights);
  const delay = positiveDelayDays(first.first_promised_date, first.first_production_completion);
  return <article className="attention-focus" aria-label="Primeiros da fila de atenção" onKeyDown={(event) => {
    if (top.length < 2 || !(event.target instanceof HTMLElement) || !event.target.closest('.focus-nav')) return;
    if (event.key === 'ArrowRight') { event.preventDefault(); go(1); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(-1); }
  }}>
    <div>
      <div className="focus-head">
        <span className="eyebrow">{index === 0 ? `Primeiro da fila · posição ${first.priority}` : `Posição ${first.priority} da fila`}</span>
        {top.length > 1 && <div className="focus-nav" role="group" aria-label="Navegar entre os primeiros da fila">
          <button type="button" className="icon-button focus-nav-button" onClick={() => go(-1)} aria-label="SKU anterior da fila"><span className="icon-flip"><Icon name="arrow" size={18} /></span></button>
          <span className="focus-nav-count" aria-hidden="true">{index + 1} de {top.length}</span>
          <button type="button" className="icon-button focus-nav-button" onClick={() => go(1)} aria-label="Próximo SKU da fila"><Icon name="arrow" size={18} /></button>
        </div>}
      </div>
      <p className="sr-only" role="status">{`Mostrando ${index + 1} de ${top.length}: ${first.sku}, posição ${first.priority} da fila.`}</p>
      <h3>{first.sku} <span>{first.product}</span></h3>
      <p className="answer-line"><strong>{reasonNames[main?.code ?? ''] ?? main?.description ?? 'Sem motivo registrado'}.</strong>{delay !== null && ` Produção prevista para ${formatDate(first.first_production_completion)}, ${delay} ${delay === 1 ? 'dia' : 'dias'} depois da data prometida.`}</p>
      <div className="focus-badges">{sortReasons(first.reasons, weights).slice(0, 3).map(reason => <Badge key={reason.code} tone={severityTone(reason.severity)}>{reasonNames[reason.code] ?? reason.description}</Badge>)}<Badge tone={confidenceTone(first.confidence)}>Confiança nos dados: {first.confidence}</Badge></div>
    </div>
    <div className="focus-actions">
      <button className="primary-button" onClick={() => onSelect(first)}>Abrir evidências de {first.sku}<Icon name="arrow" /></button>
    </div>
  </article>;
}
