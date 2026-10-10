# API

A API FastAPI expõe prioridades, previsão, recomendação, visão comercial, qualidade, validação, feedback, casos, execuções e cenários. Nenhuma rota modifica o XLSM ou a configuração oficial. Todas as rotas novas desde a V1 são aditivas: os contratos anteriores continuam válidos.

## Índice de endpoints

| Método | Rota | Finalidade | Grava dados |
|---|---|---|---|
| GET | `/api/health` | Fonte, banco, persistência e cache | — |
| GET | `/api/system` | Ambiente, modo demonstração, escrita habilitada, fonte dos dados (`data_source`), login configurado (`auth_enabled`) e limites de texto | — |
| GET | `/api/overview` | Indicadores da visão geral, inclusive o estoque projetado (`projected_stock`) | — |
| GET | `/api/priorities` | Ranking oficial (`family`, `confidence`, `search`) | — |
| GET | `/api/priorities/{sku}` | Detalhe: indicador, sinais, contribuições, previsão, faturamento estimado (`revenue_forecast`), eventos (`event_alerts`, `event_scenario`) e recomendação | — |
| GET | `/api/forecasts` | Previsão e recomendação resumida de todos os SKUs | — |
| GET | `/api/revenue-forecast` | Faturamento estimado (previsão em unidades × preço vigente), por SKU, família e total | — |
| GET | `/api/events` | Calendário de eventos: alertas por SKU, evidência histórica por família e cenário com evento | — |
| GET | `/api/direct-channels` · `/api/direct-channels/{canal}` | Canais diretos (E-commerce, Marketplace, Loja própria): faturamento observado, tendência, carteira e sugestão por SKU | — |
| GET | `/api/data-quality/channels` | Achados entre abas que afetam a leitura dos canais | — |
| GET | `/api/capacity-plan` | Capacidade semanal finita (Etapa 15.4): ordens planejadas encaixadas por linha e semana, faltas, picos, pedidos afetados e premissas | — |
| GET | `/api/production-plan` | Produção planejada: ordens planejadas somadas por mês de liberação (agora × depois), no total e por família | — |
| GET | `/api/capacity/{family}` | Capacidade semanal da família, com `allocated` e `remaining` das ordens planejadas | — |
| GET | `/api/data-quality` | Validação da planilha e cobertura de sell-out | — |
| GET | `/api/b2b2c/visibility` | Cobertura e nível demonstrativo por parceiro (V1) | — |
| GET | `/api/partners` | Parceiros e cobertura medida (filtros e paginação) | — |
| GET | `/api/partners/{codigo}` | Resumo do parceiro | — |
| GET | `/api/partners/{codigo}/skus` | Matriz parceiro–SKU com evidências mensais | — |
| GET | `/api/commercial-recommendations` | Sugestões comerciais entre parceiros | — |
| GET | `/api/partner-stock-projection` | Projeção de estoque no parceiro por par parceiro–SKU, com erros de sell-in e sell-out (sem tela; aguarda validação do grupo) | — |
| GET | `/api/validation/summary` | Central de validação da Semana 4 | — |
| GET | `/api/forecast-lab` | Laboratório de previsão (Etapa 14.3): motor atual × motor rolante, avaliação aninhada e grade de sensibilidade; não altera nada oficial | — |
| GET | `/api/model-benchmark` | Cartão do modelo oficial (o que prevê, premissas, erro) e última rodada do benchmark de modelos, com histórico | — |
| GET | `/api/runs` · `/api/runs/{id}` | Execuções registradas | — |
| GET | `/api/run-comparisons?base=&target=` | Comparação entre duas execuções | — |
| GET | `/api/config` | Pesos, limiares e listas válidas | — |
| GET | `/api/cases` · `/api/cases/{id}/history` | Casos e histórico | — |
| GET | `/api/feedback` | Decisões registradas | — |
| POST | `/api/scenarios` | Simulação de pesos/limiares, sem persistência | — |
| POST | `/api/runs` | Registra snapshot auditável | sim (403 com `WRITE_ENABLED=false`) |
| POST | `/api/cases` · PUT `/api/cases/{id}` | Cria/atualiza caso | sim (403 com `WRITE_ENABLED=false`) |
| POST | `/api/feedback` | Registra decisão humana | sim (403 com `WRITE_ENABLED=false`) |
| POST | `/api/auth/login` | Login (fase 3): devolve `token`, `expires_at` e `user` | — |
| GET | `/api/auth/me` | Usuário do token | — |
| GET | `/api/skus/cadastro` | Cadastro de SKUs, inclusive os excluídos (`ativo`), e famílias válidas; exige login | — |
| POST | `/api/skus` · PUT `/api/skus/{sku}` | Cria/edita SKU (`Produtos`, `Estoque_Atual`, `Lead_Times`) | sim (login, `DATA_SOURCE=banco`, `WRITE_ENABLED`) |
| POST | `/api/skus/{sku}/excluir` · `/api/skus/{sku}/reativar` | Exclusão lógica e reativação | sim (login, `DATA_SOURCE=banco`, `WRITE_ENABLED`) |

