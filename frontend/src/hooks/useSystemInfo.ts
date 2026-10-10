import { createContext, useContext } from 'react';

export interface SystemInfo {
  environment: 'development' | 'production';
  demo_mode: boolean;
  write_enabled: boolean;
  /** Fase 3: de onde a API lê as abas; o cadastro de SKU só existe com 'banco'. */
  data_source: 'planilha' | 'banco';
  auth_enabled: boolean;
  /** false: cadastro de SKU liberado, sem login (padrão atual do backend). */
  auth_required: boolean;
  text_limits: { note: number; user_name: number; owner: number; case_action: number; analysis_minutes: number };
  notice: string | null;
}

/** null while unknown (static pages or API offline); the server still enforces every rule. */
export const SystemInfoContext = createContext<SystemInfo | null>(null);
export const useSystemInfo = () => useContext(SystemInfoContext);

/** Defaults mirror backend/security.py so forms limit input even before /api/system answers. */
export const DEFAULT_TEXT_LIMITS: SystemInfo['text_limits'] = { note: 2000, user_name: 80, owner: 80, case_action: 200, analysis_minutes: 1440 };
