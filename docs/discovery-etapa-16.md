# Discovery — Etapa 16: fechar as lacunas do Desafio 3

> Base para uma IA (ou pessoa) implementar as correções. Escrito em 10/10/2026, com prazo de entrega em 17/10/2026.
> Os números saem da planilha atual (`data/source/Base de Dados - Caderno Inteligente.xlsm`, sha256 `03fa0ed4…`) e da
> API local, rodada em modo somente leitura. Não há código implementado; este documento só define **o quê**, **por quê**
> e **como verificar**.

## 0. Como usar este documento

1. Leia a seção 1 (fatos da base) antes de qualquer código. Vários problemas vêm de características da planilha, não de bugs.
2. Leve as decisões da seção 4 ao usuário antes de começar. As decisões D1, D2 e D4 mudam princípios das etapas anteriores.
3. Implemente na ordem da seção 5. Cada subetapa tem critérios de aceite verificáveis na base real.
4. Regras do projeto que continuam valendo (veja `docs/historico.md` e `README.md`):
   - **Dado ausente nunca vira zero.** Toda saída distingue *observado*, *calculado* e *estimado* (campo `field_nature` ou `nature`).
   - Toda recomendação traz `requires_human_review: true`, evidências e limitações.
   - Todo campo novo lido pelo frontend entra em `frontend/src/test/contract-keys.json` (validado por `tests/test_frontend_contracts.py`).
   - `frontend/src/test/volume-budget.json` limita palavras, números e colunas por tela. A `/fila` tem no máximo **5 colunas**: informação nova entra no texto do motivo, em tooltip ou no detalhe do SKU. Não afrouxe o orçamento sem decisão explícita.
   - Uma mudança de comportamento que altere um caso congelado (`config/validation_center.json`, VC-01 a VC-30) exige revisar o caso **e** registrar a mudança em `adjustments`, com o motivo.
   - Gere `docs/etapa-16/antes.json` com `scripts/snapshot_decisions.py` **antes** da primeira mudança e `depois.json` + `antes-depois.md` no fim.
   - Ambiente: rode o pytest com `--basetemp` no diretório temporário da sessão (no sandbox, `tmp_path` falha com PermissionError). Rode `npm install` em `frontend/` antes do `npm run check`; o `recharts` entrou na fase 4 e pode não estar instalado.
   - O usuário faz o commit. No fim de cada subetapa, entregue: testes Python, `npm run check`, arquivos modificados, limitações e o nome sugerido do commit.

## 1. Fatos da base que condicionam as soluções

| # | Fato verificado | Consequência |
|---|---|---|
| F1 | Os 53 pedidos da carteira estão "Confirmado", com datas prometidas **de 13/09 a 06/10/2026**. A data de planejamento é 14/09 e os lead times vão de 21 a 30 dias. | Toda falta em pedido confirmado acontece **antes** de uma produção nova chegar. Para esses SKUs, a decisão real é **quem atender com o estoque e as OPs existentes**, não "produzir". Esse fato liga os problemas P3 e P5. |
| F2 | Das 21 faltas inevitáveis, 16 têm pedido confirmado afetado (22 pedidos ao todo). As outras 5 (CI-0006, CI-0010, CI-0014, CI-0015, CI-0023) são faltas só na **demanda prevista**. | Uma falta em pedido é **observada**; uma falta na previsão é **estimada**. Hoje as duas recebem o mesmo rótulo. |
| F3 | Em 5 SKUs, dois clientes disputam o mesmo estoque: CI-0041 (KA-05 512 un. e KA-02 534 un.), CI-0049 (KA-02 e KA-01), CI-0004 (KA-02 e KA-05), CI-0005 (KA-04 e Marketplace) e CI-0027 (KA-01 e KA-05). | É aqui que a alocação (P5) tem efeito visível. |
| F4 | `Vendas_24m` tem 8 clientes × 50 SKUs × 24 meses = 9.600 linhas, sem lacunas. A participação de cada parceiro em cada SKU fica entre **0,94 e 1,03 da mediana** dos parceiros. | O faturamento por cliente é, na prática, um **rateio uniforme** e não diz nada sobre padrões por parceiro ou região. Os padrões por parceiro e região precisam vir de `Sell_In` e `Sell_Out`. Ampliar mix e Reativar (P6) não podem disparar com esse dado. |
| F5 | `Sell_In` e `Sell_Out` cobrem 5 parceiros × 10 SKUs × 12 meses (set/25 a ago/26), todo o sell-out "Observado pelo parceiro". KA-01 e KA-04 têm os mesmos 10 SKUs; KA-02 e KA-05 também; KA-03 tem 10 próprios (30 SKUs distintos). | O painel de sell-out é uma **amostra**, não o mix do parceiro. A ausência de um SKU no painel não quer dizer que o parceiro não o compra. |
| F6 | No mesmo período e para os mesmos pares, o sell-in é muito maior que o faturamento registrado para o parceiro: KA-01 11.649 × 7.922; KA-05 13.071 × 1.900 (**6,9×**). | É uma divergência entre fontes, e precisa aparecer como lacuna (P7c). |
| F7 | Os canais diretos (E-commerce, Marketplace, Loja própria) são 68% do faturamento e 68% das unidades. O cadastro declara cobertura de sell-out "Completo" com 50 SKUs, mas eles não têm linhas em `Sell_In` nem em `Sell_Out`. | Para os canais diretos, o faturamento **é** a venda ao consumidor. `direct_channels.py` já trata assim; `partner_insights.py` e `/api/b2b2c/visibility`, não (P1). |
| F8 | A curva ABC do cadastro (`Produtos.Curva ABC`) **não bate** com o faturamento dos últimos 12 meses: só 13 de 50 SKUs caem na mesma classe. Exemplos: CI-0041 é "C" no cadastro e faturou R$ 785 mil; CI-0018 é "A" e faturou R$ 98 mil. | Não use a ABC do cadastro como peso de impacto (P2). Calcule a curva pelo faturamento e mostre a divergência como aviso de qualidade. |
| F9 | `Capacidade_Semanal` tem 16 semanas por família, de 14/09 a 28/12/2026 (até 03/01). A capacidade máxima é constante; a disponível varia (Escolar: 480 a 1.200 un./semana, média de 810). | A Volta às Aulas (05/01 a 20/02/2027) cai inteira fora do calendário (P4). |
| F10 | O feedback já tem o campo `analysis_minutes`, mas há 0 registros com tempo informado. | Nenhum ganho de processo pode ser afirmado hoje (P8). |

