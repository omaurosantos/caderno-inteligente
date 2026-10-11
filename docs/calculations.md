# Cálculos

Todos os cálculos são determinísticos, partem da planilha somente leitura e mantêm dado ausente como `null`, nunca como zero. A unidade de análise operacional é o **SKU global** (`analysis_scope = "SKU global"`): nada é distribuído por parceiro ou canal. Desde a Etapa 15, o plano de suprimento projeta o SKU por dia (resumido por semana) e a capacidade é alocada por linha e semana.

## 1. Indicadores por SKU (`indicators.py`)

| Indicador | Fórmula | Fontes |
|---|---|---|
| Demanda diária de referência | média da previsão oficial dos 3 próximos meses ÷ 30,4; sem previsão, média de vendas dos 3 últimos meses; por último, `Venda média/dia` (`demand_source`) | previsão, `Vendas_24m`, `Produtos` |
| Cobertura calculada | `estoque atual / demanda diária de referência` | `Estoque_Atual` e acima |
| Cobertura pelo cadastro | `estoque atual / Produtos.Venda média/dia` (`coverage_days_registered`, só comparação) | `Estoque_Atual`, `Produtos` |
| Divergência do cadastro | aviso `REGISTERED_DEMAND_DIVERGENCE` quando \|demanda de referência ÷ venda média cadastrada − 1\| > 0,20 | idem |
| Diferença de cobertura | `cobertura informada - cobertura calculada` | `Estoque_Atual`, `Produtos` |
| Pedidos em carteira | `soma(quantidade)` por SKU | `Carteira_Pedidos` |
| Produção em ordem | `soma(quantidade)` por SKU | `Ordens_Producao` |
| Primeira conclusão | `mínimo(conclusão prevista)` por SKU | `Ordens_Producao` |
| Estoque projetado | `estoque atual + ordens - carteira` | `Estoque_Atual`, `Ordens_Producao`, `Carteira_Pedidos` |
| Lacuna operacional | `máximo(0, carteira - estoque atual - produção aberta)` | idem |
| Data crítica | menor data disponível entre primeira promessa e primeira conclusão prevista; `critical_date_reason` informa qual foi usada | `Carteira_Pedidos`, `Ordens_Producao` |
| Sell-in / sell-out acumulados | `soma` por SKU | `Sell_In`, `Sell_Out` |
| Diferença sell-in/out | `sell-in - sell-out` | `Sell_In`, `Sell_Out` |
| Visibilidade de sell-out | existe ao menos um parceiro com sell-out para o SKU | `Sell_Out` |
| Capacidade familiar | primeira semana disponível e médias de ocupação no horizonte | `Capacidade_Semanal` |

- `has_sell_out = false` significa ausência de observação. O sell-out fica `null` e `missing_data` inclui `sell_out_quantity`.
- A **lacuna operacional** é uma quantidade para análise, não uma ordem recomendada.
- A **capacidade** média por família continua como contexto; a viabilidade das ordens vem da alocação semanal (seção 4.1).

## 2. Regras e priorização

Seis regras saem dos indicadores e cinco do plano datado (falta projetada, OP de produto em descontinuação, excesso projetado, falta de capacidade e estoque acumulando no parceiro). O score é a soma dos pesos configurados dos sinais ativos. Detalhes em [regras](rules.md) e [priorização](prioritization.md).

Desde a Etapa 16.3, a ordem da fila **não** é mais o score: é faixa de urgência ↑, depois valor em risco ponderado ↓, depois score ↓, depois SKU (`impact.py` e `prioritization.prioritize`):

```text
valor_ponderado = value_at_risk.observed + estimated_weight × value_at_risk.estimated      # estimated_weight = 0,5
observed  = Σ (unidades sem cobertura na data prometida, depois da alocação) × preço vigente
estimated = falta projetada só na previsão, até o fim da cobertura × preço
excess    = valor do estoque excedente ou da redução de OP sugerida (faixa 3)
faixa 1 = pedido confirmado sem cobertura; 2 = ação de produção em até 4 semanas ou falta só na previsão;
faixa 3 = rever OP ou excesso; 4 = produzir no horizonte ou monitorar
```

