/** Fase 3: login e cadastro de SKU (backend/registry.py). */
export interface SessionUser { email: string; name: string }

export interface LoginResult { token: string; expires_at: number; user: SessionUser }

export interface SkuFields {
  produto: string;
  familia: string;
  curva_abc: 'A' | 'B' | 'C';
  lead_time_dias: number;
  lote_minimo: number;
  estoque_atual: number;
  estoque_seguranca_dias: number;
  venda_media_dia: number;
}

export interface SkuRegistryItem extends SkuFields {
  sku: string;
  ativo: boolean;
  atualizado_em: string | null;
  atualizado_por: string | null;
}

export interface SkuRegistry {
  data_source: 'planilha' | 'banco';
  editable: boolean;
  families: string[];
  items: SkuRegistryItem[];
}

export interface SkuSaved { sku: string; version: number }