## 2. Problemas, causa raiz e solução recomendada

Formato de cada problema: sintoma → causa raiz (arquivo:linha) → solução recomendada → alternativas descartadas → critérios de aceite → casos congelados afetados → esforço.

---

### P1. Canais diretos tratados como "sem visibilidade"

**Sintoma.** Das 95 linhas de `/api/commercial-recommendations`, 22 são de canais diretos e saem como `dados_insuficientes`, com rótulo "Investigar". Em `/api/partners`, a cobertura dos canais diretos é 0,0. `/api/b2b2c/visibility` nem lista os canais diretos.

**Causa raiz.**
- `src/caderno_inteligente/partner_insights.py:186`: os pares são a união de Sell_In/Sell_Out com a carteira. Os canais diretos só entram pela carteira e nunca têm sell-out, então `enough` é falso (`:205`) e a ação vira `dados_insuficientes` (`:233`).
- `partner_insights.py:292-300`: `observed_skus` e `coverage` só contam a aba `Sell_Out`.
- `backend/main.py:753`: a visibilidade filtra `Tipo != "Canal direto"`.

**Solução recomendada.**
1. Criar o conceito `visibility_source` por parceiro:
   - `sell_out_parceiro`: parceiros KA; a fonte é `Sell_Out`;
   - `faturamento_direto`: `Parceiros_Canais.Tipo == "Canal direto"` (use `direct_channels.direct_channel_codes`); a fonte é `Vendas_24m`, com natureza "observado (venda ao consumidor)".
2. Em `build_partner_insights`, separar as linhas de canal direto (`row_kind: "direct"`):
   - `sell_out_recent` e `average_monthly_sell_out` vêm de `Vendas_24m` (mesma janela `recent_months`);
   - `estimated_stock = None`, com `stock_reason: "Sem estoque intermediário: o estoque que atende o canal é o do CD"`. Isso **não** é dado insuficiente;
   - `data_quality = "sufficient"` e `data_nature = "Observado (faturamento direto)"`;
   - ação nova `canal_direto` (rótulo "Venda direta ao consumidor: acompanhar pelo canal"). O rótulo do desafio vem da sugestão de `direct_channels.py` para o mesmo SKU e canal (reaproveite `label_channel_row`); a falta em pedido do canal é tratada pela alocação (P5);
   - não aplicar a lógica de cobertura, acúmulo e divergência, que pressupõe estoque no parceiro.
3. No resumo por parceiro, para canais diretos: `observed_skus` = SKUs com faturamento nos últimos `recent_months`; `coverage` = observados ÷ catálogo (100% na base atual); `visibility_source` exposto.
4. Em `/api/b2b2c/visibility`, incluir os canais diretos e um bloco `journey` que responde "até onde vemos o consumidor":
   - unidades vendidas pela empresa nos 12 meses, por tipo de canal;
   - unidades com venda ao consumidor **observada**: venda direta + sell-out informado pelos KAs;
   - participação observada (%) e o restante como "sem visibilidade". Esse é o número que o PDF pede ("deixar claro até onde existe visibilidade real").
5. Frontend: `/carteira` e a lista de parceiros mostram a fonte ("sell-out do parceiro" × "venda direta") e param de mostrar 0% para os canais diretos.

**Alternativa descartada.** Remover as linhas de canal direto da análise comercial: some o pedido em carteira desses canais, e a falta deles some da conversa comercial.