Produto em descontinuação só conta `observed`. Preço ausente deixa o valor `null`. A curva ABC medida (80% e 95% do faturamento de 12 meses) é exposta, mas não entra na ordem. Parâmetros em `config/prioritization_impact.json`.

## 3. Previsão de demanda (`official_forecast.py`, motor v2 desde a Etapa 15.1)

- **Série:** faturamento mensal por SKU (`Vendas_24m`), com meses sem venda preenchidos com zero entre o primeiro e o último mês observado.
- **Histórico mínimo:** 6 meses. Abaixo disso, `status = insufficient_data` e nenhuma previsão numérica é gerada.
- **Modelo (sem seleção por SKU):** o primeiro da cadeia que o histórico comporta:
  1. mês do ano anterior ajustado pelo nível (`seasonal_level`, ≥ 15 meses): `nível recente (3 meses) × (mês do ano anterior ÷ nível de um ano antes)`, com a razão limitada a 0,5–3,0;
  2. sazonal ingênuo de 12 meses;
  3. média móvel de 3 meses.
- **Horizonte:** 6 meses; `forecast_next_month` e `forecast_total_3m` continuam valendo para os 3 primeiros, e `forecast_total_6m` soma os 6.
- **Erro (`backtest_wape`):** `Σ|real − previsto| / Σ real` em 7 origens rolantes (2025-11 a 2026-05), cada uma prevendo os 3 meses seguintes só com os dados anteriores a ela; o erro também é separado em meses de pico (nov, jan, fev) e normais. Novembro não cai em nenhuma origem (o modelo exige 15 meses); ele é conferido pelo caso congelado VC-28.
- **Promoção:** o v2 virou oficial porque atendeu aos quatro critérios fixados antes do teste (WAPE 10,1% → 8,0%; viés no pico +0,7%; viés agregado sem piora; 45 SKUs melhores que a baseline contra 40). O motor v1 (`forecasting.py`, holdout dos 3 últimos meses entre média móvel e sazonal ingênuo) continua reproduzível no laboratório.
- **Confiança da previsão:**
  - alta: WAPE ≤ 20%;
  - média: WAPE ≤ 40%;
  - baixa: WAPE acima de 40% ou indefinido.
- **Tendência:** compara a média dos 3 meses recentes com a dos 3 anteriores.
  - Variação acima de 10% → crescente; abaixo de −10% → decrescente; caso contrário, estável.
  - Com média anterior zero: crescente se a recente for positiva, estável se também for zero.
- **Horizonte do v1:** 3 meses; no v2, 6 meses (acima).

### 3.0 Benchmark de modelos (`model_benchmark.py`, fora do pipeline oficial)

- **Para que serve:** comparar a previsão oficial com modelos de bibliotecas conhecidas no mesmo protocolo. É evidência; trocar o modelo oficial continua exigindo os critérios de `promotion`.
- **Protocolo:** as mesmas origens de `evaluation` (2025-11 a 2026-05), cada uma prevendo os 3 meses seguintes só com os meses até ela. O erro é o WAPE agrupado de todas as origens e SKUs, também separado em meses de pico e normais, com o viés `Σ(previsto − real) ÷ Σ real`.
- **Modelos:** motor oficial; repetir o último mês (baseline); AutoETS, AutoARIMA e AutoTheta sazonais (statsforecast, sazonalidade de 12 meses); gradient boosting do scikit-learn e LightGBM, cada um como um único modelo para todos os SKUs, prevendo a razão entre o mês-alvo e o nível recente a partir do mês, do horizonte, do mesmo mês do ano anterior e do nível de um ano antes; Prophet, um modelo por SKU com sazonalidade anual multiplicativa (lento, só com `--include-slow`).
- **Lacunas:** quando um modelo não prevê um SKU numa origem, vale a previsão oficial naquele ponto e o ponto é contado em `fallback_points`. Biblioteca ausente vira `unavailable` e erro na execução vira `failed`, sempre sem erro numérico.
- **Resultado em 09/10/2026** (planilha com 24 meses, 50 SKUs): oficial 8,0% (pico 7,9%); AutoARIMA 13,3% (22,8%); LightGBM 14,4% (27,4%); gradient boosting 14,9% (29,0%); AutoETS 16,0% (22,4%); AutoTheta 16,9% (24,8%); baseline 18,9% (26,8%); Prophet 36,4% (32,9%), medido no teste exploratório. Nenhum modelo superou o oficial. Com 24 meses, os modelos sazonais de prateleira não têm dois ciclos completos para aprender a sazonalidade anual; Holt-Winters ficou de fora por exigir 24 meses de treino.

