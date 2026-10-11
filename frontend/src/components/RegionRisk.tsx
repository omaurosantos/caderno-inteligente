import { SectionCard, Tooltip } from '../components';
import type { AllocationRegions } from '../types-allocation';
import { displayCurrency, displayNumber, displayUnits } from '../pages/shared';

/** Pedidos confirmados sem cobertura por região. O valor usa o preço vigente e fica indisponível (nunca zero) quando falta preço. */
export function RegionRisk({ data }: { data: AllocationRegions }) {
  if (!data.regions.length) return null;
  return <SectionCard title="Risco por região: pedidos sem cobertura" action={<Tooltip label="Natureza dos números">{data.limitations.join(' ')}</Tooltip>}>
    <div className="table-shell" tabIndex={0} role="region" aria-label="Risco por região; role horizontalmente para ver todas as colunas"><table className="data-table responsive-table"><thead><tr><th>Região</th><th className="num">Pedidos</th><th className="num">SKUs</th><th className="num">Sem cobertura</th><th className="num">Valor (calculado)</th></tr></thead>
      <tbody>{data.regions.map(region => <tr key={region.region}>
        <td data-label="Região"><strong>{region.region}</strong></td>
        <td className="num" data-label="Pedidos">{displayNumber(region.orders)}</td>
        <td className="num" data-label="SKUs">{displayNumber(region.skus.length)}</td>
        <td className="num" data-label="Sem cobertura">{displayUnits(region.uncovered_units)}</td>
        <td className="num" data-label="Valor">{displayCurrency(region.uncovered_value)}</td>
      </tr>)}</tbody></table></div>
  </SectionCard>;
}
