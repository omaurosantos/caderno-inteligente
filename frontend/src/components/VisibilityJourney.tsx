import { SectionCard, Tooltip } from '../components';
import type { JourneyChannelType, VisibilityJourney as Journey, VisibilitySource } from '../types';
import { displayPercent, displayUnits } from '../pages/shared';

export const visibilitySourceLabels: Record<VisibilitySource, string> = { sell_out_parceiro: 'Sell-out do parceiro', faturamento_direto: 'Venda direta (faturamento)' };

const share = (part: number, total: number) => total > 0 ? part / total : null;

function ChannelRow({ channel }: { channel: JourneyChannelType }) {
  return <tr>
    <td data-label="Tipo de canal"><strong>{channel.type}</strong></td>
    <td data-label="De onde vem">{visibilitySourceLabels[channel.visibility_source]}</td>
    <td className="num" data-label="Faturado">{displayUnits(channel.billed_units)}</td>
    <td className="num" data-label="Venda observada">{displayUnits(channel.observed_consumer_units)} <small>{displayPercent(channel.share_observed)}</small>
      {channel.exceeds_billing && <Tooltip label="Sell-out acima do faturado">Sell-out informado: {displayUnits(channel.observed_consumer_units_raw)}, acima do faturado; a conta usa o faturado como teto.</Tooltip>}</td>
    <td className="num" data-label="Sem visibilidade">{displayUnits(channel.without_visibility_units)}</td>
  </tr>;
}

/** Jornada do faturado até a venda ao consumidor: o que é observado (faturamento direto e sell-out informado) e o que fica sem visibilidade (calculado). */
export function VisibilityJourney({ journey }: { journey: Journey }) {
  const observed = share(journey.observed_consumer_units, journey.total_units);
  const without = share(journey.without_visibility_units, journey.total_units);
  const natures = Object.values(journey.nature);
  return <SectionCard title="Quanto da venda ao consumidor é observado" action={<Tooltip label="Natureza dos números">{journey.note}</Tooltip>}>
    <p className="summary-line">{observed === null ? 'Sem faturamento na janela.' : <>Últimos {journey.window_months.length} meses: <strong>{displayPercent(observed)}</strong> do faturado tem venda ao consumidor observada; <strong>{displayPercent(without)}</strong> está sem visibilidade.</>}</p>
    {observed !== null && <div role="img" aria-label={`Observado ${displayPercent(observed)}, sem visibilidade ${displayPercent(without)}`} style={{ display: 'flex', height: 14, margin: '8px 0', border: '1px solid var(--rule)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
      <span style={{ width: `${observed * 100}%`, background: 'var(--ok-bar)' }} />
      <span style={{ flex: 1, background: 'repeating-linear-gradient(45deg, var(--series-other) 0 4px, var(--sheet) 4px 8px)' }} />
    </div>}
    <div className="table-shell" tabIndex={0} role="region" aria-label="Visibilidade por tipo de canal; role horizontalmente para ver todas as colunas"><table className="data-table responsive-table"><thead><tr><th>Tipo de canal</th><th>De onde vem</th><th className="num">Faturado</th><th className="num">Venda observada</th><th className="num">Sem visibilidade</th></tr></thead>
      <tbody>{journey.by_channel_type.map(channel => <ChannelRow key={channel.type} channel={channel} />)}</tbody></table></div>
    {natures.length > 0 && <p className="summary-line">{natures.join('. ')}.</p>}
  </SectionCard>;
}