### 3.1 Faturamento estimado (`revenue.py`)

```text
faturamento estimado do mês = previsão em unidades do mês × preço unitário vigente do SKU
```

- **Preço vigente:** `Precos_Produtos` (aba opcional). Sem preço válido (> 0) nela, usa o último preço faturado do SKU em `Vendas_24m`. Sem nenhum, o SKU fica sem estimativa (`null`, nunca zero). Divergência entre as duas fontes é sinalizada em `price_conflict`; vale o preço da tabela.
- **Agregação:** soma apenas SKUs com estimativa; os demais são listados em `skus_excluded`.
- **Horizonte:** telas e totais "3 meses" usam os 3 primeiros meses da previsão; `revenue_total_6m` soma os 6.
- **Erro em reais (`backtest_wape`):** o mesmo teste rolante da previsão oficial, em unidades × preço (no v1, o teste dos últimos 3 meses).
- **Variação:** estimativa de 3 meses contra o faturamento observado nos 3 meses anteriores dos mesmos SKUs.
- **Forecast comercial:** `Forecast_Comercial` × mesmo preço, em todos os meses em comum com a previsão de 6 meses (out–dez); é comparação, não erro.
- **Limites:** preço constante, receita bruta, global por SKU. Estimativa, não faturamento realizado.

### 3.2 Eventos e sazonalidade (`events.py`)

```text
fator do mês (família) = média das ocorrências de [unidades do mês ÷ média dos meses sem evento num raio de 6 meses]
cenário do mês = previsão base × fator do mês  (fator 1 sem evento ou sem evidência)
data de decisão = início do evento − lead time do SKU
```

- **Linha de base:** meses sem evento que afete a família, raio de 6 meses, mínimo de 3 meses; acompanha a tendência da família.
- **Fator:** média das ocorrências (mínimo de 1 e 12 meses de histórico da família), limitada por `config/event_factors.json` (padrão 0,5 a 3,0, com `capped` registrado).
- **Alerta:** evento que cobre a família, não terminou e (começa até o fim do horizonte **ou** `início − lead time − 30 dias` cai dentro do horizonte).
- **Sem dupla contagem:** SKU com previsão sazonal (sazonal ingênuo, combinação ou o motor oficial v2) só recebe alerta; na base, todos os 50.
- **Sem fator inventado:** evento sem histórico direto, família com histórico curto ou sem ocorrência mensurável geram só alerta.
- **Quantidade oficial:** não muda; o cenário mostra a quantidade que resultaria se o próximo mês fosse afetado.

### 3.3 Canais diretos (`direct_channels.py`)

```text
tendência = média mensal dos últimos 3 meses ÷ média dos 3 meses anteriores − 1   (faixa neutra ±10%)
participação = faturamento do canal ÷ faturamento de todos os canais em Vendas_24m
variação anual = últimos 3 meses ÷ os mesmos 3 meses do ano anterior − 1
```

- **Sinais por SKU e canal:** `NOT_SOLD` (nenhum faturamento nos 24 meses), `STOPPED` (vendeu e ficou 2 meses ou mais sem faturar), `DECLINING`, `GROWING`, `DISCONTINUING_PRODUCT` (`Produtos.Status`) e `OPEN_BACKLOG` (pedido não encerrado no canal).
- **Sugestão (precedência):** sem faturamento e produto ativo → ampliar mix; sem faturamento e produto em descontinuação → monitorar saída de linha; parou de vender → reativar; produto em descontinuação ainda vendido → monitorar saída de linha; queda → investigar; crescimento → acompanhar; senão, sem ação. Toda sugestão exige revisão humana.
- **Concentração:** participação dos 5 maiores SKUs e número de SKUs para chegar a 80% do canal.
- **Ausência não é zero:** SKU sem faturamento fica com valores nulos. Não há estoque por canal.
- Limiares em `config/direct_channel_thresholds.json`.