**Critérios de aceite.**
- 0 linhas de canal direto com `action == "dados_insuficientes"`;
- cobertura dos canais diretos = 1,0 e a dos KAs continua 0,2;
- as 23 linhas KA sem sell-out continuam `dados_insuficientes` (a lacuna real não pode sumir);
- `journey` presente, com soma das partes = total de unidades;
- teste com fixture: canal direto sem faturamento recente não ganha `sufficient`.

**Casos congelados.** VC-07 e VC-18 devem continuar passando; confira se o par de cada um é KA. Proposta de caso novo: **VC-31** "Canal direto não é dado insuficiente".

**Esforço.** 0,5 a 1 dia.

---

### P2. Ranking sem impacto

**Sintoma.** 1º lugar: CI-0041 (curva C no cadastro). 2º: CI-0047 (em descontinuação, quantidade 0). CI-0002 (curva A) aparece em 8º. A ordem só mede **quantos** sinais o SKU tem, não **quanto** está em jogo.

**Causa raiz.** `src/caderno_inteligente/prioritization.py:52`: `score = sum(weights[code])`, sem magnitude. O desempate é por SKU (`:67`).

**Solução recomendada: ordenar por faixa de urgência, depois por valor em risco.** A soma de pesos continua sendo exibida como "pontuação de sinais".

1. **Faixa de urgência** (`urgency_tier`), calculada a partir do plano de suprimento (`supply_plan.build_sku_plan`) já existente:
   - **1 – Pedido confirmado sem cobertura** (há `affected_orders`), dado observado;
   - **2 – Ação de produção nas próximas 4 semanas**: OP a antecipar, ordem planejada urgente, ou falta projetada só na demanda prevista;
   - **3 – Rever OP ou excesso**: `rever_op`, `PROJECTED_EXCESS`, acúmulo no parceiro;
   - **4 – Produzir no horizonte ou monitorar**.
2. **Valor em risco** (`value_at_risk`), sempre em reais e separado por natureza:
   - `observed`: Σ (quantidade não atendida na data prometida de cada pedido afetado × preço vigente em `Precos_Produtos`). Use a quantidade realmente descoberta na data (saída da alocação de P5), não a quantidade total do pedido;
   - `estimated`: falta projetada na demanda prevista até `cover_end` × preço;
   - `excess`: na faixa 3, valor do estoque excedente ou da redução de OP sugerida (capital parado).
   - Produto em descontinuação: só o componente `observed`; nunca soma demanda prevista.
3. **Ordenação:** faixa ↑, depois `value_at_risk.observed + peso_estimado × value_at_risk.estimated` ↓ (`peso_estimado` configurável, padrão 0,5), depois pontuação de sinais ↓, depois SKU.
4. **Curva ABC medida:** calcular `abc_measured` (80/95% do faturamento dos últimos 12 meses), expor ao lado da ABC do cadastro e criar o aviso de qualidade `ABC_REGISTRY_DIVERGENCE`. A ABC **não** entra no ranking (F8).
5. **Configuração:** nova `config/prioritization_impact.json` (`estimated_weight`, `tier_rules`, `abc_thresholds`), validada como as demais.
6. **Explicação:** o motivo na fila passa a começar pela faixa e pelo valor, por exemplo: "Pedido confirmado sem cobertura · R$ 63,9 mil em risco (KA-05, KA-02)".

**Alternativas descartadas.**
- Multiplicar a pontuação pela ABC do cadastro: a ABC do cadastro é inconsistente (F8).
- Pontuação única com pontos de impacto somados: fica opaca ("por que 47 > 44?"). A ordenação lexicográfica se explica numa frase.
- Otimização (programação linear): desproporcional para 50 SKUs e difícil de auditar.

**Critérios de aceite.**
- Todo SKU da fila tem `urgency_tier`, `value_at_risk` (com `nature`) e `abc_measured`;
- CI-0047 (descontinuação) não fica à frente de SKU ativo da mesma faixa com valor observado maior;
- as primeiras posições são SKUs da faixa 1 em ordem decrescente de valor observado. Na estimativa preliminar (carteira − estoque, sem descontar as OPs), CI-0041 (~R$ 64 mil) e CI-0004 (~R$ 59 mil) lideram; confirme com o valor pós-alocação e registre os números reais no doc da subetapa;
- `ABC_REGISTRY_DIVERGENCE` aparece em Dados da planilha, com contagem (37 SKUs divergentes na base atual);
- teste de propriedade: dentro de uma faixa, a ordem nunca contradiz o valor observado;
- a decomposição em `/execucoes` (comparação de snapshots) explica a mudança de posição.

**Casos congelados.** VC-04 ("prioridade ≤ 5 não fica sem ação") e VC-10 ("priority_top_10") podem mudar de SKU: reexecute e revise com registro. Proposta: **VC-32** "Descontinuado não lidera a fila por contagem de sinais".

**Esforço.** 1 dia.

