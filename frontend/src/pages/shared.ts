import type { DashboardData, SelectedSku } from '../types';

export interface PageProps<K extends keyof DashboardData = keyof DashboardData> {
  data: Pick<DashboardData, K>;
  onSelect: (priority: SelectedSku) => void;
  onRefresh: () => Promise<void>;
}

/** Rótulos de ação do desafio. Um teste Python compara estes textos com src/caderno_inteligente/action_labels.py. */
export const CHALLENGE_NAMES: Record<string, string> = {
  produzir: 'Produzir', repor: 'Repor', priorizar_producao: 'Priorizar produção', priorizar_parceiro: 'Priorizar parceiro', ampliar_mix: 'Ampliar mix',
  recomendar_recompra: 'Recomendar recompra', reativar: 'Reativar', monitorar: 'Monitorar', investigar: 'Investigar', sem_acao_necessaria: 'Sem ação necessária',
};
export const CHALLENGE_DEFINITIONS: Record<string, string> = {
  produzir: 'Há ordem planejada a liberar dentro da janela de decisão.',
  repor: 'O estoque estimado do parceiro cobre poucos dias do giro observado; avaliar reposição comercial.',
  priorizar_producao: 'Produzir com urgência: há alavanca real de produção (antecipar uma OP, garantir quantidade para pedido sem cobertura) ou decisão de evento próxima.',
  priorizar_parceiro: 'Decidir quem atender com o estoque existente (pedidos sem cobertura disputados) ou parceiro com várias oportunidades de reposição.',
  ampliar_mix: 'Produto ativo sem nenhum faturamento em um canal com visibilidade completa; avaliar incluí-lo no mix.',
  recomendar_recompra: 'O parceiro vende bem, mas parou de receber sell-in há mais tempo que o ritmo do próprio par; recomendar nova compra.',
  reativar: 'O SKU vendia no canal e ficou meses sem faturar; avaliar reativação.',
  monitorar: 'Sem urgência: excesso de estoque, saída de linha, crescimento ou próxima ordem planejada fora da janela.',
  investigar: 'Faltam dados ou há divergência; investigar antes de decidir. Nenhuma oportunidade é inferida.',
  sem_acao_necessaria: 'Nenhum sinal que justifique ação neste horizonte.',
};

export const reasonNames: Record<string, string> = {
  RUP_LEAD_TIME: 'Cobertura abaixo do lead time',
  RUP_SAFETY_STOCK: 'Abaixo do estoque de segurança',
  ORDER_WITHOUT_PRODUCTION: 'Pedido sem produção',
  PRODUCTION_AFTER_PROMISE: 'Produção após a promessa',
  CAPACITY_CONFLICT: 'Capacidade pressionada',
  CAPACITY_SHORTFALL: 'Não cabe na capacidade',
  PROJECTED_SHORTFALL: 'Falta antes da reposição',
  OP_FOR_DISCONTINUED: 'OP de produto saindo de linha',
  PROJECTED_EXCESS: 'Excesso depois da OP',
  PARTNER_STOCK_BUILDUP: 'Estoque acumulando no parceiro',
  EXCESS_COVERAGE: 'Excesso de cobertura',
  LOW_SELLOUT_VISIBILITY: 'Baixa visibilidade de sell-out',
};

export const statusNames: Record<string, string> = {
  novo: 'Novo',
  em_investigacao: 'Em investigação',
  aguardando_comercial: 'Aguardando comercial',
  aguardando_producao: 'Aguardando produção',
  concluido: 'Concluído',
  aceita: 'Aceita',
  alterada: 'Alterada',
  rejeitada: 'Rejeitada',
  investigar: 'Investigar',
};

export const partnerDataEffectNames: Record<string, string> = {
  nao_utilizado: 'Não usei o dado do parceiro',
  confirmou: 'Confirmou minha análise',
  aumentou_confianca: 'Aumentou minha confiança',
  alterou_decisao: 'Mudou minha decisão',
};

export const decisionActionNames: Record<string, string> = {
  aceita: 'Aceitei a sugestão',
  alterada: 'Ajustei a sugestão',
  rejeitada: 'Rejeitei a sugestão',
  investigar: 'Vou investigar',
};

