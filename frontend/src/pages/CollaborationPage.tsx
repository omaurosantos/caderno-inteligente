import { useCallback, useState } from 'react';
import { api } from '../api';
import { Alert, Badge, ErrorState, LoadingState, PageIntro, SectionCard } from '../components';
import { monthLabel } from '../components/CommercialMatrix';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import type { CollaborationGap } from '../types-collaboration';

const pct = (value: number | null | undefined, digits = 0) => value == null ? 'Não disponível' : `${(value * 100).toLocaleString('pt-BR', { maximumFractionDigits: digits })}%`;
const num = (value: number | null | undefined) => value == null ? 'Não disponível' : value.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
const gapsText = (gaps: CollaborationGap[]) => gaps.length ? gaps.map(g => g.text).join('; ') : 'Critérios atendidos';

/** Programa de Colaboração: o que cada parceiro compartilha, em que nível está e o que muda ao subir de nível. Proposta a validar. */
export default function CollaborationPage({ refreshToken }: { refreshToken: number }) {
  const loader = useCallback((signal: AbortSignal) => api.collaboration(signal), []);
  const { data, error, loading, loadedAt, refresh } = useApiResource(loader, refreshToken);
  usePageLoadStatus(loading, error, loadedAt);
  const [chosen, setChosen] = useState<string | null>(null);
  if (!data) return error ? <ErrorState message={error} onRetry={() => void refresh()} /> : <LoadingState />;
  const { program } = data;
  const partner = data.partners.find(p => p.code === chosen) ?? data.partners[0];
  return <>
    <PageIntro title="Colaboração com parceiros" description={`Quanto cada parceiro compartilha e o que muda ao compartilhar mais. Dados até ${monthLabel(data.reference_month)}.`} />
    <Alert title="Proposta a validar">{data.note} Os benefícios são hipóteses, não concessões.</Alert>
    <SectionCard title="Linha de base do programa" subtitle="Fotografia da base atual, sem histórico de envios">
      <div className="table-shell" tabIndex={0} role="region" aria-label="Linha de base do programa"><table className="data-table responsive-table"><thead><tr><th>Indicador</th><th>Valor</th><th>Como ler</th></tr></thead><tbody>
        <tr><td data-label="Indicador">Adesão</td><td data-label="Valor">{program.participating_partners} de {program.eligible_partners} parceiros ({pct(program.adhesion)})</td><td data-label="Como ler">Parceiros com algum sell-out</td></tr>
        <tr><td data-label="Indicador">Cobertura da matriz parceiro × SKU</td><td data-label="Valor">{pct(program.matrix_coverage)} ({num(program.matrix_pairs_observed)} de {num(program.matrix_pairs_total)})</td><td data-label="Como ler">Pares com sell-out informado; o resto é lacuna, não venda zero</td></tr>
        <tr><td data-label="Indicador">Índice de Colaboração médio</td><td data-label="Valor">{pct(program.mean_index)}</td><td data-label="Como ler">Média dos seis componentes, com pesos propostos</td></tr>
        {program.by_level.filter(l => l.partners > 0).map(l => <tr key={l.level}><td data-label="Indicador">Parceiros no nível {l.level ? `${l.level} (${l.name})` : l.name}</td><td data-label="Valor">{l.partners}</td><td data-label="Como ler">Classificação demonstrativa</td></tr>)}
      </tbody></table></div>
      <p className="fact-line">{program.reconciliation}</p>
      <p className="fact-line"><strong>Evolução:</strong> {program.evolution_reason}</p>
      <p className="fact-line"><strong>Decisões que mudaram com o dado do parceiro:</strong> {program.decisions.reason}</p>
    </SectionCard>
    <SectionCard title="Índice e nível por parceiro" subtitle="Escolha um parceiro para simular os próximos níveis">
      <div className="table-shell" tabIndex={0} role="region" aria-label="Parceiros do programa; role horizontalmente para ver todas as colunas"><table className="data-table responsive-table"><thead><tr><th>Parceiro</th><th>Nível</th><th>Índice</th><th>Para o próximo nível</th><th><span className="sr-only">Simular</span></th></tr></thead><tbody>
        {data.partners.map(p => <tr key={p.code}>
          <td data-label="Parceiro"><strong>{p.name}</strong><small>{p.code} · {p.type}</small></td>
          <td data-label="Nível"><Badge tone={p.level ? 'ok' : 'warning'}>{p.level ? `${p.level} · ${p.level_name}` : p.level_name}</Badge></td>
          <td data-label="Índice">{pct(p.index)}</td>
          <td data-label="Para o próximo nível">{p.next_level ? `${p.next_level}: ${gapsText(p.gaps)}` : 'Nível máximo'}</td>
          <td data-label="Simular"><button className="secondary-button" aria-pressed={p.code === partner.code} onClick={() => setChosen(p.code)}>Simular {p.code}</button></td>
        </tr>)}
      </tbody></table></div>
    </SectionCard>
    <SectionCard title={`Como o índice de ${partner.name} é calculado`} subtitle="Cada componente é calculado a partir do sell-out observado">
      {partner.dimensions ? <div className="table-shell" tabIndex={0} role="region" aria-label="Componentes do índice"><table className="data-table responsive-table"><thead><tr><th>Componente</th><th>Valor</th><th>Peso</th><th>Base do cálculo</th></tr></thead><tbody>
        {partner.dimensions.map(d => <tr key={d.key}><td data-label="Componente">{d.label}</td><td data-label="Valor">{pct(d.value)}</td><td data-label="Peso">{pct(d.weight)}</td><td data-label="Base do cálculo">{d.basis}</td></tr>)}
      </tbody></table></div> : <p className="fact-line">Sem sell-out na base: ausência é lacuna de informação, não venda zero.</p>}
    </SectionCard>
    <SectionCard title={`Simulação: o que muda para ${partner.name}`} subtitle="Efeito esperado sobre os dados desta base; não é garantia nem acordo comercial">
      {!partner.scenarios.length ? <p className="fact-line">O parceiro já está no nível máximo.</p> : <div className="table-shell" tabIndex={0} role="region" aria-label="Simulação de níveis"><table className="data-table responsive-table"><thead><tr><th>Se chegar a</th><th>O que falta</th><th>SKUs a acrescentar</th><th>Linhas com estoque estimado que passam a observado</th><th>Carteira que passa a ter dado</th><th>Contrapartida potencial (hipótese)</th></tr></thead><tbody>
        {partner.scenarios.map(s => <tr key={s.level}>
          <td data-label="Se chegar a"><strong>{s.level} · {s.name}</strong></td>
          <td data-label="O que falta">{gapsText(s.gaps)}</td>
          <td data-label="SKUs a acrescentar">{s.additional_skus ? <>{s.additional_skus}<small>{s.unlocked.candidate_skus.length ? `Comece por ${s.unlocked.candidate_skus.map(c => c.sku).join(', ')} (pedidos em carteira)` : 'Sem pedidos em carteira nos SKUs sem sell-out'}</small></> : 'Nenhum'}</td>
          <td data-label="Linhas com estoque estimado">{s.rows_with_estimated_stock ? num(s.rows_with_estimated_stock) : 'Nenhuma'}</td>
          <td data-label="Carteira coberta">{s.unlocked.covered_orders ? `${num(s.unlocked.covered_backlog_quantity)} un. em ${s.unlocked.covered_orders} pedido(s)` : 'Nenhuma'}</td>
          <td data-label="Contrapartida potencial">{s.gives}</td>
        </tr>)}
      </tbody></table></div>}
    </SectionCard>
    <details className="fact-line"><summary>Limitações da proposta</summary><ul>{data.limitations.map(l => <li key={l}>{l}</li>)}</ul></details>
  </>;
}