Respostas de erro usam `{"detail": ...}`: 401 sem login válido, 404 para recurso inexistente, 403 para escrita desabilitada, 409 para conflito (SKU já existente ou base na planilha), 429 para tentativas de login em excesso, 503 para login não configurado, 413 para corpo acima de 16 KB, 422 para validação e 500 com código de referência (`X-Request-ID`).

## `GET /api/health`

Informa disponibilidade da fonte e da persistência:

- `status`: `ok` ou `degraded`;
- `source_available`: presença do XLSM no bundle;
- `database`: `ok` ou `unavailable`;
- `persistence`: `sqlite` localmente ou `postgres` com `DATABASE_URL`;
- `cache`: situação do cache do pipeline.

## `GET /api/overview`

As métricas de ruptura distinguem SKUs únicos de ocorrências de regras:

- `rupture_sku_count`: SKUs únicos que acionaram `RUP_LEAD_TIME` ou `RUP_SAFETY_STOCK`;
- `below_lead_time_count`: SKUs únicos abaixo do lead time;
- `below_safety_stock_count`: SKUs únicos abaixo do estoque de segurança;
- `rupture_signal_count`: total de ocorrências das duas regras;
- `risk_count`: alias temporário e compatível de `rupture_sku_count`.

Um SKU que aciona as duas regras contribui uma única vez para `rupture_sku_count` e duas vezes para `rupture_signal_count`.

### `projected_stock`

Estoque projetado no horizonte da previsão, agregado da projeção semanal do plano de suprimento (Etapa 15.3). Camada derivada e somente leitura, sem cálculo novo: não altera projeção, ação, quantidade, score nem ranking. Alimenta o bloco "Estoque projetado" do Início. Regra em [calculations.md](calculations.md), seção 4.3.

- `without_new_orders` (só estoque atual e OPs abertas) e `with_planned_orders` (somando as ordens planejadas): `shortfall_sku_count` (SKUs com estoque projetado negativo em alguma semana), `below_safety_sku_count` (abaixo do estoque de segurança em alguma semana, **incluindo** os com falta) e `first_shortfall_week` (segunda-feira da primeira semana com falta, ou `null`);
- `shortfall_skus[]` (`sku`, `product`, `family`, `first_shortfall_date`, `first_shortfall_week`, `shortfall_with_plan`): SKUs com falta sem novas ordens, da falta mais próxima para a mais distante;
- `planned_production`: `urgent_total` e `horizon_total`, os mesmos totais de `GET /api/production-plan`, e `urgent_window_end`;
- `weekly[]` (`week_start`, `shortfall_sku_count`, `shortfall_with_plan_sku_count`): quantos SKUs estão em falta em cada semana, sem novas ordens e com o plano (gráfico "SKUs em falta por semana" do Início). Só entram as semanas presentes na projeção de todos os SKUs avaliados, para uma semana além do horizonte de algum SKU não parecer melhora. Lista vazia quando nenhum SKU tem previsão;
- `excluded_skus[]` (`sku`, `reason = sem_previsao`): fora da conta, nunca contados como "sem falta";
- `reference_date`, `horizon_end`, `skus_evaluated`, `limitations` e `requires_human_review = true`.

`projected_stock` é `null` se a agregação falhar; os demais campos do `/api/overview` não são afetados.

## `GET /api/forecasts`