export const toUtcDate = (value: string) => new Date(`${value.slice(0, 10)}T00:00:00Z`);
export const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeZone: 'UTC' }).format(toUtcDate(value)) : 'Não disponível';
/** Data local de hoje como 'YYYY-MM-DD' (o prazo do caso é uma data sem horário). */
export const todayIso = (now = new Date()) => `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
/** Dias de atraso de um caso aberto com prazo no passado; `null` se concluído, sem prazo ou dentro do prazo. */
export function caseOverdueDays(item: { status: string; due_date: string }, today = todayIso()): number | null {
  if (item.status === 'concluido' || !/^\d{4}-\d{2}-\d{2}$/.test(item.due_date)) return null;
  const days = Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${item.due_date}T00:00:00Z`)) / 86_400_000);
  return days > 0 ? days : null;
}
const MONTHS_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
/** 'YYYY-MM-DD' → 'set/26'. */
export const formatMonth = (value?: string | null) => value ? `${MONTHS_PT[Number(value.slice(5, 7)) - 1] ?? value.slice(5, 7)}/${value.slice(2, 4)}` : 'Não disponível';
export const formatDateTime = (value: string) => new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
export const displayNumber = (value: unknown) => displayQuantity(value);
export const displayPercent = (value: number | null | undefined) => typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value) : 'Não disponível';

export const missingDataNames: Record<string, string> = {
  first_promised_date: 'primeira data prometida',
  first_production_completion: 'primeira conclusão prevista',
  sell_in_quantity: 'sell-in',
  sell_out_quantity: 'sell-out',
  forecast_quantity: 'forecast',
};

export function positiveDelayDays(promisedDate: string | null, completionDate: string | null) {
  if (!promisedDate || !completionDate) return null;
  const milliseconds = toUtcDate(completionDate).getTime() - toUtcDate(promisedDate).getTime();
  const days = Math.round(milliseconds / 86_400_000);
  return days > 0 ? days : null;
}

export const severityRank: Record<string, number> = { crítica: 4, alta: 3, média: 2, baixa: 1 };

/** Sinais do mais pesado para o mais leve (peso do ranking; desempate por severidade e código). Só muda a ordem de exibição. */
export function sortReasons<T extends { code: string; severity: string }>(reasons: T[], weights?: Record<string, number>): T[] {
  return [...reasons].sort((a, b) => (weights?.[b.code] ?? 0) - (weights?.[a.code] ?? 0)
    || (severityRank[b.severity] ?? 0) - (severityRank[a.severity] ?? 0) || a.code.localeCompare(b.code));
}

