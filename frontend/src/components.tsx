import { useEffect, useId, useRef, useState } from 'react';
import { MOBILE_MENU_QUERY, useMediaQuery } from './hooks/useMediaQuery';
import type { ReactNode } from 'react';
import { Link, matchPath, useLocation } from 'react-router-dom';
import type { PageId, Priority } from './types';
import { glossary, reasonNames, sortReasons } from './pages/shared';
import type { GlossaryTerm } from './pages/shared';

type IconName =
  | 'guide'
  | 'overview'
  | 'priorities'
  | 'forecasts'
  | 'cases'
  | 'quality'
  | 'b2b'
  | 'runs'
  | 'feedback'
  | 'validation'
  | 'menu'
  | 'close'
  | 'refresh'
  | 'arrow'
  | 'search';

const iconPaths: Record<IconName, ReactNode> = {
  guide: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22V5.5Z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5A2.5 2.5 0 0 1 20 22V5.5Z"/></>,
  overview: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  priorities: <><path d="M4 6h16M4 12h10M4 18h7"/><path d="m17 15 3 3 3-4"/></>,
  forecasts: <><path d="M4 19V5M4 19h16"/><path d="m7 15 4-4 3 2 5-6"/><path d="M16 7h3v3"/></>,
  cases: <><path d="M9 5h6l1 2h4v13H4V7h4l1-2Z"/><path d="M9 12h6M9 16h4"/></>,
  quality: <><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3Z"/><path d="m9 12 2 2 4-5"/></>,
  b2b: <><circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-4 2-7 5-7s5 3 5 7M14 14c3-1 6 1 7 5"/></>,
  runs: <><path d="M12 3a9 9 0 1 1-8 5"/><path d="M3 3v6h6M12 7v5l3 2"/></>,
  feedback: <><path d="M4 4h16v13H9l-5 4V4Z"/><path d="M8 9h8M8 13h5"/></>,
  validation: <><path d="M9 3h6v3H9z"/><path d="M7 4.5H5v16h14v-16h-2"/><path d="m8.5 13 2.5 2.5 4.5-5"/></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16"/>,
  close: <path d="m6 6 12 12M18 6 6 18"/>,
  refresh: <><path d="M20 6v5h-5"/><path d="M18 16a8 8 0 1 1 1-9l1 4"/></>,
  arrow: <path d="m9 18 6-6-6-6"/>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
};

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name]}</svg>;
}

/** Título (h1 e aba do navegador) de cada rota. Um nome só por página. */
export const navigation: Array<{ id: PageId; path: string; label: string; description: string }> = [
  { id: 'guide', path: '/guia', label: 'Guia de uso', description: 'Como usar o protótipo' },
  { id: 'overview', path: '/', label: 'Início', description: 'Indicadores' },
  { id: 'queue', path: '/fila', label: 'Fila operacional', description: 'Qual SKU analisar, o que fazer e quanto' },
  { id: 'skus', path: '/skus', label: 'SKUs', description: 'Lista completa de SKUs' },
  { id: 'revenue', path: '/faturamento', label: 'Faturamento previsto', description: 'Estimativa em reais para três meses' },
  { id: 'capacity', path: '/capacidade', label: 'Capacidade', description: 'Onde a produção planejada não cabe' },
  { id: 'cases', path: '/casos', label: 'Casos', description: 'Acompanhamento' },
  { id: 'quality', path: '/qualidade', label: 'Dados da planilha', description: 'Integridade e lacunas' },
  { id: 'b2b', path: '/parceiros', label: 'Oportunidades', description: 'Onde repor, por parceiro e SKU' },
  { id: 'partners', path: '/carteira', label: 'Parceiros', description: 'Cobertura de dados por parceiro' },
  { id: 'channels', path: '/canais', label: 'Canais diretos', description: 'Faturamento observado' },
  { id: 'scenarios', path: '/cenarios', label: 'Cenários', description: 'Simulações sem alterar o ranking' },
  { id: 'runs', path: '/execucoes', label: 'Execuções', description: 'Histórico e comparação entre execuções' },
  { id: 'feedback', path: '/decisoes', label: 'Histórico de decisões', description: 'Decisões registradas pelo PCP' },
  { id: 'validation', path: '/validacao', label: 'Confiança nas recomendações', description: 'Validação dos resultados' },
  { id: 'model', path: '/modelo', label: 'Modelo de previsão', description: 'O que o modelo prevê, premissas e modelos comparados' },
  { id: 'audit', path: '/auditoria', label: 'Auditoria', description: 'Casos de teste, método e histórico' },
];