Retorna uma visão consolidada, somente leitura, com um item por SKU. A resposta combina identificação, posição e score do ranking oficial quando existentes, a previsão oficial (motor v2: 6 meses, com `forecast_total_3m`, `forecast_total_6m`, `backtest_windows` e `backtest_peak_wape`) e um resumo da recomendação operacional.

- usa o mesmo pipeline em memória de prioridades e detalhe;
- não recalcula nem altera score, ranking ou regras;
- inclui SKUs fora do ranking, identificados por `priority = null`;
- mantém forecast ausente como `null`, nunca como demanda zero;
- toda recomendação retorna `requires_human_review = true`;
- o resumo da recomendação traz `secondary_actions`, `planned_quantity_horizon` e `first_shortfall_date` (Etapa 15.3).

Ações operacionais possíveis: `investigar_dados`, `antecipar_op`, `atraso_inevitavel`, `produzir`, `produzir_validar_capacidade`, `rever_op`, `monitorar_excesso` e `sem_acao_necessaria`. No detalhe (`/api/priorities/{sku}`), a recomendação inclui o plano datado: `planned_orders`, `op_adjustments`, `affected_orders`, `projection` (semanal), `capacity` (situação de cada ordem na linha), `earliest_arrival` e a cascata em `calculation`; o indicador inclui `reference_daily_demand`, `demand_source`, `coverage_days_registered` e `data_quality_warnings` (Etapa 15.2).

O cálculo detalhado, as premissas e as evidências permanecem em `GET /api/priorities/{sku}`.

## `GET /api/revenue-forecast`

Estimativa de faturamento dos 3 meses previstos: `previsão em unidades × preço unitário vigente`. Camada derivada e somente leitura; não altera previsão, score, ranking nem recomendação, e `GET /api/forecasts` não ganhou campos.

- `items[]` (um por SKU): `status` (`ok`, `sem_preco` ou `sem_previsao`), `unit_price`, `price_source` (`Precos_Produtos` ou último preço de `Vendas_24m`), `price_conflict`, `forecast_units`, `revenue_values`, `revenue_next_month`, `revenue_total_3m`, `forecast_confidence`, `calculation.terms[]`, `observed_revenue` (12 meses, observado) e `commercial_reference` (Forecast_Comercial × mesmo preço, só nos meses em comum);
- `families[]` e `total`: `by_month`, `revenue_total_3m`, `skus_with_estimate`, `skus_excluded[]`, `confidence_distribution`, `backtest_wape` (erro em R$ do teste dos últimos 3 meses), `observed_last_3m_same_skus`, `change_vs_last_3m` e `commercial_reference`;
- `formula`, `field_nature` (observado, previsto ou estimado, com origem) e `limitations`;
- SKU sem preço ou sem previsão retorna valores `null` e entra em `skus_excluded`; nunca R$ 0.

`GET /api/priorities/{sku}` inclui o mesmo item em `revenue_forecast` (`null` se a estimativa falhar, sem afetar o restante).

## `GET /api/production-plan`

Ordens planejadas do plano de suprimento somadas pelo **mês de liberação**, separando as que liberam dentro da janela de decisão (`urgent`, a quantidade sugerida da fila) das demais (`later`). Camada derivada e somente leitura: não recalcula a projeção e não altera ação, quantidade, score nem ranking. Alimenta o gráfico da Fila operacional.

- `total` e `families[]` (com `family`): `months[]` (`month`, `urgent`, `later`), `urgent_total` (= soma de `suggested_quantity`) e `horizon_total` (= soma de `planned_quantity_horizon`, inclusive os meses omitidos);
- `omitted_months`: meses de liberação fora de `months` porque o horizonte da previsão não cobre o maior lead time (regra em [calculations.md](calculations.md), seção 4.2);
- `excluded_skus[]` (`sku`, `reason = sem_previsao`): SKUs sem previsão, fora da soma e nunca contados como zero;
- `reference_date`, `horizon_end`, `urgent_window_end`, `max_lead_time_days`, `field_nature`, `limitations` e `requires_human_review = true`.

## `GET /api/events`

Usa o `Calendario_Eventos` como alerta e como cenário explícito. Camada derivada e somente leitura: não altera previsão, score, ranking nem a quantidade oficial, e `GET /api/forecasts` não ganhou campos.

