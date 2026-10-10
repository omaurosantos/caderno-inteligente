import type { LoginResult, SessionUser } from './types-registry';

/** Sessão de login guardada no navegador; expira junto com o token. O servidor confere o token a cada gravação. */
const KEY = 'caderno-inteligente.sessao';

export interface Session { token: string; expiresAt: number; user: SessionUser }

export function readSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session.token || session.expiresAt * 1000 <= Date.now()) { clearSession(); return null; }
    return session;
  } catch {
    return null;
  }
}

export function saveSession(result: LoginResult): Session {
  const session = { token: result.token, expiresAt: result.expires_at, user: result.user };
  try { window.localStorage.setItem(KEY, JSON.stringify(session)); } catch { /* sem armazenamento: a sessão vale só nesta tela */ }
  return session;
}

export function clearSession() {
  try { window.localStorage.removeItem(KEY); } catch { /* nada a limpar */ }
}