---

### P3. Excesso do rótulo "Priorizar produção"

**Sintoma.** 24 dos 43 SKUs da fila saem como "Priorizar produção". As 21 faltas inevitáveis recebem todas esse rótulo, inclusive com quantidade 0, produto em descontinuação ou falta só na previsão.

**Causa raiz.** `src/caderno_inteligente/action_labels.py:127-132`: `atraso_inevitavel` e `antecipar_op` viram `priorizar_producao` sem considerar se existe uma alavanca de produção. Pelo fato F1, na maioria dos casos **nenhuma produção nova chega a tempo**. Além disso, `:141` sobe para `priorizar_producao` todo `produzir` que esteja no top 10 da fila.

**Solução recomendada: uma tabela de decisão por alavanca.** A pergunta é "o que o usuário pode fazer agora?". Avalie as linhas na ordem; a primeira que casar vence.

| # | Condição | Rótulo do desafio | Texto da ação |
|---|---|---|---|
| 1 | Previsão com histórico insuficiente | Investigar | (como hoje) |
| 2 | Pedido confirmado sem cobertura **e** 2 ou mais clientes disputando o estoque | **Priorizar parceiro** | "Atender {cliente A} antes de {cliente B}" (vem da alocação de P5) |
| 3 | OP ainda não iniciada pode ser antecipada (`antecipar_op`) | Priorizar produção | "Antecipar OP-xxxx" |
| 4 | Pedido confirmado sem cobertura, 1 cliente, produto ativo, com ordem urgente de quantidade > 0 | Priorizar produção | "Garantir {n} un. e renegociar {pedido}" |
| 5 | Pedido confirmado sem cobertura, sem alavanca de produção (quantidade 0 ou produto em descontinuação) | **Monitorar** | "Renegociar {pedido}: o estoque e a OP existentes não cobrem a data; sem nova produção" |
| 6 | Falta só na demanda prevista (sem pedido afetado) | Produzir (com ordem urgente) ou Monitorar | O motivo diz "falta **estimada** pela previsão" |
| 7 | `rever_op` | Investigar | (como hoje) |
| 8 | `produzir` urgente, faixa 1 ou 2 de P2 | Priorizar produção | |
| 9 | `produzir` no horizonte | Produzir | |
| 10 | `monitorar_excesso` | Monitorar | |
| 11 | Nenhuma das anteriores | Sem ação necessária | |

- Troque o critério "posição ≤ 10" pela faixa de urgência de P2: a posição sozinha não justifica urgência.
- Cada rótulo ganha `lever` (`alocar`, `antecipar_op`, `produzir_agora`, `renegociar`, `produzir_futuro`, `rever_op`, `nenhuma`) e `decide_by`: data da decisão, que é a data de liberação da ordem urgente, a data prometida do pedido ou a data de decisão do evento.
- Novo resumo "Decisões de hoje" (`decide_by ≤ referência + 7 dias`): responde "quais decisões precisam ser tomadas agora?" (PDF, pergunta 10). Pode ficar no Início, respeitando o orçamento de volume da rota `/`.

**Critérios de aceite.**
- Nenhum rótulo cobre mais de 40% da fila;
- todo "Priorizar produção" tem alavanca de produção real: `suggested_quantity > 0` ou OP antecipável;
- CI-0047 e CI-0050 (descontinuação) nunca saem como Priorizar produção nem Produzir;
- as 5 faltas só na previsão (F2) dizem "estimada" no motivo;
- os 5 SKUs disputados (F3) saem como Priorizar parceiro;
- `decide_by` presente em todo SKU com ação.

**Casos congelados.** **VC-20** espera `challenge_code: priorizar_producao` para o CI-0041. Pela nova tabela, ele passa a **Priorizar parceiro** (dois clientes disputando). Revise o caso com registro em `adjustments`. VC-10 e VC-11 também precisam ser reexecutados.

**Esforço.** 0,5 a 1 dia, depois de P5.

---

### P4. Capacidade acaba antes do horizonte

**Sintoma.** 30 de 43 SKUs ficam com capacidade "a confirmar"; Acessórios, Executivo e Refis têm status de família "a confirmar". A Volta às Aulas fica sem avaliação de capacidade.

**Causa raiz.** `src/caderno_inteligente/capacity_plan.py:74`: uma ordem com `release_week > max(weeks)` vira `a_confirmar`. O calendário termina em 03/01/2027 (F9) e o horizonte do plano vai até 28/02/2027.

**Solução recomendada: estender o calendário com capacidade estimada, sempre rotulada.**
1. Para cada família, gerar as semanas de `max(weeks) + 1` até `horizon_end`, com natureza `estimada`:
   - **central:** capacidade máxima − média dos compromissos base das últimas 8 semanas observadas;
   - **conservador:** menor capacidade disponível observada (Escolar: 480/semana), usada como cenário de sensibilidade.