### 3.4 Rótulos de ação do desafio (`action_labels.py`)

Camada derivada: não recalcula nada, só lê o que já existe. Limiares em `config/challenge_actions.json`.

```text
Priorizar parceiro (SKU)  = pedido sem cobertura disputado por ≥ 2 clientes distintos (alavanca "alocar")
Priorizar parceiro (parceiro) = parceiro com ≥ 2 pares Repor E ≥ 1 deles em SKU entre os 10 primeiros da fila
Priorizar produção = alavanca real de produção: antecipar OP, garantir quantidade para pedido sem cobertura,
                     produzir urgente na faixa 1 de urgência, ou decisão de evento em até 30 dias
Recomendar recompra = ação comercial "monitorar" E sell-out recente positivo E ≥ 3 meses de sell-in
                      E meses sem sell-in ≥ max(2, 2 × intervalo típico entre envios do próprio par)
```

- **Tabela de decisão por alavanca (Etapa 16.4).** A pergunta é "o que o usuário pode fazer agora?". As linhas operacionais são avaliadas na ordem e a primeira que casa vence; a posição ≤ 10 na fila deixou de promover um SKU a Priorizar produção (a posição não justifica urgência).

  | # | Condição | Rótulo | `lever` |
  |---|---|---|---|
  | 1 | previsão com histórico insuficiente | Investigar | `nenhuma` |
  | 2 | pedido sem cobertura e 2 ou mais clientes disputando | Priorizar parceiro | `alocar` |
  | 3 | OP não iniciada que pode ser antecipada (produto ativo) | Priorizar produção | `antecipar_op` |
  | 4 | pedido sem cobertura, produto ativo, ordem urgente de quantidade > 0 | Priorizar produção | `produzir_agora` |
  | 5 | pedido sem cobertura sem alavanca de produção (quantidade 0 ou descontinuação) | Monitorar ("renegociar") | `renegociar` |
  | 6 | falta só na previsão (sem pedido afetado): o motivo diz "estimada pela previsão" | Produzir (com ordem urgente) ou Monitorar | `produzir_agora` ou `nenhuma` |
  | 7 | `rever_op` | Investigar | `rever_op` |
  | 8 | produzir urgente na faixa 1 ou com decisão de evento na janela | Priorizar produção | `produzir_agora` |
  | 9 | produzir no horizonte; a próxima liberação cai na janela de decisão (4 semanas) | Produzir | `produzir_futuro` |
  | 9b | produzir no horizonte; a próxima liberação cai depois da janela | Monitorar ("a liberar em dd/mm") | `produzir_futuro` |
  | 10 | `monitorar_excesso` | Monitorar | `nenhuma` |
  | 11 | demais | Sem ação necessária | `nenhuma` |

- **`decide_by`:** data da decisão (liberação da ordem urgente, data prometida do pedido, fim da janela de decisão ou data do evento), nunca anterior à data de planejamento (prazo vencido → "decidir hoje"). Alimenta "Decisões de hoje" (`decide_by` até a referência + 7 dias).
- **Distribuição na base atual** (50 SKUs): Monitorar 30%, Produzir 26%, Priorizar produção 24%, Priorizar parceiro 10%, Investigar 10%. Nenhum rótulo passa de 30%; o teto exigido era 40%. Descontinuados (CI-0047, CI-0050) nunca saem como Priorizar produção nem Produzir.
- **Precedência:** dado insuficiente, antigo ou divergente vence tudo e vira "Investigar"; depois, risco/urgência; depois, oportunidade; por último, monitorar.
- **Sem inferência:** parceiro sem sell-out suficiente nunca recebe "Repor", "Recomendar recompra" ou "Priorizar parceiro". "Ampliar mix" e "Reativar" só saem dos canais diretos, onde a ausência de faturamento é observada; na base atual não há lacuna de faturamento, então não disparam (a explicação está em `/api/rules/coverage`, com os casos VC-14, VC-15 e VC-16 como prova de que a regra funciona). Linhas de canal direto têm ação `canal_direto` (venda observada, sem estoque intermediário), que não é dado insuficiente.
- **Evidência:** cada rótulo traz os valores usados (posição na fila, cobertura, último sell-in, etc.), as limitações e `requires_human_review`.