- `events[]`: período, impacto, `has_history`, `in_horizon`, `past`, `decision_date_earliest`, `skus_alerted` e a evidência por família (`factor`, `factor_raw`, `capped`, `occurrences`, `months_used`, `evidence_status`, `note`);
- `items[]` (um por SKU): `alerts[]` (evento, período, `days_to_start`, `decision_date` = início − lead time, `in_horizon`, `evidence`), `scenario_applicable`, `scenario_note` e `scenario` (`base_units`, `factors`, `scenario_units`, `incremental_units_3m`, faturamento no cenário, `quantity` oficial × com cenário);
- `family_factors[]`: fator por família e mês, com as ocorrências usadas;
- `settings` (de `config/event_factors.json`), `ignored_events[]` (linhas do calendário descartadas, com o motivo), `field_nature` e `limitations`;
- SKU com `seasonal_naive_12` recebe só alertas (`scenario = null` e a explicação em `scenario_note`); evento sem histórico direto nunca gera fator.

`GET /api/priorities/{sku}` inclui `event_alerts` e `event_scenario` (`null` se a análise falhar, sem afetar o restante).

## `GET /api/direct-channels` e `GET /api/direct-channels/{canal}`

Visão observada dos canais diretos, definidos pelo cadastro (`Parceiros_Canais.Tipo = "Canal direto"`). A fonte é o faturamento de `Vendas_24m`; os canais diretos não têm Sell_In nem Sell_Out e a base não tem estoque por canal. Camada somente leitura: não altera previsão, ranking nem `/api/data-quality`.

- lista: `totals` (faturamento direto e participação), `channels[]` (faturamento e unidades de 24 meses, participação, tendência, variação sobre o ano anterior, série mensal, concentração, carteira aberta, contagem de sinais e de sugestões, cobertura declarada × observada), `findings[]`, rótulos, `field_nature` e `limitations`;
- detalhe: `channel` e `items[]` (um por SKU, por faturamento): `revenue_24m`, `rank`, `share_in_channel`, `cumulative_share`, `trend`, `change_ratio`, `yoy_ratio`, contexto dos parceiros, carteira aberta, `signals[]` e `suggestion` (`code`, `label`, `reason`, `requires_human_review`). Filtros `signal`, `suggestion` e `search`;
- SKU sem faturamento no canal tem valores `null` e o sinal `NOT_SOLD`; nunca zero;
- 404 para canal inexistente (inclusive parceiro B2B); 422 para `signal` ou `suggestion` inválidos;
- `GET /api/data-quality/channels` devolve `findings[]` (cobertura declarada dos canais diretos sem linhas em Sell_Out; Sell_In dos parceiros que difere do faturado), com evidência numérica e tratamento. Nada é reconciliado.

## Rótulos de ação do desafio (`challenge_action`)

Campo opcional e aditivo, derivado das ações e dos sinais já calculados; não substitui `action`, não altera score, ranking, previsão nem quantidades. Aparece em `GET /api/forecasts` (por SKU), `GET /api/priorities/{sku}`, `GET /api/commercial-recommendations`, `GET /api/partners/{codigo}/skus` (por par parceiro–SKU), `GET /api/partners` (só `priorizar_parceiro`; `null` caso contrário) e em cada SKU de `GET /api/direct-channels/{canal}`.

- Estrutura: `code`, `label`, `source` (`operational`, `commercial`, `partner` ou `channel`), `origin_action`, `reason`, `signals_used`, `evidence[]` (`label`, `value`, `origin`), `limitations[]` e `requires_human_review`.
- Códigos: `produzir`, `repor`, `priorizar_producao`, `priorizar_parceiro`, `ampliar_mix`, `recomendar_recompra`, `reativar`, `monitorar`, `investigar` e `sem_acao_necessaria`.
- Filtro `challenge_action` em `/api/partners`, `/api/partners/{codigo}/skus`, `/api/commercial-recommendations` e `/api/direct-channels/{canal}` (422 para código inválido). As respostas de parceiros e canais trazem `challenge_labels`.
- Limiares em `config/challenge_actions.json`. Regras e precedência em [Etapa 13](historico.md).
- `POST /api/feedback` aceita `challenge_action` opcional (validado); `GET /api/feedback` o devolve (`null` em decisões anteriores). Exige a migração `003_challenge_action.sql` no Supabase para ser gravado; sem ela, a decisão é registrada sem o rótulo.