/** Menu principal: 8 entradas (a Ajuda fica na barra superior). As rotas agrupadas continuam abrindo por URL e aparecem como abas (SubNav). */
export const menuGroups: Array<{ id: string; label: string; to: string; paths: string[] }> = [
  { id: 'home', label: 'Início', to: '/', paths: ['/'] },
  { id: 'production', label: 'Planejamento', to: '/fila', paths: ['/fila', '/capacidade', '/cenarios', '/prioridades', '/previsoes'] },
  { id: 'skus', label: 'SKUs', to: '/skus', paths: ['/skus'] },
  { id: 'finance', label: 'Financeiro', to: '/faturamento', paths: ['/faturamento'] },
  { id: 'partners', label: 'Comercial', to: '/parceiros', paths: ['/parceiros', '/carteira', '/canais'] },
  { id: 'decisions', label: 'Acompanhamento', to: '/casos', paths: ['/decisoes', '/casos'] },
  { id: 'trust', label: 'Confiança', to: '/validacao', paths: ['/validacao', '/modelo'] },
  { id: 'backstage', label: 'Bastidores', to: '/auditoria', paths: ['/auditoria', '/execucoes', '/qualidade'] },
];

export const subNavigation: Record<string, Array<{ label: string; to: string }>> = {
  partners: [{ label: 'Oportunidades', to: '/parceiros' }, { label: 'Parceiros', to: '/carteira' }, { label: 'Canais diretos', to: '/canais' }],
  backstage: [{ label: 'Auditoria', to: '/auditoria' }, { label: 'Execuções', to: '/execucoes' }, { label: 'Dados da planilha', to: '/qualidade' }],
  decisions: [{ label: 'Casos', to: '/casos' }, { label: 'Histórico de decisões', to: '/decisoes' }],
  trust: [{ label: 'Validação', to: '/validacao' }, { label: 'Modelo de previsão', to: '/modelo' }],
};

