import type { FormEvent } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import { SectionCard } from '../components';
import { clearSession, readSession, saveSession } from '../session';
import type { Session } from '../session';
import type { SkuFields, SkuRegistry, SkuRegistryItem } from '../types-registry';

const messageOf = (error: unknown) => error instanceof Error ? error.message : 'A solicitação falhou.';

/** Sessão e cadastro (fase 3). Só consulta a API com a base no banco; 401 encerra a sessão local.
 * Sem login exigido (authRequired = false), o cadastro fica liberado e nenhum token é enviado. */
export function useSkuRegistry(enabled: boolean, refreshToken: number, authRequired = true) {
  const [session, setSession] = useState<Session | null>(() => enabled ? readSession() : null);
  const [registry, setRegistry] = useState<SkuRegistry | null>(null);
  const [error, setError] = useState('');
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => { if (enabled && !session) setSession(readSession()); }, [enabled, session]);

  const expire = useCallback((caught: unknown) => {
    if (caught instanceof ApiError && caught.status === 401) {
      clearSession();
      setSession(null);
      setRegistry(null);
      setError('Sua sessão expirou. Entre novamente.');
      return true;
    }
    return false;
  }, []);

  const token = authRequired ? session?.token ?? '' : '';
  const active = enabled && (!authRequired || Boolean(session));

  useEffect(() => {
    if (!active) { setRegistry(null); return; }
    const controller = new AbortController();
    api.skuRegistry(token, controller.signal).then((result) => { setRegistry(result); setError(''); }).catch((caught: unknown) => {
      if (controller.signal.aborted || expire(caught)) return;
      setError(messageOf(caught));
    });
    return () => controller.abort();
  }, [active, token, refreshToken, reloadToken, expire]);

  const signIn = async (email: string, password: string) => {
    const created = saveSession(await api.login(email, password));
    setError('');
    setSession(created);
  };
  const signOut = () => { clearSession(); setSession(null); setRegistry(null); };
  return { session, active, token, authRequired, registry, error, expire, signIn, signOut, reload: () => setReloadToken((current) => current + 1) };
}

export function LoginForm({ onSubmit, disabled }: { onSubmit: (email: string, password: string) => Promise<void>; disabled: boolean }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try { await onSubmit(email, password); } catch (caught) { setError(messageOf(caught)); setPassword(''); } finally { setBusy(false); }
  };
  return <form className="form-layout login-form" aria-label="Entrar para cadastrar SKUs" onSubmit={(event) => void submit(event)}>
    <label>E-mail<input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
    <label>Senha<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    <div className="form-actions">{error && <span className="form-message form-error" role="alert">{error}</span>}<button className="primary-button" disabled={busy || disabled}>{busy ? 'Entrando…' : 'Entrar'}</button></div>
  </form>;
}

const EMPTY: SkuFields = { produto: '', familia: '', curva_abc: 'C', lead_time_dias: 0, lote_minimo: 0, estoque_atual: 0, estoque_seguranca_dias: 0, venda_media_dia: 0 };
const NUMBERS: Array<[keyof SkuFields, string, string]> = [
  ['lead_time_dias', 'Prazo de produção (dias)', '1'], ['lote_minimo', 'Lote mínimo', '1'], ['estoque_atual', 'Estoque atual', '1'],
  ['estoque_seguranca_dias', 'Estoque de segurança (dias)', '1'], ['venda_media_dia', 'Venda média por dia', '0.1'],
];