## `GET /api/b2b2c/visibility`

Cada parceiro recebe uma classificação demonstrativa derivada da cobertura de SKUs com sell-out observado:

- `Sem visibilidade`: 0%;
- `Essencial`: acima de 0% e abaixo de 40%;
- `Conectado`: de 40% até abaixo de 80%;
- `Estratégico`: 80% ou mais.

A resposta também informa `next_level`, a quantidade adicional de SKUs necessária e uma descrição do dado requerido. Essa classificação não representa acordo comercial firmado.

## `GET /api/feedback` e `POST /api/feedback`

Além de SKU, ação, observação e usuário, o feedback aceita:

- `partner_data_effect`: `nao_utilizado`, `confirmou`, `aumentou_confianca` ou `alterou_decisao`;
- `analysis_minutes`: número inteiro não negativo e opcional.

Bancos SQLite existentes são migrados de modo aditivo. Registros anteriores recebem `partner_data_effect = "nao_utilizado"` e `analysis_minutes = null`. Em produção, o mesmo contrato é preservado pelo adaptador PostgreSQL/Supabase.

O overview expõe `decision_count` e `partner_data_influenced_decision_count`. O segundo contabiliza decisões com efeito `aumentou_confianca` ou `alterou_decisao`.

## Etapa 4 — APIs comerciais aditivas

Os endpoints existentes não mudaram. As novas leituras não alteram ranking, previsão ou recomendação operacional.

- `GET /api/partners`: todos os parceiros/canais cadastrados e cobertura medida.
- `GET /api/partners/{codigo}`: resumo, referência, método e limitação de atribuição de decisões.
- `GET /api/partners/{codigo}/skus`: pares reais daquele parceiro, métricas e evidências mensais.
- `GET /api/commercial-recommendations`: pares reais, filtráveis entre parceiros.

Filtros exatos nas listas: `partner`, `sku`, `region`, `channel`, `action`, `data_quality`. A lista de SKUs do parceiro recebe o código pelo caminho, sem parâmetro `partner`. `action` aceita `avaliar_reposicao`, `monitorar_estoque`, `investigar_divergencia`, `solicitar_atualizacao`, `dados_insuficientes`; `data_quality` aceita `sufficient`, `stale`, `insufficient`.

Listas retornam envelope com `reference_month`, `total`, `items`, `limit`, `offset`, `thresholds`, `field_nature`, `limitation`. Paginação: `limit` padrão 200, entre 1 e 500; `offset` não negativo. Resumo do parceiro representa seus vínculos completos, mesmo quando a matriz está filtrada. Meses são `YYYY-MM`; datas de pedidos são ISO.

Valores ausentes são nulos; números observados iguais a zero continuam zero. Cada item comercial contém parceiro/SKU, meses efetivamente usados, períodos mensais e pedidos da carteira. Dados globais de estoque/capacidade/forecast não são incluídos. `reference_month` é a referência da base, não a data atual.

Parceiro inexistente retorna 404. Filtro enumerado inválido, paginação inválida ou dados/configuração comercial inválidos retornam 422. Atribuição de decisões por parceiro é explicitamente indisponível: `decisions.attribution_available=false`, `decisions.items=null`, com justificativa.

Método e regras: `docs/commercial-rules.md`.

## Etapa 14.3 — `GET /api/forecast-lab`

Leitura aditiva e somente leitura para o bloco "Modelos candidatos (laboratório)" da Validação. Não altera previsão, ranking, score nem recomendação oficiais (um teste compara `/api/forecasts` antes e depois). Configuração: `config/forecast_engine.json`.

