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
Priorizar produção = ação produzir* E (posição ≤ 10 na fila de atenção OU decisão de evento no horizonte em até 30 dias)
Priorizar parceiro = parceiro com ≥ 2 pares Repor E ≥ 1 deles em SKU entre os 10 primeiros da fila
Recomendar recompra = ação comercial "monitorar" E sell-out recente positivo E ≥ 3 meses de sell-in
                      E meses sem sell-in ≥ max(2, 2 × intervalo típico entre envios do próprio par)
```

- **Precedência:** dado insuficiente, antigo ou divergente vence tudo e vira "Investigar"; depois, risco/urgência; depois, oportunidade; por último, monitorar.
- **Sem inferência:** parceiro sem sell-out suficiente nunca recebe "Repor", "Recomendar recompra" ou "Priorizar parceiro". "Ampliar mix" e "Reativar" só saem dos canais diretos, onde a ausência de faturamento é observada.
- **Evidência:** cada rótulo traz os valores usados (posição na fila, cobertura, último sell-in, etc.), as limitações e `requires_human_review`.

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
3. o que não couber até a necessidade fica sem programação (`insuficiente`); ordem que começaria depois do calendário fica `a_confirmar`.

Premissas: unidades homogêneas por família; consumo na semana de início; compromissos base não validados com a empresa; sem calendário depois de 28/12/2026; antecipar e reduzir OP não mexem na capacidade.

### 4.2 Produção planejada por mês (`production_plan.py`)

Soma as ordens planejadas do plano de suprimento pelo mês de liberação (`release_date`), no total e por família:

- **agora** (`urgent`): liberação até o fim da janela de decisão; somam exatamente a quantidade sugerida da fila;
- **depois** (`later`): as demais ordens até o fim do horizonte da previsão.

**Mês completo:** um mês de liberação M só é exibido quando `último dia de M + maior lead time entre os SKUs ≤ fim do horizonte`. Depois disso, as ordens que atenderiam necessidades além do horizonte não foram planejadas, e o mês pareceria menor do que é. Na base atual (horizonte em 28/02/2027, maior lead time de 27 dias), janeiro é completo (31/01 + 27 = 27/02) e fevereiro fica de fora. O total do horizonte continua contando as ordens dos meses omitidos.

SKU sem previsão não tem plano: fica fora da soma e é listado. As OPs já abertas não entram (usam a data de conclusão, não a de liberação), e a soma não desconta a capacidade das linhas (seção 4.1).

## 5. Visão comercial parceiro–SKU (`partner_insights.py`)

Usa apenas chaves reais parceiro–SKU–mês. O estoque considerado é o estoque estimado do último sell-out do próprio parceiro, nunca o estoque do CD. Cobertura no parceiro = `estoque estimado / (média mensal de sell-out / 30)`; giro zero ou ausente gera cobertura `null`.

Janela de acúmulo (Etapa 15.5, 6 meses): `sell-through = sell-out ÷ sell-in`, estoque inicial (mês anterior à janela) → final e a conta `estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t)` conferida mês a mês. O sinal de acúmulo do parceiro sobe para o SKU (regra `PARTNER_STOCK_BUILDUP`) sem distribuir o estoque do CD.

Sinais, limiares e precedência das ações estão em [regras comerciais](commercial-rules.md).

### 5.1 Projeção de estoque no parceiro (`partner_stock_projection.py`, sem tela)

- **Identidade:** `estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t)`. Ela fecha, com tolerância de 1 unidade, em 100% dos meses dos 50 pares da base.
- **Sell-out previsto:** média dos últimos 6 meses do par. Foi a janela de menor erro entre último mês, 3 e 6 meses (origens fev a mai/2026, 3 meses à frente): sell-out 32,7% / 28,0% / 26,4% e sell-in 35,4% / 29,7% / 28,2%.
- **Cenários:** com reposição (sell-in igual à média de 6 meses) e sem reposição (sell-in zero). O segundo não depende de prever sell-in.
- **Saídas:** estoque projetado nos 3 meses seguintes ao último mês observado, mês de ruptura (primeiro mês com estoque ≤ 0), cobertura em dias (`estoque ÷ sell-out previsto/30`) e reposição até a cobertura-alvo de 30 dias ao fim do próximo mês.
- **Limites:** 12 meses por par não permitem captar sazonalidade; só os 50 pares com sell-out (20% dos possíveis) têm projeção.

## 6. Central de validação (`validation_center.py`)

- **Baseline de previsão:** repete o último mês observado antes de cada origem. Não participa da previsão. O modelo só "supera" a baseline com WAPE estritamente menor; empate conta como não superou.
- **Erro com o motor v2:** as mesmas 7 origens rolantes da previsão oficial, com WAPE separado em meses normais e de pico.
- **WAPE mediano:** mediana dos WAPE por SKU.
- **WAPE ponderado:** `Σ erros absolutos / Σ demanda real` somando os SKUs com demanda no holdout.
- **Casos congelados:** comparam a saída obtida pelas mesmas funções de regras, previsão, plano, capacidade e recomendação com a saída esperada registrada em `config/validation_center.json`. Um caso com `pending_until` fica listado como pendente e não conta como aprovado nem reprovado (usado no protocolo da Etapa 15; hoje nenhum está pendente).
- **Comportamento seguro:** além das checagens anteriores, nenhuma falta projetada aparece como "Sem ação necessária" e toda ordem planejada respeita o lote mínimo.
- **Tempo de análise:** soma, média e mediana dos minutos informados nas decisões. Antes de 20 registros, não há comparação com a linha de base.

## 7. Comparação entre execuções (`run_comparison.py`)

Para cada SKU presente nas duas execuções, a diferença de score é decomposta usando os pesos gravados em cada uma:

```text
Δ score = Σ peso_alvo(sinais adicionados) − Σ peso_base(sinais removidos) + Σ (peso_alvo − peso_base)(sinais mantidos)
```

Quando a soma das parcelas difere de `Δ score`, o item é marcado como não explicado. A posição pode mudar com score igual quando outros SKUs entram, saem ou mudam de score; o desempate do ranking é por código do SKU.