2. Novos status: `ok_estimado` ("Cabe na capacidade estimada") e `insuficiente_estimado` ("Não cabe nem na capacidade estimada"). `a_confirmar` só sobra se o método estiver desligado na configuração.
3. Configuração em `config/capacity_extension.json` (ou chaves novas em `supply_plan.json`): `method: "media_compromissos_8_semanas"`, `scenario: "central"`, `enabled: true`.
4. Tela `/capacidade`: semanas estimadas com hachura ou cor distinta e a legenda "estimada: além do calendário da base". No pico, mostrar os dois cenários.

**Alternativa descartada.** Cortar o horizonte no fim do calendário: esconde exatamente a Volta às Aulas, o maior risco operacional da base.

**Critérios de aceite.**
- `a_confirmar` = 0 com o método ligado;
- toda semana estimada tem `nature: "estimada"` e `method`;
- a família Escolar no pico de jan–fev sai `insuficiente_estimado`, com quantidade sem programação > 0;
- desligar o método reproduz exatamente a saída atual (teste de regressão).

**Casos congelados.** VC-29 aceita `insuficiente` e `a_confirmar`; inclua `insuficiente_estimado` na lista do caso, com registro.

**Esforço.** 0,5 dia.

---

### P5. Falta alocar produto escasso entre parceiros e regiões

**Sintoma.** O PDF pergunta "Para quais parceiros ou regiões determinado produto deveria ser priorizado?" e "Quais produtos, parceiros ou regiões apresentam risco de ruptura?". Hoje o sistema só lista os pedidos afetados e diz "renegociar prazos".

**Causa raiz.** Não existe módulo de alocação. `supply_plan.affected_orders` (`supply_plan.py:167`) atende a carteira em ordem de data prometida e só reporta quem atrasa, sem escolher.

**Solução recomendada: novo módulo `src/caderno_inteligente/allocation.py`, com pontuação transparente por pedido e atendimento parcial.**

1. **Oferta por SKU:** estoque do CD na data de referência, mais o recebimento das OPs abertas na conclusão prevista, mais as ordens planejadas na data de chegada. São as mesmas séries do plano de suprimento; não recalcule.
2. **Demanda:** pedidos abertos da carteira. A demanda prevista **não** é alocada a clientes.
3. **Pontuação de cada pedido** (`allocation_score`), com pesos em `config/allocation.json` e cada componente exposto como evidência:

   | Componente | Fonte | Natureza | Padrão |
   |---|---|---|---|
   | Urgência: dias até a data prometida (atrasado na referência pontua mais) | Carteira | observado | peso 3 |
   | Canal direto: a ruptura é venda perdida ao consumidor | Parceiros_Canais.Tipo | cadastral | peso 2 |
   | Cobertura do SKU no parceiro baixa (≤ 30 dias), só se houver sell-out suficiente | partner_insights | estimado | peso 2 |
   | Estoque acumulando no parceiro, ou cobertura ≥ 90 dias | partner_insights | estimado | peso −3 (atende por último) |
   | Sem sell-out do par | — | ausente | 0 (**nunca** infere; o motivo diz "sem dado do parceiro") |
   | Tamanho do pedido (atendimento integral de pedido pequeno libera mais clientes) | Carteira | observado | peso 1, opcional |

   Não use o faturamento por cliente de `Vendas_24m` como peso estratégico: ele é um rateio uniforme (F4) e daria um peso falso. Na base atual, o sell-out só existe em 2 dos 22 pedidos afetados, então a urgência e o canal decidem a maioria. O motivo precisa dizer isso.
4. **Algoritmo:** ordenar os pedidos do SKU pela pontuação (desempate: data prometida, depois código do pedido). Percorrer a oferta no tempo e atender integralmente enquanto der. O primeiro pedido que não couber recebe o que sobra (atendimento parcial, se `allow_partial`) e o restante na data em que a próxima chegada cobrir. Saída por pedido: `allocated_now`, `allocated_later` com `expected_date`, `delay_days`, `rank`, `score_components` e `reason`.
5. **Agregações:**
   - por SKU: frase de decisão, no formato (números apenas ilustrativos) "Atender KA-02 (534 un.) integralmente; KA-05 recebe N un. agora e o restante em dd/mm com a OP-xxxx";
   - **por região** (`Parceiros_Canais.Região`; os canais diretos são "Nacional", e a Loja própria é "Sudeste"): unidades e reais descobertos, número de pedidos e SKUs. Responde "quais regiões têm risco de ruptura";
   - por parceiro: pedidos descobertos e valor. Alimenta "Priorizar parceiro" no nível do parceiro, além do critério atual de reposição.
6. **API:**
   - `GET /api/allocation` (todos os SKUs com disputa ou falta; filtros `sku`, `regiao`, `cliente`) e o bloco `allocation` em `/api/priorities/{sku}`;
   - `GET /api/allocation/regions` para o resumo por região.