/** Mesmo formulário para criar (com o código) e editar (código fixo). As regras finais são do servidor. */
export function SkuForm({ families, initial, onSubmit, onCancel }: { families: string[]; initial?: SkuRegistryItem; onSubmit: (fields: SkuFields, sku: string) => Promise<void>; onCancel: () => void }) {
  const [sku, setSku] = useState(initial?.sku ?? '');
  const [fields, setFields] = useState<SkuFields>(() => initial ? { ...EMPTY, ...pick(initial) } : { ...EMPTY, familia: families[0] ?? '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = <K extends keyof SkuFields>(key: K, value: SkuFields[K]) => setFields((current) => ({ ...current, [key]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try { await onSubmit(fields, sku.trim().toUpperCase()); } catch (caught) { setError(messageOf(caught)); } finally { setBusy(false); }
  };
  const title = initial ? `Editar ${initial.sku}` : 'Novo SKU';
  return <form className="form-layout sku-form" aria-label={title} onSubmit={(event) => void submit(event)}>
    {!initial && <label>Código do SKU<input required maxLength={32} pattern="[A-Za-z0-9][A-Za-z0-9._\-]*" value={sku} onChange={(event) => setSku(event.target.value)} /></label>}
    <label>Produto<input required maxLength={120} value={fields.produto} onChange={(event) => set('produto', event.target.value)} /></label>
    <label>Família<select required value={fields.familia} onChange={(event) => set('familia', event.target.value)}>{families.map((family) => <option key={family}>{family}</option>)}</select></label>
    <label>Curva ABC<select value={fields.curva_abc} onChange={(event) => set('curva_abc', event.target.value as SkuFields['curva_abc'])}><option>A</option><option>B</option><option>C</option></select></label>
    {NUMBERS.map(([key, label, step]) => <label key={key}>{label}<input type="number" min={0} step={step} required value={fields[key]} onChange={(event) => set(key, Number(event.target.value) as never)} /></label>)}
    <div className="form-actions">{error && <span className="form-message form-error" role="alert">{error}</span>}
      <button type="button" className="secondary-button" disabled={busy} onClick={onCancel}>Cancelar</button>
      <button className="primary-button" disabled={busy}>{busy ? 'Salvando…' : initial ? 'Salvar alterações' : 'Cadastrar SKU'}</button></div>
  </form>;
}

function pick(item: SkuRegistryItem): SkuFields {
  return { produto: item.produto, familia: item.familia, curva_abc: item.curva_abc, lead_time_dias: item.lead_time_dias, lote_minimo: item.lote_minimo,
    estoque_atual: item.estoque_atual, estoque_seguranca_dias: item.estoque_seguranca_dias, venda_media_dia: item.venda_media_dia };
}

type Registry = ReturnType<typeof useSkuRegistry>;

/** Bloco "Cadastro" da lista de SKUs: login, novo SKU, edição e excluídos (com reativação). */
export function SkuRegistryPanel({ state, authEnabled, writeEnabled, editing, onEdit, onChanged }: {
  state: Registry; authEnabled: boolean; writeEnabled: boolean; editing: SkuRegistryItem | null;
  onEdit: (item: SkuRegistryItem | null) => void; onChanged: (message: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const { session, registry, active, token } = state;
  const inactive = registry?.items.filter((item) => !item.ativo) ?? [];
  const families = registry?.families ?? [];

  const save = async (fields: SkuFields, sku: string) => {
    if (!active) return;
    try {
      if (editing) await api.updateSku(token, editing.sku, fields); else await api.createSku(token, { ...fields, sku });
    } catch (caught) {
      if (state.expire(caught)) return;
      throw caught;
    }
    setCreating(false);
    onEdit(null);
    onChanged(editing ? `${editing.sku} atualizado.` : `${sku} cadastrado. Ele já entra na fila e nas previsões.`);
  };
  const reactivate = async (sku: string) => {
    if (!active) return;
    try { await api.reactivateSku(token, sku); onChanged(`${sku} reativado.`); } catch (caught) { if (!state.expire(caught)) onChanged(messageOf(caught)); }
  };

  const action = session && state.authRequired ? <div className="registry-user"><span>{session.user.name || session.user.email}</span><button type="button" className="secondary-button" onClick={state.signOut}>Sair</button></div> : undefined;
  return <SectionCard title="Cadastro" className="form-card registry-card" action={action}>
    {state.error && <p className="form-message form-error" role="alert">{state.error}</p>}
    {!writeEnabled && <p className="write-disabled-note" role="note">Cadastro desabilitado nesta publicação (somente leitura).</p>}
    {!active ? (authEnabled ? <LoginForm onSubmit={state.signIn} disabled={!writeEnabled} /> : <p role="note">Login não configurado nesta publicação.</p>)
      : editing ? <SkuForm key={editing.sku} families={families} initial={editing} onSubmit={save} onCancel={() => onEdit(null)} />
        : creating ? <SkuForm families={families} onSubmit={save} onCancel={() => setCreating(false)} />
          : <div className="registry-actions">
            <button type="button" className="primary-button" disabled={!registry?.editable || !writeEnabled} onClick={() => setCreating(true)}>Adicionar SKU</button>
            {inactive.length > 0 && <details><summary>Excluídos ({inactive.length})</summary><ul className="registry-inactive">{inactive.map((item) => <li key={item.sku}>
              <span><strong>{item.sku}</strong> {item.produto}</span>
              <button type="button" className="secondary-button" disabled={!writeEnabled} onClick={() => void reactivate(item.sku)}>Reativar</button>
            </li>)}</ul></details>}
          </div>}
  </SectionCard>;
}