export type GlossaryTerm = 'score' | 'wape' | 'baseline' | 'holdout' | 'sellin' | 'sellout' | 'leadtime' | 'cobertura' | 'ausente' | 'confianca_dados' | 'confianca_previsao' | 'op' | 'faturamento_estimado' | 'producao_planejada' | 'cenario_evento' | 'canais_diretos';
export const glossary: Record<GlossaryTerm, { name: string; text: string }> = {
  score: { name: 'Pontos de atenção', text: 'Soma dos pesos dos problemas encontrados no SKU. Ordena o que analisar primeiro; não é a quantidade a produzir.' },
  wape: { name: 'Erro médio da previsão (WAPE)', text: 'Quanto, em %, a previsão errou em testes com meses já vendidos, incluindo meses de pico, somando todos os SKUs. Menor é melhor; não garante a precisão futura.' },
  baseline: { name: 'Previsão simples de comparação (baseline)', text: 'Repete o último mês observado. Serve para mostrar se o modelo realmente acrescenta algo.' },
  holdout: { name: 'Teste em meses já vendidos', text: 'O modelo prevê, a partir de várias datas do passado, os 3 meses seguintes usando só o que havia até ali; a diferença para o vendido é o erro (backtest).' },
  sellin: { name: 'Vendido ao parceiro (sell-in)', text: 'Quantidade enviada pela fábrica ao parceiro.' },
  sellout: { name: 'Vendido pelo parceiro (sell-out)', text: 'Quantidade que o parceiro vendeu ao consumidor. Quando não foi informada, o dado está ausente: não é venda zero.' },
  leadtime: { name: 'Prazo de produção (lead time)', text: 'Dias entre pedir e receber a produção do SKU.' },
  cobertura: { name: 'Cobertura em dias', text: 'Por quantos dias o estoque dura no ritmo de venda previsto para os 3 próximos meses.' },
  ausente: { name: 'Dado ausente', text: 'Informação que não existe na planilha. Nunca é tratada como zero.' },
  confianca_dados: { name: 'Confiança nos dados do SKU', text: 'Qualidade da evidência usada no ranking (por exemplo, se há sell-out observado). Baixa pede validação humana.' },
  confianca_previsao: { name: 'Confiança na previsão', text: 'Calculada pelo erro do modelo nos testes com meses já vendidos. Não é garantia de atendimento.' },
  faturamento_estimado: { name: 'Faturamento estimado', text: 'Previsão em unidades × preço vigente da tabela de preços, mantido constante: sem reajuste, desconto ou campanha. É receita bruta e global por SKU, não por parceiro ou canal. Estimativa, não faturamento realizado; SKU sem preço ou sem previsão fica de fora, nunca vira R$ 0.' },
  producao_planejada: { name: 'Produção planejada', text: 'Soma das ordens planejadas pelo mês em que a produção precisa começar (liberação). "Agora" são as que liberam dentro da janela de decisão (a quantidade sugerida da fila); "depois", as demais até o fim da previsão. É plano sugerido, não OP liberada, e não desconta a capacidade das linhas. Mês cujo prazo de produção passa do fim da previsão fica de fora, para não parecer menor do que é; SKU sem previsão também fica de fora, nunca vira zero.' },
  cenario_evento: { name: 'Cenário com evento', text: 'Previsão base × fator do mês, medido no histórico da própria família (mês do evento ÷ média dos meses sem evento). É estimativa indicativa com poucas ocorrências, não prevê campanhas e não substitui a previsão nem a quantidade oficial. Sem histórico direto ou com previsão sazonal de 12 meses (que já repete o ano anterior), só há alerta.' },
  canais_diretos: { name: 'Canais diretos', text: 'E-commerce, Marketplace e Loja própria. A visão vem do faturamento (venda ao consumidor); não há linhas deles em sell-in nem em sell-out e não há estoque por canal, só o do CD. A tendência compara os meses recentes com os anteriores e pode refletir sazonalidade. SKU sem faturamento no canal aparece como não vendido, nunca como venda zero. A sugestão é demonstrativa e exige revisão humana.' },
  op: { name: 'Ordem de produção (OP)', text: 'Registro que manda produzir. Este sistema nunca cria nem libera uma OP.' },
};

const ptNumber = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
const ptInteger = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
/** Quantidades: inteiro a partir de 100; uma casa abaixo disso. Ausente é "Não disponível", nunca zero. */
export const displayQuantity = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? (Math.abs(value) >= 100 ? ptInteger : ptNumber).format(value) : 'Não disponível';
const ptCurrency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
const ptCurrencyCents = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2, maximumFractionDigits: 2 });
/** Valor ausente nunca vira R$ 0. */
export const displayCurrency = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? ptCurrency.format(value) : 'Não disponível';
export const displayPrice = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? ptCurrencyCents.format(value) : 'Não disponível';
export const displayUnits = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? `${displayQuantity(value)} un.` : 'Não disponível';
export const displayDays = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? `${ptInteger.format(value)} ${Math.round(value) === 1 ? 'dia' : 'dias'}` : 'Não disponível';
/** Cobertura/participação: 0 casas. */
export const displayShare = (value: number | null | undefined) => typeof value === 'number' && Number.isFinite(value) ? `${ptInteger.format(value * 100)}%` : 'Não disponível';

/** Textos prontos do backend usam ponto decimal ("1246.3"); troca por pt-BR e arredonda como as quantidades da tela. */
export function localizeText(text: string): string {
  return text.replace(/(?<![\d.-])(\d+)\.(\d+)(?!\d|\.\d)/g, (_, whole: string, fraction: string) => displayQuantity(Number(`${whole}.${fraction}`)));
}