7. **Tela:**
   - detalhe do SKU: bloco "Quem atender primeiro", com uma linha por pedido e os componentes no tooltip;
   - fila: o motivo do SKU disputado vira "Atender KA-02 antes de KA-05";
   - Comercial: resumo por região. Use cartões ou uma tabela de até 5 colunas e confira o orçamento de volume da rota.
8. **Interação com P2:** o `value_at_risk.observed` do ranking passa a ser o valor **depois** da alocação (o que de fato fica descoberto).

**Alternativas descartadas.**
- Só FIFO pela data prometida: é o que existe hoje, sem decisão.
- Programação linear: sem dado de margem ou penalidade por cliente na base, otimizaria pesos inventados.
- Ratear proporcionalmente: atrasa todos e não responde "quem primeiro".

**Critérios de aceite.**
- Para cada um dos 5 SKUs disputados (F3) há uma ordem de atendimento com motivo;
- a soma alocada nunca passa da oferta acumulada em nenhuma data (teste de propriedade);
- um pedido sem sell-out do par nunca recebe ponto de cobertura;
- o resumo por região soma o total descoberto;
- mudar um peso em `allocation.json` muda a ordem de forma previsível (teste);
- a resposta traz `requires_human_review: true` e a limitação "alocação sugerida; não reserva estoque nem altera pedidos".

**Casos congelados.** Propostas: **VC-33** "SKU disputado tem ordem de atendimento" (CI-0041) e **VC-34** "Parceiro com estoque acumulando é atendido por último" (fixture sintética).

**Esforço.** 1,5 a 2 dias. É o item de maior valor para o PDF.

---

### P6. Ampliar mix, Recomendar recompra e Reativar nunca disparam

**Sintoma.** As regras existem (`action_labels.py:44-46`, `direct_channels.py`), têm casos congelados com fixture (VC-14 a VC-16) e nunca aparecem na base real.

**Causa raiz.** São os dados, não o código:
- **Ampliar mix e Reativar** dependem de lacunas de faturamento num canal; `Vendas_24m` não tem nenhuma (F4);
- **Recompra** depende de meses sem sell-in num par que vende; o Sell_In é contínuo nos 12 meses (F5);
- uma ampliação de mix por "penetração relativa entre parceiros" também não dispara: a participação varia de 0,94 a 1,03 (F4). Usar a ausência do SKU no painel de sell-out como lacuna de mix seria **inferir oportunidade de dado ausente**, o que o projeto proíbe (F5).

**Solução recomendada.**
1. **Cobertura de regras** (`GET /api/rules/coverage`): para cada regra e rótulo, mostrar:
   - quantas vezes disparou na base;
   - a condição em linguagem simples;
   - se for zero, **por que** (com o número que comprova, por exemplo "Vendas_24m tem faturamento em 100% dos meses para todos os pares canal × SKU");
   - que dado faria a regra disparar;
   - o caso congelado que comprova que ela funciona (VC-14, VC-15, VC-16).

   Exibir em Bastidores › Auditoria e numa linha do roteiro de demonstração.
2. **Uma oportunidade real que dispara: "ampliar visibilidade".** Liste os 23 pares KA × SKU com pedido em carteira e sem sell-out, ordenados pelo valor do pedido. O texto: "pedir ao parceiro o sell-out destes SKUs". Use o rótulo **Investigar** com `signal: "SELL_OUT_REQUEST"`. Isso ataca o objetivo do PDF de "reduzir a lacuna" sem inventar oportunidade.
3. **Não** criar dado sintético na base real para forçar disparos.

**Critérios de aceite.**
- `/api/rules/coverage` lista todas as regras do `PRECEDENCE` de `action_labels.py` e as 11 regras operacionais, com a contagem igual à das saídas reais;
- toda regra com zero disparos tem motivo e um caso congelado de referência;
- a lista de "pedir sell-out" tem exatamente os pares KA com carteira e sem sell-out.

**Esforço.** 0,5 dia.

---

### P7. Inconsistências menores

**P7a – Texto do teto da razão sazonal.**
- Causa: `src/caderno_inteligente/forecast_candidates.py:90` e `:140` dizem "0,5–2,0"; `config/forecast_engine.json:40` usa `ratio_bounds: [0.5, 3.0]`.
- Solução: montar a descrição a partir de `ratio_bounds`, sem texto fixo. Teste: a descrição do `seasonal_level` em `/api/model-benchmark` contém o teto configurado.
- Esforço: 15 minutos.

**P7b – Dois cálculos de estoque no parceiro.**
- Situação: `partner_insights.py` (fotografia atual: cobertura, acúmulo, conta de estoque) e `partner_stock_projection.py` (projeção para frente, cenários com e sem reposição, erro de 26% no sell-out; sem tela e marcada "em revisão pelo grupo"). Não se contradizem: uma olha para trás, a outra para frente.
- Solução recomendada: **integrar** a projeção como evidência para frente nas linhas comerciais com dado suficiente:
  - `days_until_stockout_without_replenishment` (quando o estoque do parceiro acaba se a empresa parar de enviar);
  - `replenishment_to_target` (quantidade para fechar o próximo mês com 30 dias);
  - o erro medido (WAPE de 26%) como confiança.

  O rótulo "Repor" ganha uma quantidade sugerida, sempre como estimativa. A rota `/api/partner-stock-projection` fica como detalhe. A limitação "não alimenta recomendação comercial" sai do módulo: alinhe com o Felipe, que escreveu o módulo, antes de mudar isso (decisão D6).
