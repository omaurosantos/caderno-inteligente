# Histórico das etapas

Resumo dos registros de cada etapa da V2 (Etapas 2 a 15.6, mais as fases de usabilidade, enxugamento e redesign). Os registros completos, com listas de arquivos, contagens de testes e roteiros de deploy de cada etapa, estão no histórico do git até o commit `5105948`.

Todos os números foram medidos na planilha de hash SHA-256 `03fa0ed4…803f`. A referência atual do produto está em [calculations.md](calculations.md), [rules.md](rules.md), [prioritization.md](prioritization.md), [commercial-rules.md](commercial-rules.md), [api.md](api.md) e [decisions.md](decisions.md).

## Etapa 2 — Carregamento por página

- Cada página passou a buscar só os próprios endpoints (`useApiResource` + `PageResource`), em vez de um `loadDashboard()` único. Troca de rota cancela a leitura anterior (`AbortController`), e respostas antigas são ignoradas.
- Uma atualização que falha mantém os dados anteriores na tela. Falha em feedback, casos ou execuções não bloqueia a Visão geral.
- Sem cache entre rotas: voltar a uma página refaz as consultas (intencional, sem biblioteca nova).

## Etapa 3 — Jornada visual

- Visão geral em três blocos: o que exige atenção (primeiro SKU da fila e todos os seus sinais), ações sugeridas e qualidade da decisão. A ordem do backend é preservada, e o bloco de ações não inventa quantidade a partir do score.
- Padrões compartilhados: cabeçalho com status e horário da última carga, alertas, tooltips acessíveis, filtros com contagem e limpeza, distinção explícita entre prioridade de análise e ação de produção.
- **Ajuste registrado na validação:** o intervalo entre primeira promessa e primeira conclusão passou a se chamar "Intervalo de risco entre datas", sem mudar o cálculo, porque a base não vincula pedido a OP e não comprova atraso efetivo.

## Etapa 4 — Parceiros e recomendação comercial

- Núcleo comercial separado (`partner_insights.py`), cinco sinais (`REPOSITION_OPPORTUNITY`, `PARTNER_EXCESS_RISK`, `SELLIN_SELLOUT_DIVERGENCE`, `STALE_PARTNER_DATA`, `INSUFFICIENT_PARTNER_DATA`) e quatro APIs (`/api/partners`, `/api/partners/{codigo}`, `/api/partners/{codigo}/skus`, `/api/commercial-recommendations`).
- Une só chaves existentes; o estoque do parceiro é o estimado do último sell-out, nunca o do CD. Giro zero ou ausente dá cobertura nula, sem infinito.
- **Ajuste registrado na validação:** a cobertura comercial passou a ser medida pelos registros de sell-out, e não pela declaração cadastral de cobertura completa, porque canais declarados como completos apareciam sem sell-out.
- Base: 8 parceiros/canais, 95 vínculos parceiro–SKU (45 só com carteira, sem imputação). Decisões não são atribuíveis a parceiros, porque o feedback não registra o código do parceiro.

## Etapa 5 — Central de validação

- Página `/validacao` e `GET /api/validation/summary`: comparação com o processo atual, previsão contra baseline ("repetir o último mês"), casos congelados em `config/validation_center.json`, comportamento seguro, falhas conhecidas e histórico de ajustes. Exporta CSV e imprime.
- O WAPE do protótipo e o MAPE de 31% da empresa medem coisas diferentes e não são comparados diretamente. Pedidos no prazo e aderência ao plano não são recalculáveis com a base.
- Tempo de análise: nenhum ganho é afirmado antes de 20 decisões com minutos registrados.

## Etapa 6 — Comparação entre execuções

