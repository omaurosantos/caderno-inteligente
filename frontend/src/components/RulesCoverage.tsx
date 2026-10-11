import { Link } from 'react-router-dom';
import { Badge, Tooltip } from '../components';
import { displayCurrency, displayQuantity } from '../pages/shared';
import type { PrecedenceLine, RuleCoverage, RulesCoverage as RulesCoverageData } from '../types-rules';

const LEVEL_NAMES: Record<PrecedenceLine['level'], string> = { operational: 'SKU', commercial: 'Comercial', partner: 'Parceiro', channel: 'Canal' };
const LEVEL_SHORT: Record<keyof NonNullable<RuleCoverage['fires_by_level']>, string> = { sku: 'SKU', commercial: 'comercial', partner: 'parceiro', channel: 'canal' };

/** Quando a regra não disparou: o motivo, o dado que faltaria e o caso que prova a regra. Sem motivo registrado, diz isso em vez de omitir. */
function ZeroExplanation({ rule }: { rule: RuleCoverage }) {
  const reference = rule.reference_case;
  return <div className="coverage-zero">
    <span>{rule.zero_reason ?? 'Sem motivo registrado para o zero; verificar.'}</span>
    {rule.data_needed && <small>Dado necessário: {rule.data_needed}</small>}
    {reference && <small><Badge tone={reference.origin === 'synthetic' ? 'medium' : 'neutral'} title={reference.origin === 'synthetic' ? 'A regra foi provada com entrada sintética; ela não ocorreu na operação.' : 'Caso real da base.'}>{reference.origin === 'synthetic' ? 'sintético' : 'base real'}</Badge> {reference.case}: {reference.title}</small>}
  </div>;
}

function RuleTable({ title, rules, operational }: { title: string; rules: RuleCoverage[]; operational: boolean }) {
  if (!rules.length) return null;
  return <div className="table-shell" tabIndex={0} role="region" aria-label={title}><table className="data-table coverage-table">
    <caption>{title}</caption>
    <thead><tr><th>{operational ? 'Sinal' : 'Rótulo'}</th><th>Disparos</th><th>{operational ? 'Peso' : 'Por nível'}</th><th>Se zero: por quê</th></tr></thead>
    <tbody>{rules.map((rule) => <tr key={`${rule.kind}-${rule.rule}`} className={rule.fires === 0 ? 'is-zero' : undefined}>
      <td><strong>{rule.label}</strong><small title={rule.condition}>{rule.condition}</small></td>
      <td><strong>{displayQuantity(rule.fires)}</strong></td>
      <td>{operational ? (typeof rule.weight === 'number' ? displayQuantity(rule.weight) : '—') : (rule.fires_by_level ? (Object.keys(LEVEL_SHORT) as Array<keyof typeof LEVEL_SHORT>).filter((level) => rule.fires_by_level![level] > 0).map((level) => `${LEVEL_SHORT[level]} ${rule.fires_by_level![level]}`).join(', ') || '—' : '—')}</td>
      <td>{rule.fires === 0 ? <ZeroExplanation rule={rule} /> : '—'}</td>
    </tr>)}</tbody>
  </table></div>;
}

/** Bastidores › Auditoria: quantas vezes cada regra e cada rótulo disparam na base atual, e por que os zeros são zeros. */
export function RulesCoverage({ data }: { data: RulesCoverageData }) {
  const zeros = data.rules.filter((rule) => rule.fires === 0);
  const operational = data.rules.filter((rule) => rule.kind === 'operational');
  const labels = data.rules.filter((rule) => rule.kind === 'label');
  const requests = [...data.sell_out_requests].sort((a, b) => (b.backlog_value ?? -1) - (a.backlog_value ?? -1));
  const unexplained = zeros.filter((rule) => !rule.zero_reason).length;
  return <details className="detail-block audit-block rules-coverage" open>
    <summary>Cobertura das regras<small>{data.rules.length - zeros.length} de {data.rules.length} disparam na base atual; {zeros.length} em zero{unexplained ? `, ${unexplained} sem motivo` : ', todos explicados'}</small></summary>
    <p className="fact-line">Disparos contados sobre as saídas atuais. Zero não é defeito: a linha explica se a base não tem o caso ou se falta dado, e cita um caso de referência. <Tooltip label="Natureza dos campos">{Object.entries(data.field_nature).map(([field, nature]) => `${field}: ${nature}`).join('. ')}</Tooltip></p>
    <RuleTable title="Sinais do ranking" rules={operational} operational />
    <RuleTable title="Rótulos de ação" rules={labels} operational={false} />
    {data.precedence.length > 0 && <details className="validation-details"><summary>Ordem de precedência dos rótulos</summary>
      <div className="table-shell" tabIndex={0} role="region" aria-label="Precedência dos rótulos"><table className="data-table coverage-table">
        <thead><tr><th>Nível</th><th>Posição</th><th>Linha</th><th>Disparos</th></tr></thead>
        <tbody>{data.precedence.map((line) => <tr key={`${line.level}-${line.position}`}><td>{LEVEL_NAMES[line.level] ?? line.level}</td><td>{line.position}</td><td>{line.line}</td><td>{displayQuantity(line.code_fires)}</td></tr>)}</tbody>
      </table></div>
    </details>}
    {requests.length > 0 && <details className="validation-details"><summary>Sell-out a pedir aos parceiros ({requests.length} pares)</summary>
      <p className="fact-line">Pares parceiro × SKU sem sell-out suficiente e com pedido em carteira, do maior valor ao menor. Sem preço, o valor fica indisponível.</p>
      <div className="table-shell" tabIndex={0} role="region" aria-label="Pedidos de sell-out"><table className="data-table coverage-table">
        <thead><tr><th>Parceiro</th><th>SKU</th><th>Carteira (un.)</th><th>Valor</th><th>Pedidos</th></tr></thead>
        <tbody>{requests.map((item) => <tr key={`${item.partner}-${item.sku}`}><td>{item.partner}</td><td><Link to={`/skus/${encodeURIComponent(item.sku)}`}>{item.sku}</Link><small>{item.product}</small></td><td>{displayQuantity(item.backlog_quantity)}</td><td>{displayCurrency(item.backlog_value)}</td><td>{item.orders.join(', ')}</td></tr>)}</tbody>
      </table></div>
    </details>}
    {data.limitations.length > 0 && <ul className="validation-list">{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
    {data.requires_human_review && <p className="fact-line"><Badge tone="medium">revisão humana</Badge> A cobertura descreve a base atual; não autoriza produção.</p>}
  </details>;
}