const inGroup = (pathname: string, paths: string[]) => paths.some((path) => path === '/' ? pathname === '/' : !!matchPath({ path, end: false }, pathname));
export const groupFor = (pathname: string) => menuGroups.find((group) => inGroup(pathname, group.paths));

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const mobile = useMediaQuery(MOBILE_MENU_QUERY);
  const aside = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useEffect(() => { aside.current?.toggleAttribute('inert', mobile && !open); }, [mobile, open]);
  // Mobile drawer: move focus into the menu when it opens, close with Escape and return focus to the trigger.
  useEffect(() => {
    if (!mobile || !open) return;
    aside.current?.querySelector<HTMLElement>('nav a')?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') { onClose(); document.getElementById('menu-button')?.focus(); } };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [mobile, open, onClose]);
  return <>
    <div className={`sidebar-scrim ${open ? 'is-open' : ''}`} onClick={onClose} aria-hidden="true" />
    <aside ref={aside} id="menu-principal" aria-label="Menu" aria-hidden={mobile && !open ? true : undefined} className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="brand">
        <span className="brand-name">Caderno Inteligente</span>
        <button className="icon-button sidebar-close" onClick={onClose} aria-label="Fechar menu"><Icon name="close" /></button>
      </div>
      <nav aria-label="Navegação principal">
        {menuGroups.map((item) => {
          const active = inGroup(pathname, item.paths);
          return <Link key={item.id} to={item.to} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={onClose}>
            <strong>{item.label}</strong>
          </Link>;
        })}
      </nav>
    </aside>
  </>;
}

/** Abas entre as rotas de um mesmo grupo do menu (as URLs continuam as mesmas). */
export function SubNav() {
  const { pathname } = useLocation();
  const group = groupFor(pathname);
  const items = group ? subNavigation[group.id] : undefined;
  if (!items) return null;
  return <nav className="subnav" aria-label="Seções desta área">{items.map((item) => {
    const active = !!matchPath({ path: item.to, end: false }, pathname);
    return <Link key={item.to} to={item.to} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>{item.label}</Link>;
  })}</nav>;
}

/** Regra de uso dita uma vez, no topo de toda página com dados. */
/** Páginas com sugestão em lista (Início, Fila operacional, Parceiros). No detalhe do SKU a regra vive no cartão da ação; nas demais não é repetida. */
export const showsRule = (pathname: string) => pathname === '/' || pathname === '/fila' || pathname.startsWith('/parceiros') || pathname.startsWith('/canais');

export function RuleLine() {
  return <p className="rule-line" role="note"><strong>Apoio à decisão:</strong> toda sugestão exige revisão humana e não é ordem de produção. <Link to="/guia">Ajuda</Link></p>;
}

export function Topbar({ title, onMenu, onRefresh, refreshing, showRefresh = true, loadedAt = null, error = '', staticPage = false, menuOpen = false }: { title: string; onMenu: () => void; onRefresh: () => void; refreshing: boolean; showRefresh?: boolean; loadedAt?: number | null; error?: string; staticPage?: boolean; menuOpen?: boolean }) {
  const timestamp = loadedAt === null ? null : new Intl.DateTimeFormat('pt-BR', { timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date(loadedAt));
  return <header className="topbar">
    <div className="topbar-title">
      <button id="menu-button" className="icon-button menu-button" onClick={onMenu} aria-label="Abrir menu" aria-expanded={menuOpen} aria-controls="menu-principal"><Icon name="menu" /></button>
      <h1 id="page-title" tabIndex={-1}>{title}</h1>
    </div>
    <div className="topbar-actions">
      <div className="load-status" role="status"><span>{staticPage ? 'Conteúdo de orientação' : refreshing ? 'Carregando dados…' : error ? 'Falha na consulta' : loadedAt === null ? 'Sem dados carregados' : 'Dados carregados'}</span><small title="Última consulta concluída no navegador; não indica atualização da planilha de origem.">{staticPage ? 'Não consulta a API' : timestamp ? `Atualizado às ${timestamp}` : 'Ainda sem carga concluída'}</small></div>
      <Link className="secondary-button help-link" to="/guia" aria-label="Ajuda: abrir o guia de uso"><Icon name="guide" size={17} /><span>Ajuda</span></Link>
      {showRefresh && <button className="secondary-button" onClick={onRefresh} disabled={refreshing} aria-label={refreshing ? 'Atualizando dados' : 'Atualizar dados desta página'}><Icon name="refresh" /><span>{refreshing ? 'Atualizando…' : 'Atualizar'}</span></button>}
    </div>
  </header>;
}

export function Alert({ title, children, tone = 'info', action }: { title: string; children: ReactNode; tone?: 'info' | 'warning' | 'error'; action?: ReactNode }) {
  return <div className={`ui-alert ui-alert-${tone}`} role={tone === 'error' || tone === 'warning' ? 'alert' : 'note'}><div><strong>{title}</strong><div>{children}</div></div>{action}</div>;
}

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  return <span className={`tooltip ${open ? 'is-open' : ''} ${dismissed ? 'is-dismissed' : ''}`} onMouseEnter={() => setDismissed(false)}><button type="button" className="tooltip-trigger" aria-label={label} aria-describedby={id} aria-expanded={open} onFocus={() => setDismissed(false)} onClick={() => { setDismissed(false); setOpen(value => !value); }} onBlur={() => setOpen(false)} onKeyDown={event => { if (event.key === 'Escape') { setOpen(false); setDismissed(true); } }}>?</button><span id={id} role="tooltip" className="tooltip-content">{children}</span></span>;
}

/** "?" com a definição em linguagem simples de um termo do glossário. */
export function Hint({ term }: { term: GlossaryTerm }) {
  const entry = glossary[term];
  return <Tooltip label={`O que é: ${entry.name}`}>{entry.text}</Tooltip>;
}

export function SystemBanner({ info }: { info: { demo_mode: boolean; write_enabled: boolean; notice: string | null } | null }) {
  if (!info || (!info.demo_mode && info.write_enabled)) return null;
  return <div className="system-banner" role="note" aria-label="Modo da publicação">
    {info.demo_mode && <span><strong>Demonstração.</strong> {info.notice}</span>}
    {!info.write_enabled && <span><strong>Somente leitura.</strong> Registro de decisões, casos e execuções está desabilitado nesta publicação.</span>}
  </div>;
}

export function PageIntro({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return <div className="page-intro"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>;
}

export function Badge({ children, tone = 'neutral', title }: { children: ReactNode; tone?: string; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function severityTone(severity: string) {
  if (severity === 'crítica') return 'critical';
  if (severity === 'alta') return 'high';
  if (severity === 'média') return 'medium';
  return 'neutral';
}

export function confidenceTone(confidence: string) {
  return confidence === 'baixa' ? 'low' : confidence === 'alta' ? 'good' : 'medium';
}

/** Sinal que mais pesa no score (o primeiro da lista da API é só a ordem alfabética dos códigos). */
export function mainReason(reasons: Priority['reasons'], weights?: Record<string, number>) {
  return sortReasons(reasons, weights)[0];
}

/** Sinais de risco de ruptura, os mesmos que o backend conta em rupture_sku_count. */
export const RUPTURE_CODES = ['RUP_LEAD_TIME', 'RUP_SAFETY_STOCK'];
export const hasRuptureRisk = (reasons: Priority['reasons'] = []) => reasons.some((reason) => RUPTURE_CODES.includes(reason.code));

/** Navegação entre páginas de uma lista; some quando tudo cabe em uma página. */
export function Pagination({ page, pages, onChange, label }: { page: number; pages: number; onChange: (page: number) => void; label: string }) {
  if (pages <= 1) return null;
  return <nav className="pagination" aria-label={label}>
    <button type="button" className="secondary-button" onClick={() => onChange(page - 1)} disabled={page <= 1}>Anterior</button>
    <span role="status">Página {page} de {pages}</span>
    <button type="button" className="secondary-button" onClick={() => onChange(page + 1)} disabled={page >= pages}>Próxima</button>
  </nav>;
}

export function MetricCard({ label, value, detail, tone = 'blue', icon }: { label: ReactNode; value: ReactNode; detail: string; tone?: string; icon: IconName }) {
  return <article className={`metric-card metric-${tone}`}><div className="metric-icon"><Icon name={icon} /></div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}

export function PriorityTable({ rows, onSelect, weights }: { rows: Priority[]; onSelect: (row: Priority) => void; weights?: Record<string, number> }) {
  if (!rows.length) return <EmptyState title="Nenhuma prioridade encontrada" description="Ajuste os filtros ou atualize os dados." />;
  return <div className="table-shell" tabIndex={0} role="region" aria-label="Prioridades; role horizontalmente para ver todas as colunas"><table className="data-table priority-table responsive-table"><caption className="sr-only">Prioridade de análise · não é autorização de produção</caption><thead><tr><th>Posição</th><th>SKU / Produto</th><th>Motivo principal</th><th>Pontos <Hint term="score" /></th><th>Confiança nos dados <Hint term="confianca_dados" /></th><th><span className="sr-only">Abrir</span></th></tr></thead><tbody>{rows.map((row) => {
    const main = mainReason(row.reasons, weights);
    return <tr key={row.sku} onClick={() => onSelect(row)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' && event.target === event.currentTarget) onSelect(row); }}>
      <td data-label="Posição"><span className={`rank ${row.priority <= 3 ? 'top' : ''}`}>{row.priority}</span></td>
      <td data-label="SKU"><strong>{row.sku}</strong><small>{row.product}</small></td>
      <td className="cell-stack" data-label="Motivo principal"><Badge tone={severityTone(main?.severity)}>{reasonNames[main?.code] ?? main?.description ?? 'Sem motivo'}</Badge></td>
      <td data-label="Pontos"><strong className="score">{row.attention_score}</strong></td>
      <td data-label="Confiança nos dados"><Badge tone={confidenceTone(row.confidence)}>{row.confidence}</Badge></td>
      <td className="cell-action"><button className="icon-button table-detail-button" aria-label={`Abrir evidências de ${row.sku}`} onClick={event => { event.stopPropagation(); onSelect(row); }}><Icon name="arrow" size={17} /></button></td>
    </tr>;
  })}</tbody></table></div>;
}

export function LoadingState() {
  return <div className="loading-grid" role="status" aria-label="Carregando dados"><div className="skeleton hero-skeleton" />{[1, 2, 3, 4].map((item) => <div className="skeleton card-skeleton" key={item} />)}<div className="skeleton table-skeleton" /></div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="state-card error-state" role="alert"><div className="state-icon">!</div><h2>Não foi possível carregar o painel</h2><p>{message}</p><button className="primary-button" onClick={onRetry}><Icon name="refresh" />Tentar novamente</button></div>;
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state" role="status"><span>○</span><strong>{title}</strong><p>{description}</p></div>;
}

export function SectionCard({ title, subtitle, action, children, className = '' }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`section-card ${className}`}><div className="section-heading"><div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}