- Esforço: 0,5 dia.

**P7c – Sell-in muito maior que o faturamento do parceiro.**
- Solução: aviso de qualidade `SELLIN_BILLING_DIVERGENCE` por parceiro em `/api/data-quality`, com a razão (KA-05: 6,9×) e o texto "as duas fontes não fecham; o sistema usa Sell_In e Sell_Out para o parceiro e Vendas_24m para o total do SKU".
- Incluir também o aviso `BILLING_UNIFORM_SPLIT` (F4): "o faturamento por cliente é quase proporcional entre clientes e não é usado para padrões por parceiro".
- Os dois aparecem em Dados da planilha e no mapa da jornada de P1.
- Esforço: 0,5 dia.

---

### P8. IA e impacto mensurável

**Sintoma.** O PDF pergunta "como os dados e a **IA** poderiam ajudar". A solução é estatística e determinística (boa para auditoria), com um benchmark de ML offline. A Validação não afirma nenhum ganho de processo (F10).

**Solução recomendada em três partes, da mais barata à mais cara.**

1. **Narrativa honesta da IA já existente (sem código):** a previsão é aprendida dos dados e testada contra statsforecast, scikit-learn, LightGBM e Prophet (`/modelo`). O modelo sazonal simples venceu no backtest com pico e por isso é o oficial. Colocar no roteiro de demonstração.
2. **Medição de impacto com o que já existe:**
   - **Tempo de análise automático:** no frontend, medir o tempo entre abrir o detalhe do SKU e registrar a decisão, e preencher `analysis_minutes` (editável pelo usuário; informar que o tempo é medido). O backend já aceita o campo;
   - **Teste moderado com 3 usuários** (protocolo em `docs/semana-4-validacao-v2.md`), cronometrando as tarefas "o que produzir", "quem atender" e "onde há risco". Com 20 registros, a Validação libera a comparação contra as 22 h/semana informadas;
   - **Valor em risco endereçado** (observado): soma de `value_at_risk.observed` dos SKUs com decisão registrada. É um número de impacto que não depende de dado futuro;
   - **Modelo × Forecast_Comercial (consenso S&OP):** para os meses em comum (out a dez/26), mostrar onde o modelo e o S&OP divergem mais de 20% por SKU, como pauta de revisão. O erro do S&OP não é mensurável, porque a base só traz meses futuros.
3. **Resumo em linguagem natural por LLM (opcional e atrás de flag):**
   - endpoint `POST /api/ai/brief` recebe a dataset sha e devolve um texto curto: "Decisões de hoje" (P3) + alocações (P5) + riscos por região, gerado pela API da Anthropic a partir **apenas** do JSON das evidências;
   - **guardas obrigatórias:**
     - temperatura baixa e prompt que proíbe números fora do payload;
     - verificação automática depois da geração: todo número e todo SKU do texto precisa existir no payload; se falhar, devolver o resumo determinístico por template;
     - rótulo visível "texto gerado por IA a partir das evidências; números conferidos";
     - cache pela sha da base e pela versão da configuração;
   - configuração:
     - `AI_BRIEF_ENABLED=false` por padrão;
     - `ANTHROPIC_API_KEY` secreta só no backend (nunca no bundle; o teste `check:bundle` já varre o bundle);
     - modelo configurável por `AI_BRIEF_MODEL`, sugerido `claude-haiku-5-5` pelo custo e pela latência;
     - timeout curto, compatível com a função da Vercel;
   - sem a chave, a tela mostra o template determinístico. A demonstração não pode depender de rede.

**Critérios de aceite.**
- `analysis_minutes` preenchido automaticamente em toda decisão nova;
- a Validação mostra "valor em risco endereçado";
- com a flag desligada, nenhuma chamada externa acontece (teste);
- com a flag ligada e uma resposta simulada que contém um número inventado, o endpoint devolve o template (teste).

**Esforço.** Partes 1 e 2: 1 dia. Parte 3: 1 dia.

## 3. Mapa de dependências

```text
16.0 linha de base ──► P7a, P7c, P1 (independentes, rápidos)
                         │
                         ▼
                    P5 alocação ──► P2 ranking (usa o valor descoberto pós-alocação)
                         │                 │
                         └──────► P3 rótulos (usa a alocação e a faixa de P2)
P4 capacidade (independente) ──► reavaliar P3 (capacidade insuficiente_estimado)
P6 cobertura de regras (depois de P1 a P3, para contar os rótulos finais)
P7b projeção no parceiro (depois de P1)
P8 (no fim; o resumo por IA consome P3 e P5)
```