### 3.5 Alocação de produto escasso (`allocation.py`)

Responde "quem atender primeiro?" quando o estoque não cobre todos os pedidos. **Exceção D1** em [decisions.md](decisions.md): reparte só dados observados, nunca previsão. Pesos em `config/allocation.json`.

1. **Oferta por SKU:** estoque do CD na referência, mais as OPs abertas na conclusão prevista, mais as ordens planejadas na chegada. São as séries do plano de suprimento; nada é recalculado.
2. **Demanda:** os pedidos abertos da carteira. A demanda prevista **não** é alocada a clientes.
3. **Pontuação de cada pedido** (`allocation_score`, cada componente exposto com natureza e motivo):

   | Componente | Natureza | Peso |
   |---|---|---:|
   | Urgência (dias até a data prometida; vencido na referência pontua mais) | observado | 3 |
   | Canal direto (ruptura é venda perdida ao consumidor) | cadastral | 2 |
   | Cobertura do SKU no parceiro ≤ 30 dias, só com sell-out suficiente | estimado | 2 |
   | Estoque acumulando no parceiro ou cobertura ≥ 90 dias | estimado | −3 |
   | Pedido pequeno (atender integral libera mais clientes) | observado | 1 |
   | Par sem sell-out | ausente | 0 |

   Par sem sell-out nunca ganha ponto de cobertura: o motivo diz "sem dado do parceiro". O faturamento por cliente **não** é peso, porque é um rateio quase uniforme (0,92 a 1,03 da mediana). Na base, o sell-out só existe em 2 dos 22 pedidos afetados, então urgência, canal e tamanho do pedido decidem quase tudo, e o motivo diz isso.
4. **Algoritmo:** ordena os pedidos do SKU pela pontuação (empate: data prometida, depois código do pedido) e percorre a oferta no tempo. Atende integralmente enquanto couber; o primeiro que não couber recebe o que sobra (`allow_partial`) e o restante na data em que a próxima chegada cobrir. Saída por pedido: `allocated_now`, `allocated_later` (data e OP), `delay_days`, `rank` e `reason`. A soma alocada nunca passa da oferta acumulada em nenhuma data.
5. **Agregações:** frase de decisão por SKU ("KA-02 recebe 303 un. agora e o restante em 05/10 com a ordem planejada; KA-05 recebe em 05/10"); risco por região (`Parceiros_Canais.Região`; canais diretos são "Nacional", Loja própria é "Sudeste"), cuja soma é o total descoberto; unidades e valor por parceiro.
6. **Pedido sem data prometida ou SKU sem preço:** valor `null` com o motivo, nunca zero.

Base atual: 17 SKUs com falta, 21 pedidos, 6.626 un. e R$ 401.632,40 sem cobertura na data prometida; 5 SKUs disputados, cada um com ordem de atendimento. O valor `observed` do ranking é o que sobra **depois** desta alocação. É sugestão com `requires_human_review`: não reserva estoque nem altera pedidos.

### 3.6 Visibilidade do consumidor (`visibility.py`)

`journey` em `/api/b2b2c/visibility` mede até onde se vê a venda ao consumidor nos 12 meses (set/2025 a ago/2026):

```text
observado(canal direto) = faturado do canal                      # o faturamento é a venda ao consumidor
observado(parceiro KA)  = min(sell-out informado do par, faturado do par)   # limitado ao faturado
sem visibilidade        = faturado − observado                   # calculado
participação observada  = observado ÷ faturado total
```

Base atual: 328.111 un. faturadas, 246.389 com venda observada (**75,1%**) e 81.722 sem visibilidade. Canal direto 100%; varejista 22,5%; distribuidor 19,8%. Sell-out não é venda zero quando ausente. O sell-out de alguns pares KA passa do faturado (sell-in e faturamento não fecham); o excedente é descartado do cálculo e sinalizado em `exceeds_billing`.

## 4. Plano de suprimento e recomendação operacional (`supply_plan.py`, `recommendations.py`)

Projeção **diária** de 14/09/2026 (`config/supply_plan.json → reference_date`) até o fim da previsão (28/02/2027), resumida por semana:

```text
demanda do dia     = carteira na data prometida (vencida → primeiro dia)
                   + [previsão do mês × dias restantes ÷ dias do mês − carteira do mês]⁺ rateado pelos dias   # sem dupla contagem
entradas do dia    = OPs abertas na conclusão prevista + ordens planejadas
estoque projetado  = estoque atual + entradas − demanda          # pode ficar negativo (falta)
segurança (unid.)  = demanda diária de referência × dias de segurança
chegada mais cedo  = data de planejamento + lead time
ordem planejada    = na 1ª data ≥ chegada mais cedo com estoque < segurança:
                     segurança − estoque projetado + demanda das 4 semanas seguintes − OPs que chegam nelas,
                     arredondada para cima ao lote; liberação = necessidade − lead time
quantidade sugerida = soma das ordens com liberação até a data de planejamento + 4 semanas
```

- **Pedidos afetados:** a carteira tem prioridade sobre a previsão; um pedido é afetado quando o estoque mais as entradas só o cobrem depois da data prometida.
- **Antecipar OP:** há falta (ou pedido atrasado) antes de uma OP ainda não iniciada (Planejada/Liberada) que, iniciada na data de planejamento com a mesma duração, chegaria a tempo.
- **Reduzir OP (excesso):** logo após a chegada, o estoque projetado passa de 90 dias de demanda futura + segurança; reduz em lotes inteiros sem criar falta nesse período.
- **Produto em descontinuação:** sem previsão e sem ordem nova; a OP fica com o necessário para a carteira que o estoque não cobre (em lotes) ou é cancelada.

**Ação principal (precedência):**

| Ordem | Situação | Ação |
|---|---|---|
| 1 | Previsão insuficiente | `investigar_dados`, sem quantidade (`null`) |
| 2 | OP não iniciada pode chegar antes da falta | `antecipar_op` |
| 3 | Falta antes da chegada mais cedo | `atraso_inevitavel` |
| 4 | Ordem planejada com liberação na janela de 4 semanas | `produzir` (`produzir_validar_capacidade` se não couber na linha) |
| 5 | OP a reduzir ou cancelar | `rever_op` |
| 6 | Ordem planejada fora da janela | `produzir` ("liberar a partir de dd/mm") |
| 7 | Cobertura atual acima do limite, sem OP a rever | `monitorar_excesso` |
| 8 | Estoque projetado acima da segurança no horizonte inteiro | `sem_acao_necessaria` |

As ações que também valem ficam em `secondary_actions`. A recomendação traz `planned_orders`, `op_adjustments`, `affected_orders`, `projection` (semanal), `capacity` e a cascata em `calculation`.

**Confiança da recomendação:** parte da confiança da previsão; cai para baixa sem sell-out observado e de alta para média quando alguma ordem não cabe na linha.

Sem plano (entradas sintéticas da validação), vale a conta anterior de "próximo mês". Toda recomendação tem `requires_human_review = true` e não cria, antecipa nem reduz ordem de produção.

### 4.1 Capacidade semanal finita (`capacity_plan.py`)

As ordens planejadas disputam a `Capacidade disponível` de `Capacidade_Semanal` (que já desconta compromissos base e OPs existentes), por família:

1. ordem de atendimento: data de necessidade, depois curva ABC e SKU;
2. consome na semana de liberação; se faltar, antecipa semana a semana até a data de planejamento (pré-produção);
3. o que não couber até a necessidade fica sem programação (`insuficiente`).

**Capacidade estimada além do calendário (Etapa 16.5).** O calendário da base termina em 03/01/2027 e o horizonte do plano em 28/02/2027, o que deixava a Volta às Aulas sem avaliação (`a_confirmar` em 37 SKUs). Para cada família, as semanas seguintes ao calendário são geradas até o fim do horizonte com `nature: "estimada"` e `method`:

```text
central      = capacidade máxima − média de "Compromissos base" das últimas 8 semanas observadas
conservador  = menor "Capacidade disponível" observada na família (sensibilidade)
```