- `/execucoes?base=&alvo=` e `GET /api/run-comparisons`: entradas e saídas do ranking, mudança de posição, score e confiança, e decomposição da diferença de score em sinais e pesos (marcada "Não explicado" quando a soma não fecha).
- O snapshot ganhou a coluna opcional `comparison` (`schema_version = 1`) com previsão, recomendação e cobertura por parceiro. Migração aditiva `002_run_comparison.sql`. Execuções anteriores comparam só o ranking.

## Etapa 7 — Testes do frontend e acessibilidade

- Vitest, Testing Library, jsdom e axe-core. `npm run check` roda typecheck, Vitest, `node --test`, build e varredura de segredos no bundle.
- Contrato frontend × API: `contract-keys.json` lista os campos lidos em cada endpoint, e o pytest confere que a API real os entrega.
- Correções: contraste de `--slate-500`, foco visível nas linhas, papéis ARIA, tabelas roláveis focáveis, títulos por rota, link "Pular para o conteúdo", gaveta móvel acessível e `RouteErrorBoundary` por rota.

## Etapa 8 — Segurança e modo de demonstração

- Variáveis `APP_ENV`, `DEMO_MODE`, `WRITE_ENABLED` e `CORS_ORIGINS` (detalhes em [deploy-vercel-supabase.md](deploy-vercel-supabase.md)). Em produção, erros são genéricos com `X-Request-ID`, e os logs nunca mostram `DATABASE_URL`.
- Limites de tamanho e conteúdo em todas as escritas; SKU precisa existir. Cabeçalhos de segurança e CSP no frontend. Limpeza de dados por `scripts/reset_demo_data.py` ou `supabase/maintenance/reset_demo_data.sql`.
- Sem autenticação e sem limite de taxa: para publicação aberta, use `WRITE_ENABLED=false`.

## Etapa 9 — Documentação e demonstração

- README, arquitetura, API, cálculos e regras consolidados. Criados [semana-4-validacao-v2.md](semana-4-validacao-v2.md) e [roteiro-demonstracao.md](roteiro-demonstracao.md).
- `scripts/smoke_test.py`: smoke test somente leitura das URLs publicadas (até 47 verificações; a única escrita usa SKU inexistente e precisa ser recusada).

## Etapa 10 — Faturamento estimado

- `faturamento = previsão em unidades × preço vigente` (`revenue.py`), sempre rotulado como estimativa. Preço de `Precos_Produtos` (aba opcional) ou último preço faturado; sem preço, sem valor em R$.
- Erro em reais medido no mesmo teste da previsão. Forecast comercial aparece como referência, só nos meses em comum.
- Limitações: preço constante, receita bruta, previsão global por SKU (sem faturamento por parceiro, canal ou região).

## Etapa 11 — Sazonalidade e eventos

- `Calendario_Eventos` virou alerta por SKU com **data de decisão** (início do evento − lead time) e cenário explícito com fator por evidência histórica da família (limitado a 0,5–3,0 em `config/event_factors.json`).
- O teto ficou em 3,0, e não em 2,0, porque Volta às Aulas em Escolar mostrou ×2,41. Fator vem do histórico, não de tabela por impacto, que contradizia os dados.
- SKU com previsão sazonal recebe só alerta, para não contar o pico duas vezes. Evento sem histórico direto (Coleção Primavera) gera só alerta.

## Etapa 12 — Canais diretos

- E-commerce, Marketplace e Loja própria ganharam visão própria (`/canais`, `direct_channels.py`): faturamento de 24 meses, tendência, curva de contribuição, carteira e sugestão por SKU. Canal direto é definido pelo cadastro.
- Somam 68,2% do faturamento. Os três canais têm a mesma composição e sazonalidade (dado sintético), então o painel não os discrimina entre si.
- Achados de qualidade, sem reconciliação: os canais diretos não têm Sell_Out apesar de declarados "Completo"; o Sell_In dos parceiros é ~2,79× o faturado.

## Etapa 13 — Rótulos de ação

