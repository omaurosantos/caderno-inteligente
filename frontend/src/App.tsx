import type { ReactNode } from 'react';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { matchPath, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { PageResource } from './components/PageResource';
import { RouteErrorBoundary } from './components/RouteErrorBoundary';
import { LoadingState, RuleLine, Sidebar, SubNav, SystemBanner, Topbar, navigation, showsRule } from './components';
import type { SelectedSku } from './types';
import { PageLoadContext } from './hooks/usePageLoadStatus';
import { SystemInfoContext } from './hooks/useSystemInfo';
import type { SystemInfo } from './hooks/useSystemInfo';
import { api } from './api';
import type { PageLoadStatus } from './hooks/usePageLoadStatus';
import './styles.css';

const GuidePage = lazy(() => import('./pages/GuidePage'));
const OverviewPage = lazy(() => import('./pages/OverviewPage'));
const OperationalQueuePage = lazy(() => import('./pages/OperationalQueuePage'));
const RevenueForecastPage = lazy(() => import('./pages/RevenueForecastPage'));
const CapacityPage = lazy(() => import('./pages/CapacityPage'));
const CasesPage = lazy(() => import('./pages/CasesPage'));
const QualityPage = lazy(() => import('./pages/QualityPage'));
const B2BPage = lazy(() => import('./pages/B2BPage'));
const PartnersListPage = lazy(() => import('./pages/PartnersListPage'));
const DirectChannelsPage = lazy(() => import('./pages/DirectChannelsPage'));
const PartnerDetailPage = lazy(() => import('./pages/PartnerDetailPage'));
const ChannelDetailPage = lazy(() => import('./pages/ChannelDetailPage'));
const ScenariosPage = lazy(() => import('./pages/ScenariosPage'));
const RunsPage = lazy(() => import('./pages/RunsPage'));
const FeedbackPage = lazy(() => import('./pages/FeedbackPage'));
const ValidationPage = lazy(() => import('./pages/ValidationPage'));
const ModelPage = lazy(() => import('./pages/ModelPage'));
const SkuDetailPage = lazy(() => import('./pages/SkuDetailPage'));
const SkuListPage = lazy(() => import('./pages/SkuListPage'));
const AuditoriaPage = lazy(() => import('./pages/AuditoriaPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

const PAGE_FIELDS = {
  OverviewPage: ['overview'],
  CasesPage: ['cases', 'priorities', 'config'],
  QualityPage: ['quality'],
  ScenariosPage: ['config'],
  RunsPage: ['runs'],
  FeedbackPage: ['feedback', 'priorities', 'config'],
} as const;

/** Endereços antigos das abas de Parceiros (?aba=parceiros e ?aba=diretos) abrem as páginas novas com os mesmos filtros. */
function LegacyPartnersRoute({ children }: { children: ReactNode }) {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const tab = params.get('aba');
  if (tab !== 'parceiros' && tab !== 'diretos') return <>{children}</>;
  params.delete('aba');
  const search = params.size ? `?${params}` : '';
  return <Navigate to={{ pathname: tab === 'diretos' ? '/canais' : '/carteira', search }} replace />;
}

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [refreshToken, setRefreshToken] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [loadStatus, setLoadStatus] = useState<PageLoadStatus & { path: string }>({ path: '', loading: true, error: '', loadedAt: null });
  const reportLoad = useCallback((status: PageLoadStatus) => setLoadStatus({ ...status, path: location.pathname }), [location.pathname]);
  const refresh = () => setRefreshToken(token => token + 1);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);

  const firstRender = useRef(true);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    setMenuOpen(false);
    // Move focus to the page title after client-side navigation so screen readers announce the new page.
    if (firstRender.current) { firstRender.current = false; return; }
    document.getElementById('page-title')?.focus({ preventScroll: true });
  }, [location.pathname]);

  const current = useMemo(() => {
    if (matchPath('/parceiros/:codigo', location.pathname)) return { label: 'Detalhe do parceiro', description: 'Evidência comercial por SKU' };
    if (matchPath('/canais/:canal', location.pathname)) return { label: 'Detalhe do canal', description: 'Faturamento observado por SKU' };
    if (matchPath('/skus/:sku', location.pathname)) return { label: 'Detalhe do SKU', description: 'Evidências e recomendação' };
    const item = navigation.find((candidate) => matchPath({ path: candidate.path, end: candidate.path === '/' }, location.pathname));
    return item ?? { label: 'Página não encontrada', description: 'Navegação' };
  }, [location.pathname]);

  const selectSku = useCallback((item: SelectedSku) => {
    navigate(`/skus/${encodeURIComponent(item.sku)}`, { state: { from: `${location.pathname}${location.search}` } });
  }, [location.pathname, location.search, navigate]);

  const isGuide = location.pathname === '/guia';
  useEffect(() => { document.title = `${current.label} · Caderno Inteligente`; }, [current.label]);

  const staticPage = isGuide || current.label === 'Página não encontrada';
  const status = loadStatus.path === location.pathname ? loadStatus : { loading: true, error: '', loadedAt: null };

  // Runtime mode (demo / read-only) is read once API-backed pages are used; static pages stay offline-capable.
  useEffect(() => {
    if (staticPage || systemInfo) return;
    const controller = new AbortController();
    api.system(controller.signal).then(setSystemInfo).catch(() => { /* unknown mode: the server still enforces it */ });
    return () => controller.abort();
  }, [staticPage, systemInfo, refreshToken]);

  return <SystemInfoContext.Provider value={systemInfo}><PageLoadContext.Provider value={reportLoad}><div className="app-shell">
    <a className="skip-link" href="#conteudo" onClick={(event) => { event.preventDefault(); document.getElementById('page-title')?.focus(); }}>Pular para o conteúdo</a>
    <Sidebar open={menuOpen} onClose={closeMenu} />
    <main className="main-content" id="conteudo">
      <Topbar title={current.label} onMenu={() => setMenuOpen(true)} menuOpen={menuOpen} onRefresh={() => void refresh()} refreshing={!staticPage && status.loading} loadedAt={staticPage ? null : status.loadedAt} error={staticPage ? '' : status.error} staticPage={staticPage} showRefresh={!staticPage} />
      <div className="page-content">
        {!staticPage && <SystemBanner info={systemInfo} />}
        {!staticPage && showsRule(location.pathname) && <RuleLine />}
        <SubNav />
        <RouteErrorBoundary key={location.pathname}><Suspense fallback={<LoadingState />}>
          <Routes>
            <Route path="/guia" element={<GuidePage />} />
            <Route path="/" element={<PageResource key="OverviewPage" fields={PAGE_FIELDS.OverviewPage} refreshToken={refreshToken}>{(dashboard, reload) => <OverviewPage data={dashboard} onSelect={selectSku} onRefresh={reload} refreshToken={refreshToken} />}</PageResource>} />
            <Route path="/fila" element={<OperationalQueuePage onSelect={selectSku} refreshToken={refreshToken} />} />
            <Route path="/faturamento" element={<RevenueForecastPage refreshToken={refreshToken} />} />
            <Route path="/capacidade" element={<CapacityPage refreshToken={refreshToken} />} />
            {/* Rotas antigas: mesmos parâmetros (busca, familia, acao, rotulo, confianca, ordem, todos), nova página. */}
            <Route path="/prioridades" element={<Navigate to={{ pathname: '/fila', search: location.search }} replace />} />
            <Route path="/previsoes" element={<Navigate to={{ pathname: '/fila', search: location.search }} replace />} />
            <Route path="/casos" element={<PageResource key="CasesPage" fields={PAGE_FIELDS.CasesPage} refreshToken={refreshToken}>{(dashboard, reload) => <CasesPage data={dashboard} onSelect={selectSku} onRefresh={reload} />}</PageResource>} />
            <Route path="/qualidade" element={<PageResource key="QualityPage" fields={PAGE_FIELDS.QualityPage} refreshToken={refreshToken}>{(dashboard, reload) => <QualityPage data={dashboard} onSelect={selectSku} onRefresh={reload} />}</PageResource>} />
            <Route path="/parceiros" element={<LegacyPartnersRoute><B2BPage refreshToken={refreshToken} /></LegacyPartnersRoute>} />
            <Route path="/carteira" element={<PartnersListPage refreshToken={refreshToken} />} />
            <Route path="/canais" element={<DirectChannelsPage refreshToken={refreshToken} />} />
            <Route path="/parceiros/:codigo" element={<PartnerDetailPage key={location.pathname} refreshToken={refreshToken} />} />
            <Route path="/canais/:canal" element={<ChannelDetailPage key={location.pathname} refreshToken={refreshToken} />} />
            <Route path="/cenarios" element={<PageResource key="ScenariosPage" fields={PAGE_FIELDS.ScenariosPage} refreshToken={refreshToken}>{(dashboard, reload) => <ScenariosPage data={dashboard} onSelect={selectSku} onRefresh={reload} />}</PageResource>} />
            <Route path="/execucoes" element={<PageResource key="RunsPage" fields={PAGE_FIELDS.RunsPage} refreshToken={refreshToken}>{(dashboard, reload) => <RunsPage data={dashboard} onSelect={selectSku} onRefresh={reload} />}</PageResource>} />
            <Route path="/decisoes" element={<PageResource key="FeedbackPage" fields={PAGE_FIELDS.FeedbackPage} refreshToken={refreshToken}>{(dashboard, reload) => <FeedbackPage data={dashboard} onSelect={selectSku} onRefresh={reload} />}</PageResource>} />
            <Route path="/validacao" element={<ValidationPage refreshToken={refreshToken} />} />
            <Route path="/modelo" element={<ModelPage refreshToken={refreshToken} />} />
            <Route path="/auditoria" element={<AuditoriaPage refreshToken={refreshToken} />} />
            <Route path="/skus" element={<SkuListPage refreshToken={refreshToken} />} />
            <Route path="/skus/:sku"element={<SkuDetailPage key={location.pathname} refreshToken={refreshToken} />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense></RouteErrorBoundary>
      </div>
    </main>
  </div></PageLoadContext.Provider></SystemInfoContext.Provider>;
}

export default App;