- `promotion_status` (`pendente`), `promotion_note`, `engine` (`v1`) e `requires_human_review`: o motor rolante é um desafiante; a promoção é decisão separada.
- `selection`: `skus`, `changed_skus`, `models[]` (descrição, histórico mínimo, SKUs escolhidos em cada motor, erro mediano) e `changed[]` (SKUs cujo modelo mudaria).
- `nested`: avaliação aninhada do padrão (`aggregate` de `baseline`, `v1` e `rolling` com WAPE e viés ponderados e SKUs que superam a baseline, `rolling_vs_v1` e `criteria`).
- `sensitivity`: `cells[]` (uma por combinação de períodos de teste × janelas mínimas, com a marca `is_default`) e `summary`.
- `intervals` (Etapa 14.4): faixa de previsão P10–P90 do motor rolante: `level`, `skus_with_band`, `skus_without_band`, `calibration` (cobertura medida fora da amostra) e `items[]` (faixa do próximo mês por SKU). Estimativa; a cobertura observada na base atual (48%) fica abaixo dos 80% nominais.
- `field_nature` e `limitations`, no padrão dos demais endpoints.
- O cálculo leva alguns segundos na primeira chamada; o resultado fica em cache até a planilha ou `config/forecast_engine.json` mudarem. Configuração inválida devolve 422.

## `GET /api/model-benchmark`

Leitura aditiva para a aba Confiança › Modelo de previsão (`/modelo`). Não altera previsão, ranking, score nem recomendação oficiais (um teste compara `/api/forecasts` antes e depois).

- `official`: cartão do modelo em uso, montado da configuração (`config/forecast_engine.json`) e da previsão oficial já calculada:
  - `engine`, `engine_label`, `target` (o que é previsto, fonte e granularidade) e `horizon_months`;
  - `models[]`: a cadeia na ordem em que é tentada, com histórico mínimo e quantos SKUs usaram cada modelo;
  - `data`: SKUs e SKUs com previsão, meses de histórico;
  - `assumptions[]`: premissas em texto, com os limites lidos da configuração (por exemplo, a razão sazonal);
  - `evaluation`: origens, horizonte, meses de pico, `wape`, `peak_wape`, `normal_wape`, `bias` e pontos avaliados (nulo no motor v1);
  - `confidence` (regra e SKUs por nível) e `limitations[]`.
- `benchmark`: a rodada mais recente gravada em `runtime/benchmarks.db` por `scripts/benchmark_models.py`:
  - sem banco ou sem rodada: `status = "no_run"`, `stale = null`, `run = null`, `history = []`, e uma `note` com o comando para gerar a rodada. A leitura não cria o arquivo;
  - com rodada: `status = "ok"`, `stale` (o hash SHA-256 da planilha mudou desde a rodada) com `note`, `run` (`id`, `created_at`, `source_hash`, `protocol`, `environment`, `results[]`) e `history[]` (resumo de cada rodada, com o modelo de menor WAPE);
  - `results[]`: medidos primeiro, do menor para o maior WAPE; `unavailable` (biblioteca ausente) e `failed` (erro na execução) vêm por último, com `wape` nulo, nunca zero. Cada item traz `library_version`, `params`, `wape`, `peak_wape`, `normal_wape`, `bias`, `evaluated_points`, `fallback_points`, `duration_seconds`, `is_official` e `beats_official`.
- O banco do benchmark é só SQLite local: na publicação da Vercel, `runtime/` não é enviado e o endpoint responde `no_run`.

## `GET /api/partner-stock-projection`

**Sem tela, aguardando validação do grupo.** Somente leitura; não alimenta ranking, recomendação comercial nem plano. Configuração: `config/partner_projection.json`.

- Filtros opcionais `partner` e `sku` (até 40 letras, números, espaço, `_`, `.` ou `-`; fora disso, 422). Código sem sell-out informado devolve 404. Os erros agregados continuam os da base inteira quando há filtro.
- `errors.sell_out` e `errors.sell_in`: `wape`, `bias` e `points` da média usada, medidos nas origens configuradas. Cada item traz os mesmos erros só do par, para a tela poder exibir a incerteza.
- `items[]` por par: `current_stock`, `forecast_monthly_sell_out`, `coverage_days_now`, `replenishment_to_target`, `months` e `scenarios` (`with_replenishment` e `without_replenishment`, cada um com `monthly_sell_in`, `projected_stock[]`, `stockout_month` e `coverage_days_end`). Par com mês faltante na janela: `status = "insufficient_data"`, valores nulos e `reason`.
- `method` (fórmulas e configuração), `pairs`, `pairs_with_projection`, `total`, `limitations`, `nature = "estimado"` e `requires_human_review = true`.

## Etapa 5 — `GET /api/validation/summary`