Ordem que cabe só na capacidade estimada fica `ok_estimado`; a que não cabe nem nela fica `insuficiente_estimado`. `a_confirmar` sobra apenas com o método desligado (`config/capacity_extension.json → enabled`), que reproduz a saída anterior. `insuficiente_estimado` não gera `CAPACITY_SHORTFALL` nem muda o score. Linha Escolar: o pico segue `insuficiente` por uma falta **observada** em dez/26 (12.970 un. sem programação no cenário central e 13.600 no conservador); as ordens de fev/27 de CI-0014, CI-0016 e CI-0041 ficam `insuficiente_estimado`. A capacidade estimada **não** é capacidade informada pela empresa.

Premissas: unidades homogêneas por família; consumo na semana de início; compromissos base não validados com a empresa; semanas depois de 28/12/2026 são estimadas; antecipar e reduzir OP não mexem na capacidade.

### 4.2 Produção planejada por mês (`production_plan.py`)

Soma as ordens planejadas do plano de suprimento pelo mês de liberação (`release_date`), no total e por família:

- **agora** (`urgent`): liberação até o fim da janela de decisão; somam exatamente a quantidade sugerida da fila;
- **depois** (`later`): as demais ordens até o fim do horizonte da previsão.

**Mês completo:** um mês de liberação M só é exibido quando `último dia de M + maior lead time entre os SKUs ≤ fim do horizonte`. Depois disso, as ordens que atenderiam necessidades além do horizonte não foram planejadas, e o mês pareceria menor do que é. Na base atual (horizonte em 28/02/2027, maior lead time de 27 dias), janeiro é completo (31/01 + 27 = 27/02) e fevereiro fica de fora. O total do horizonte continua contando as ordens dos meses omitidos.

SKU sem previsão não tem plano: fica fora da soma e é listado. As OPs já abertas não entram (usam a data de conclusão, não a de liberação), e a soma não desconta a capacidade das linhas (seção 4.1).

### 4.3 Estoque projetado no Início (`projected_stock.py`)

Conta SKUs a partir da projeção semanal da seção 4 (`min_projected` e `min_projected_with_plan` de cada semana), sem cálculo novo, em duas leituras:

```text
sem novas ordens = estoque atual + OPs abertas − demanda
com o plano      = estoque atual + OPs abertas + ordens planejadas − demanda
falta            = SKU com estoque projetado < 0 em alguma semana do horizonte
abaixo da segurança = SKU com estoque projetado < segurança em alguma semana (inclui os com falta)
primeira semana de falta = a mais cedo entre os SKUs com falta
```

A falta que sobra **com o plano** é a que as ordens planejadas não alcançam: antes da chegada mais cedo de uma reposição nova (data de planejamento + lead time, o caso de `atraso_inevitavel`) ou antes de uma OP aberta que já cobre a necessidade logo depois (o caso de `antecipar_op`, quando a OP ainda pode ser antecipada). A conta não considera a antecipação: mostra a falta enquanto ela não for decidida. A produção planejada repete os totais da seção 4.2 (`urgent_total` e `horizon_total`). SKU sem previsão fica fora da conta e é listado.

Na base atual (50 SKUs, horizonte em 28/02/2027): 44 SKUs ficam com falta sem novas ordens, a partir da semana de 14/09/2026; com o plano, 22 ainda ficam com falta e 33 abaixo da segurança; produção planejada de 22.900 un. com liberação até 12/10/2026 e 139.300 un. no horizonte.

## 5. Visão comercial parceiro–SKU (`partner_insights.py`)

Usa apenas chaves reais parceiro–SKU–mês. O estoque considerado é o estoque estimado do último sell-out do próprio parceiro, nunca o estoque do CD. Cobertura no parceiro = `estoque estimado / (média mensal de sell-out / 30)`; giro zero ou ausente gera cobertura `null`.

Janela de acúmulo (Etapa 15.5, 6 meses): `sell-through = sell-out ÷ sell-in`, estoque inicial (mês anterior à janela) → final e a conta `estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t)` conferida mês a mês. O sinal de acúmulo do parceiro sobe para o SKU (regra `PARTNER_STOCK_BUILDUP`) sem distribuir o estoque do CD.

Linhas de canal direto (`row_kind = "direct"`, Etapa 16.1) não passam por essa lógica: a venda observada vem de `Vendas_24m`, o estoque estimado é `null` ("sem estoque intermediário") e a ação é `canal_direto`. Nas linhas de parceiro com sell-out suficiente, a projeção para frente da seção 5.1 entra como evidência (`forward_projection`).