- Campo derivado `challenge_action` (`action_labels.py`, `config/challenge_actions.json`) com os rótulos do desafio: Produzir, Priorizar produção, Repor, Priorizar parceiro, Recomendar recompra, Ampliar mix, Reativar, Monitorar, Investigar e Sem ação necessária. Não é motor novo: a ação existente continua sendo a fonte.
- Dado insuficiente vence tudo ("Investigar"). "Ampliar mix" só sai nos canais diretos, onde a ausência é observada; nos parceiros, falta de registro não prova que não vendem.
- **Ajuste registrado na validação:** 11 casos congelados sintéticos (VC-09 a VC-19), um por rótulo. Ampliar mix, Recomendar recompra e Reativar não ocorrem nesta base.
- Migração `003_challenge_action.sql` (coluna opcional em `feedback`).

## Usabilidade, enxugamento e redesign

- **Usabilidade:** 40 propostas aplicadas, só de apresentação e navegação. O motivo principal passou a ser o sinal de maior peso, a ação e a quantidade ficaram no topo do SKU, e "Registrar decisão" já vem com o SKU preenchido.
- **Enxugamento:** palavras nas 15 telas de 20.524 para 6.392 (−69%). Detalhes de método foram para `/auditoria`. O orçamento de volume (`frontend/src/test/volume-budget.json`) virou teste de regressão.
- **Redesign "folha pautada":** um único `styles.css` com tokens, fontes embutidas (a CSP só aceita fontes do próprio domínio), menu em 7 grupos e Comercial em 3 páginas. Critério de clareza por tela em [criterio-de-clareza.md](criterio-de-clareza.md).

## Etapa 14 — Modelos candidatos de previsão

- **14.0:** todas as 50 séries têm 24 meses e nenhum mês zerado (Croston/SBA ficou de fora). O snapshot da previsão v1 em `docs/etapa-14-0/` é referência de regressão para os testes.
- **14.1:** seis candidatos em `forecast_candidates.py` (`moving_average_3`, `seasonal_naive_12`, `ses`, `combo_ma_sn`, `seasonal_level`, `holt_damped`) e critérios de promoção fixados em `config/forecast_engine.json` antes de qualquer resultado.
- **14.2:** backtest rolante com WAPE agrupado, parcimônia e avaliação aninhada. O motor rolante superou o v1 (7,0% × 9,0%), mas o ganho variou de −26,7% a +22,6% conforme a grade, e `minimum_windows` foi ajustado depois de ver números (todas as células registradas).
- **14.3:** laboratório na Validação (`GET /api/forecast-lab`), com a grade de sensibilidade inteira à vista.
- **14.4:** faixas P10–P90 cobriram só 48% dos meses fora da amostra contra 80% nominais. Não foram alargadas para "acertar" e depois ficaram escondidas até recalibração.

## Etapa 15 — Correção do motor de decisão

Comparação completa em [etapa-15/antes-depois.md](etapa-15/antes-depois.md), gerada por `scripts/snapshot_decisions.py` a partir de `etapa-15/antes.json` e `etapa-15/depois.json`.

### Etapa 15.0 — Linha de base e protocolo

- Decisões aprovadas: D1, saídas oficiais podem mudar com comparação antes × depois; D2, motor `v2` = `seasonal_level`; D3, data de planejamento 2026-09-14; D4, `CAPACITY_SHORTFALL` substitui `CAPACITY_CONFLICT`; D5, acúmulo no parceiro → Investigar; D6, rota `/capacidade`.
- **Gravado antes do código:** origens de avaliação e meses de pico (`forecast_engine.json`), `config/supply_plan.json`, limiares de acúmulo, pesos das regras novas e os casos VC-20 a VC-30, que ficaram "pendentes" até a subetapa que os atende.
- **Ajuste registrado na validação:** o VC-04 ("CI-0041 sem ação") seria revisto na 15.3, porque 914 un. prometidas para 13 e 14/09 ficavam sem cobertura até a OP-7840 (08/10).
- Antes: 30 SKUs "Sem ação necessária", 8 deles no top 10; previsão de nov/26 em 29.235 un. contra 34.259 realizadas em nov/25.