Leitura aditiva e somente leitura para a Central de validação (`/validacao`). Reutiliza o pipeline cacheado, a previsão e a recomendação existentes; não altera pesos, limiares, modelos, ranking nem arquivos. Configuração: `config/validation_center.json`.

Campos principais:

- `process_comparison`: uma linha por indicador da empresa, com `informed` (natureza `informado`), `recalculated` (natureza `recalculado`, com `comparable` e `reason`) e `target` (natureza `meta` ou `null`). Valores não recalculáveis são `null`, nunca zero.
- `analysis_time`: decisões registradas, registros com minutos, soma, média e mediana; `comparison_allowed=false` enquanto a amostra for menor que `minimum_sample`.
- `forecast_evaluation`: holdout de 3 meses por SKU para cada candidato, para o modelo selecionado e para a baseline `naive_last` (último mês observado). Inclui SKUs elegíveis e insuficientes, WAPE mediano e ponderado, vitórias por modelo, SKUs que não superaram a baseline (empate conta como não superou) e lista por SKU.
- `frozen_cases`: os oito casos congelados com entrada, esperado, obtido, verificações, resultado (`passou`, `falhou`, `nao_encontrado`), limitação e ajuste. `source_matches_frozen=false` indica que a planilha mudou desde o congelamento.
- `safe_behavior`: verificações executadas a cada consulta (`aprovado`/`reprovado`) e as cobertas por teste automatizado (`coberto_por_teste`).
- `known_failures`, `known_limitations`, `adjustments` e `requires_human_review=true`.

Falha da persistência não derruba a rota: o tempo de análise volta vazio, com nota explicativa, e a falha é listada em `known_failures`. Configuração de validação inválida retorna 422.

## Etapa 6 — Comparação entre execuções

Mudanças aditivas em contratos existentes:

- `POST /api/runs` continua retornando `{"id": ...}`. O snapshot passa a preservar também um payload `comparison` (versão `schema_version = 1`) com previsão e recomendação operacional por SKU, limiares comerciais e cobertura B2B2C por parceiro cadastrado.
- `GET /api/runs` acrescenta `comparison_schema_version` (`null` em execuções anteriores).
- `GET /api/runs/{id}` acrescenta `comparison` (`null` em execuções anteriores).

### `GET /api/run-comparisons?base={id}&target={id}`

Compara dois snapshots gravados, sem recalcular nada. A rota é separada de `/api/runs/{id}` para não conflitar com a validação inteira do identificador.

- `base`, `target`: metadados com id, data, hash da planilha, SKUs no ranking e versão do snapshot.
- `context`: `source_changed`, `weights_changes`, `thresholds_changes` e `commercial_thresholds` (indisponível em snapshots anteriores).
- `ranking`: `entered`, `exited`, `changed` e `summary`. Cada item alterado traz posição e score base/alvo, `position_delta` (positivo = subiu), `score_delta`, `signals_added`, `signals_removed`, `score_breakdown` (sinal adicionado, removido ou peso alterado, com o delta), `score_delta_explained`, `explanation` e `evidence_changes` (valores de evidência dos sinais mantidos).
- `forecasts`: mudanças por SKU em previsão e recomendação, com `delta` numérico quando aplicável.
- `b2b_coverage`: mudanças por parceiro cadastrado em cobertura, SKUs observados e último sell-out.
- `comparable`, `notes`, `limitations`.

Seção sem dados compatíveis retorna `{"available": false, "reason": "..."}`. Isso ocorre com snapshot anterior à Etapa 6, versão de snapshot diferente, ranking sem os campos necessários ou análise comercial indisponível no registro. Base igual ao alvo ou id menor que 1 retorna 422; execução inexistente retorna 404.

## Etapa 8 — Segurança e modo de demonstração

### `GET /api/system` (novo, aditivo)

Retorna `environment`, `demo_mode`, `write_enabled`, `text_limits` (`note`, `user_name`, `owner`, `case_action`, `analysis_minutes`) e `notice`. Não consulta o banco e não expõe segredos nem dados de conexão.

### Escrita desabilitável

Com `WRITE_ENABLED=false`, `POST /api/feedback`, `POST /api/cases`, `PUT /api/cases/{id}` e `POST /api/runs` retornam **403** com `detail` explicativo. Leituras e `POST /api/scenarios` (simulação sem persistência) continuam disponíveis.