## 4. Decisões para o usuário aprovar antes do código

| ID | Decisão | Recomendação |
|---|---|---|
| D1 | Permitir **alocar o estoque do CD entre pedidos confirmados** (P5). O princípio atual diz "nunca distribuir dados globais por parceiro". | Aprovar: a alocação usa só pedidos confirmados (observados), não distribui previsão e é sugestão com revisão humana. Registrar a exceção no `docs/decisions.md`. |
| D2 | Mudar a ordenação oficial da fila para faixa de urgência + valor em risco (P2). | Aprovar. A pontuação de sinais continua visível. |
| D3 | Peso da falta **estimada** no valor em risco. | 0,5. |
| D4 | Revisar os casos congelados VC-20 (CI-0041 vira Priorizar parceiro), VC-29 (aceitar `insuficiente_estimado`) e, se mudarem, VC-04 e VC-10. | Aprovar, com registro em `adjustments`. |
| D5 | Método da capacidade estimada (P4). | Média dos compromissos das últimas 8 semanas, com o mínimo observado como cenário conservador. |
| D6 | Integrar a projeção de estoque do Felipe às recomendações comerciais (P7b). | Aprovar, depois de alinhar com o Felipe. |
| D7 | Implementar o resumo por LLM (P8, parte 3) antes de 17/10. | Só se P1 a P5 estiverem prontos até 14/10; senão fica fora. |

## 5. Plano de subetapas sugerido (com o nome do commit)

| Subetapa | Conteúdo | Dias | Commit sugerido |
|---|---|---|---|
| 16.0 | `docs/etapa-16/antes.json`, casos VC-31 a VC-34 como `pending`, configurações novas com valores aprovados, P7a | 0,5 | `chore(etapa-16.0): linha de base, casos-alvo e texto do teto sazonal` |
| 16.1 | P1 canais diretos + mapa da jornada + P7c avisos de fonte | 1 | `fix(etapa-16.1): canais diretos com visibilidade observada e mapa da jornada` |
| 16.2 | P5 alocação (módulo, API, bloco no SKU, resumo por região) | 2 | `feat(etapa-16.2): alocação de estoque escasso por pedido, parceiro e região` |
| 16.3 | P2 faixa de urgência + valor em risco + ABC medida | 1 | `feat(etapa-16.3): fila por urgência e valor em risco, ABC medida` |
| 16.4 | P3 tabela de decisão por alavanca + `decide_by` + "Decisões de hoje" | 1 | `fix(etapa-16.4): rótulos por alavanca de decisão e decisões de hoje` |
| 16.5 | P4 capacidade estendida | 0,5 | `feat(etapa-16.5): capacidade estimada além do calendário` |
| 16.6 | P6 cobertura de regras + pedir sell-out; P7b projeção nas linhas comerciais | 1 | `feat(etapa-16.6): cobertura de regras, pedido de sell-out e projeção no parceiro` |
| 16.7 | P8 tempo automático, valor endereçado, modelo × S&OP; `depois.json`, `antes-depois.md`, docs e roteiro | 1 | `feat(etapa-16.7): impacto mensurável, comparação final e roteiro` |
| 16.8 (opcional) | P8 resumo por LLM atrás de flag | 1 | `feat(etapa-16.8): resumo das decisões por IA com verificação de números` |

O total sem a 16.8 é de cerca de 8 dias de trabalho. Com o prazo de 17/10, a ordem de corte é: 16.6 e 16.7 encolhem primeiro; 16.1 a 16.4 são o mínimo para a demonstração.

## 6. Metas de saída (antes → depois, na base atual)

| Métrica | Antes (10/10) | Meta |
|---|---|---|
| Linhas comerciais de canal direto como "dados insuficientes" | 22 | 0 |
| Cobertura exibida dos canais diretos | 0% | 100% (fonte: venda direta) |
| Participação das unidades com venda ao consumidor observada | não calculada | exibida no mapa da jornada |
| SKUs com "Priorizar produção" | 24 de 43 | ≤ 40% da fila, todos com alavanca de produção |
| Descontinuados como Priorizar produção | 1 (CI-0047, 2º lugar) | 0 |
| SKUs disputados com ordem de atendimento | 0 de 5 | 5 de 5 |
| Resumo de risco por região | inexistente | presente |
| SKUs com capacidade "a confirmar" | 30 | 0 (com o método ligado) |
| Regras com zero disparos explicadas | 0 | todas |
| Decisões com tempo de análise | 0 | automático em toda decisão nova |
| Casos congelados | 30 aprovados | 34, todos aprovados ou revistos com registro |

## 7. Fora de escopo

- Alterar a planilha ou criar dados sintéticos na base real.
- Trocar o motor de previsão (o v2 foi promovido na Etapa 15 com critério; o benchmark não mostrou ganho).
- Otimização matemática de produção ou de alocação.
- Login obrigatório, que pertence à fase 3 dos colegas.