### Etapa 15.1 — Previsão v2

- Motor oficial `v2`: mês do ano anterior ajustado pelo nível, horizonte de 6 meses, erro medido em 7 origens rolantes com meses de pico.
- Atendeu aos quatro critérios gravados: WAPE de 10,1% para 8,0%, viés no pico de +0,7%, viés agregado sem piora e 45 SKUs melhores que a baseline contra 40 do v1.
- Previsão de nov/26 de 29.235 para 36.203 un. Novembro não é testável pela avaliação rolante (15 meses mínimos); é conferido pelo VC-28.

### Etapa 15.2 — Cobertura pela demanda

- A cobertura passou a usar a demanda de referência (média da previsão oficial dos 3 próximos meses) em vez de `Produtos.Venda média/dia`. A divergência vira o aviso `REGISTERED_DEMAND_DIVERGENCE`.
- CI-0014: 55 → 30,5 dias. CI-0004 entra em ruptura e sobe para a 8ª posição; CI-0009 entra na fila por excesso.
- **Decisão do usuário:** o VC-03 (excesso) falhou com o CI-0044 (84,8 dias, abaixo de 90). A alternativa (vendas dos 3 últimos meses) foi apresentada e recusada; o caso passou para o CI-0040 (~200 dias).

### Etapa 15.3 — Projeção datada e motor de ação

- `supply_plan.py`: projeção diária de 14/09/2026 a 28/02/2027 (carteira na data prometida, previsão rateada, OPs na conclusão prevista), com pedidos afetados, antecipar OP, ordens planejadas com data de liberação e redução ou cancelamento de OP.
- Precedência: investigar → antecipar OP → falta inevitável → produzir urgente → rever OP → produzir (liberar depois) → monitorar excesso → sem ação.
- "Sem ação necessária" de 28 para 0; quantidade a liberar agora de 7.700 para 22.900 un. Regras novas `PROJECTED_SHORTFALL`, `OP_FOR_DISCONTINUED` e `PROJECTED_EXCESS`.
- **Decisões do usuário:** manter a precedência quando VC-03, VC-22 e VC-08 pediam outra ação principal; a esperada passou a ser verificada como secundária.

### Etapa 15.4 — Capacidade semanal

- `capacity_plan.py` encaixa as ordens planejadas na capacidade livre de cada linha e semana (alocação gulosa por data de necessidade, com pré-produção). O que não cabe fica "sem programação", nunca jogado para depois.
- Escolar: 8.720 un. sem programação; o pico de 20.800 un. não cabe. `CAPACITY_SHORTFALL` em 6 SKUs com falta real, em vez dos 6 marcados pela ocupação média.
- Sem calendário de capacidade depois de dezembro: ordens posteriores ficam "a confirmar".

### Etapa 15.5 — Estoque no parceiro

- Janela de acúmulo de 6 meses por par parceiro–SKU (sell-through, crescimento do estoque, conferência da conta de estoque). Sinal `PARTNER_STOCK_BUILDUP` → "Não repor; acionar sell-out". O excesso estável virou "Monitorar estoque alto".
- KA-02 · CI-0009: vendeu 59% do que recebeu, estoque 595 → 931 un. A conta fecha, então é produto parado e não erro de registro. A OP-7808 cai de 1.200 para 300.
- Casos congelados: 30 de 30 aprovados.

### Etapa 15.6 — Telas e roteiro

- Detalhe do SKU › Evidências › "Plano de suprimento": cascata, pedidos afetados, ajustes de OP, ordens planejadas e projeção semanal. A fila mostra "Falta a partir de dd/mm".
- Documentação de referência e [roteiro-demonstracao.md](roteiro-demonstracao.md) reescritos em torno de quatro casos: CI-0041, KA-02 · CI-0009, CI-0050 e a linha Escolar.