Sinais, limiares e precedência das ações estão em [regras comerciais](commercial-rules.md).

### 5.1 Projeção de estoque no parceiro (`partner_stock_projection.py`, sem tela)

- **Identidade:** `estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t)`. Ela fecha, com tolerância de 1 unidade, em 100% dos meses dos 50 pares da base.
- **Sell-out previsto:** média dos últimos 6 meses do par. Foi a janela de menor erro entre último mês, 3 e 6 meses (origens fev a mai/2026, 3 meses à frente): sell-out 32,7% / 28,0% / 26,4% e sell-in 35,4% / 29,7% / 28,2%.
- **Cenários:** com reposição (sell-in igual à média de 6 meses) e sem reposição (sell-in zero). O segundo não depende de prever sell-in.
- **Saídas:** estoque projetado nos 3 meses seguintes ao último mês observado, mês de ruptura (primeiro mês com estoque ≤ 0), cobertura em dias (`estoque ÷ sell-out previsto/30`) e reposição até a cobertura-alvo de 30 dias ao fim do próximo mês.
- **Uso nas recomendações (Etapa 16.6):** dias até acabar sem reposição, quantidade para fechar o próximo mês com 30 dias e o WAPE de 26% entram como evidência nas linhas "Repor" (`forward_projection`), sempre estimados. A rota `/api/partner-stock-projection` continua como detalhe.
- **Limites:** 12 meses por par não permitem captar sazonalidade; só os 50 pares com sell-out (20% dos possíveis) têm projeção.

## 6. Central de validação (`validation_center.py`)

- **Baseline de previsão:** repete o último mês observado antes de cada origem. Não participa da previsão. O modelo só "supera" a baseline com WAPE estritamente menor; empate conta como não superou.
- **Erro com o motor v2:** as mesmas 7 origens rolantes da previsão oficial, com WAPE separado em meses normais e de pico.
- **WAPE mediano:** mediana dos WAPE por SKU.
- **WAPE ponderado:** `Σ erros absolutos / Σ demanda real` somando os SKUs com demanda no holdout.
- **Casos congelados:** comparam a saída obtida pelas mesmas funções de regras, previsão, plano, capacidade e recomendação com a saída esperada registrada em `config/validation_center.json`. Um caso com `pending_until` fica listado como pendente e não conta como aprovado nem reprovado (usado no protocolo da Etapa 15; hoje nenhum está pendente).
- **Comportamento seguro:** além das checagens anteriores, nenhuma falta projetada aparece como "Sem ação necessária" e toda ordem planejada respeita o lote mínimo.
- **Tempo de análise:** soma, média e mediana dos minutos informados nas decisões. Antes de 20 registros, não há comparação com a linha de base. Desde a Etapa 16.7, o frontend mede o tempo entre abrir o detalhe do SKU e registrar a decisão e preenche o campo (editável). Hoje há 0 registros: nenhum ganho de processo é afirmado.
- **Valor em risco endereçado:** soma de `value_at_risk.observed` dos SKUs com decisão registrada. Natureza observada; não é dinheiro recuperado. Sem decisões, é R$ 0 (soma vazia).
- **Modelo × S&OP:** para os meses em comum (out a dez/26), lista os SKUs em que o modelo e o `Forecast_Comercial` divergem mais de 20% (52 divergências em 32 SKUs). É pauta de revisão: o erro do S&OP não é mensurável, porque a base só traz meses futuros.
- **Casos congelados:** 34 de 34 passam (VC-31 a VC-34 liberados na Etapa 16; VC-07, VC-10, VC-20 e VC-29 revistos com registro).

## 7. Comparação entre execuções (`run_comparison.py`)

Para cada SKU presente nas duas execuções, a diferença de score é decomposta usando os pesos gravados em cada uma:

```text
Δ score = Σ peso_alvo(sinais adicionados) − Σ peso_base(sinais removidos) + Σ (peso_alvo − peso_base)(sinais mantidos)
```

Quando a soma das parcelas difere de `Δ score`, o item é marcado como não explicado. A posição pode mudar com score igual quando outros SKUs entram, saem ou mudam de score; o desempate do ranking é por código do SKU.