### Validação de entrada

- Decisões e casos recusam campos desconhecidos (422) e exigem SKU existente na base atual (422).
- Limites: `sku` 32, `note` 2000, `user_name` 80, `owner` 80, `action` do caso 200, `analysis_minutes` entre 0 e 1440. `due_date` vazio ou `AAAA-MM-DD` válido. `run_id` ≥ 1.
- Texto com caracteres de controle é recusado; quebras de linha e tabulação são permitidas. Espaços nas pontas são removidos.
- `PUT /api/cases/{id}` de caso inexistente retorna 404, sem gravar histórico órfão.
- `POST /api/scenarios` aceita somente regras e limiares conhecidos. Pesos ficam entre 0 e 100, `excess_coverage_days` entre 1 e 3650 e `capacity_occupation_threshold` entre 0 e 2.
- `GET /api/priorities`: `search`, `family` e `confidence` com até 100 caracteres.
- Corpo de `POST` e `PUT` acima de 16 KB retorna 413.

### Erros, cabeçalhos e CORS

- Toda resposta traz `X-Request-ID`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` e `Referrer-Policy: no-referrer`.
- Erro não tratado retorna 500 com `detail` contendo o código de referência. Em `APP_ENV=production` a mensagem é genérica; em desenvolvimento inclui o tipo e a mensagem, já sem connection strings.
- Em produção, erros 422 de validação retornam somente `type`, `loc` e `msg`, sem ecoar o valor enviado.
- CORS aceita apenas as origens válidas de `CORS_ORIGINS`, os métodos GET, POST, PUT e OPTIONS e os cabeçalhos `Content-Type` e `Authorization` (fase 3), sem cookies.

## Etapa de usabilidade — sem mudança de contrato

A etapa de usabilidade ([histórico](historico.md)) não adicionou, removeu nem alterou campos ou rotas. A interface passou a usar rotas que já existiam: `GET /api/config` (pesos, para ordenar os sinais por peso) em `/` e `/prioridades`, `GET /api/commercial-recommendations?action=avaliar_reposicao` na lista de oportunidades de `/parceiros` e `score_contributions` de `GET /api/priorities/{sku}` (decomposição do score). A etapa de enxugamento (`docs/etapa-enxugamento.md`) também não alterou contratos: a página `/auditoria` usa `GET /api/validation/summary` e `GET /api/partners?limit=1` (método comercial), e vários campos deixaram de ser exibidos sem deixar de existir.

## Fase 3 — Login e cadastro de SKU

Detalhes, decisões e passo a passo em [fase-3-banco-e-cadastro.md](fase-3-banco-e-cadastro.md).

- `POST /api/auth/login` recebe `{email, password}`. Responde 401 se a senha estiver errada, 429 depois de 5 falhas em 10 minutos e 503 em produção sem `AUTH_SECRET`.
- Com `AUTH_REQUIRED=true`, as rotas de cadastro exigem `Authorization: Bearer <token>`; sem token válido, ou com usuário inativo, respondem 401. Com `AUTH_REQUIRED=false` (padrão atual), as rotas ficam liberadas e as alterações são registradas como `sem-login`. `GET /api/system` informa o modo em `auth_required`.
- `POST /api/skus` recebe `sku`, `produto`, `familia` (uma família da base), `curva_abc` (`A`, `B` ou `C`), `lead_time_dias`, `lote_minimo`, `estoque_atual`, `estoque_seguranca_dias` e `venda_media_dia`, todos não negativos. Responde 201 com `{sku, version}`. `PUT /api/skus/{sku}` recebe os mesmos campos, sem `sku`. Campos desconhecidos dão 422.
- Toda gravação é validada com `validate_dataset` na prévia da base inteira; um erro que a base não tinha antes dá 422. SKU duplicado (ativo ou inativo) dá 409.
- Com `DATA_SOURCE=planilha`, as gravações respondem 409 e `GET /api/skus/cadastro` retorna `editable: false`.
- A exclusão é lógica e usa POST, não DELETE: o SKU sai de todos os cálculos, e casos, decisões e execuções que o citam continuam. Excluir um SKU já excluído (ou reativar um ativo) dá 409.