## Etapa 16 — Fechar as lacunas do Desafio 3

Especificação em [discovery-etapa-16.md](discovery-etapa-16.md); decisões em [decisions.md](decisions.md); resumo por problema, números e commits em [etapa-16-resumo.md](etapa-16-resumo.md); comparação antes × depois em [etapa-16/antes-depois.md](etapa-16/antes-depois.md).

### Etapa 16.0 — Linha de base e casos-alvo

- Snapshot "antes" (`docs/etapa-16/antes.json`) gravado antes de qualquer mudança; três configurações novas (`allocation.json`, `prioritization_impact.json`, `capacity_extension.json`); VC-31 a VC-34 gravados como pendentes; texto do teto da razão sazonal montado a partir de `ratio_bounds` (P7a).

### Etapa 16.1 — Canais diretos e jornada da visibilidade (P1, P7c)

- As 22 linhas de canal direto deixaram de ser `dados_insuficientes`: viram `canal_direto`, com venda observada pelo faturamento e sem estoque intermediário. Cobertura de 0% para 100%; os 23 pares KA sem sell-out continuam como lacuna real.
- `/api/b2b2c/visibility` lista os canais diretos e traz `journey`: 75,1% das unidades faturadas têm venda ao consumidor observada.
- Avisos de qualidade `SELLIN_BILLING_DIVERGENCE` e `BILLING_UNIFORM_SPLIT`.

### Etapa 16.2 — Alocação de produto escasso (P5)

- `allocation.py`: ordem de atendimento por pedido confirmado, com pontuação transparente, atendimento parcial e resumo por região. 17 SKUs com falta (6.626 un., R$ 401.632,40, 21 pedidos); 5 disputados, todos com ordem de atendimento.

### Etapa 16.3 — Fila por urgência e valor em risco (P2)

- Faixas de urgência (17 / 12 / 5 / 9 SKUs nas faixas 1 a 4), `value_at_risk`, `abc_measured` e `priority_reason`. CI-0004 lidera; CI-0047 (descontinuação) deixa a 2ª posição.

### Etapa 16.4 — Rótulos por alavanca (P3)

- Tabela de decisão de 11 linhas, com `lever` e `decide_by`, e bloco "Decisões de hoje" (26 itens). Priorizar produção de 26 para 12 SKUs; nenhum rótulo acima de 30%.

### Etapa 16.5 — Capacidade estimada (P4)

- Semanas estimadas até o fim do horizonte; `a_confirmar` de 37 SKUs para 0. Novos status `ok_estimado` e `insuficiente_estimado`.

### Etapa 16.6 — Cobertura de regras, sell-out e projeção do parceiro (P6, P7b)

- `/api/rules/coverage` explica as regras com zero disparos; lista de 23 pares KA × SKU com pedido e sem sell-out ("pedir sell-out"); projeção para frente nas linhas "Repor".

### Etapa 16.7 — Impacto mensurável e IA honesta (P8)

- Tempo de análise medido automaticamente; valor em risco endereçado e pauta Modelo × S&OP (52 divergências acima de 20% em 32 SKUs) na Validação; narrativa da IA no roteiro. 34 de 34 casos congelados passam.

## Pendências registradas

- Deploy e smoke test com o motor novo; teste moderado com usuários (protocolo em [semana-4-validacao-v2.md](semana-4-validacao-v2.md)).
- Recalibração das faixas P10–P90; reconciliação Sell_In × Vendas_24m (hoje só aviso); vínculo pedido–OP (depende de dados da empresa); capacidade informada pela empresa depois de dezembro (hoje é estimativa); teste moderado com usuários para destravar a comparação do tempo de análise (0 registros hoje); resumo por LLM (D7, fora da Etapa 16).
- Sem autenticação; decisões não atribuíveis a parceiros.
