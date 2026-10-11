# Roteiro de demonstração — 5 minutos

Roteiro da versão da Etapa 16, que fecha as lacunas apontadas na análise de aderência ao desafio. Ele responde à pergunta norteadora — como os dados e a IA podem ajudar o PCP a decidir o que produzir, quanto, quando, para quais parceiros e onde há risco — com cinco blocos reais da base:

1. **Início e fila:** quais decisões tomar hoje, em ordem de dinheiro em risco;
2. **CI-0041:** o estoque não cobre dois clientes → quem atender primeiro;
3. **Linha Escolar:** Volta às Aulas contra a capacidade, inclusive depois do calendário da base;
4. **Visibilidade:** até onde vemos o consumidor, e o risco por região;
5. **Por que confiar:** a IA que existe (e por que o modelo simples venceu), as regras que não dispararam e o impacto medido.

Os números são os da planilha de demonstração atual (SHA-256 `03fa0ed4…803f`), com a data de planejamento de 14/09/2026. Se a planilha mudar, confira-os antes de apresentar. Os comparativos completos estão em [docs/etapa-15/antes-depois.md](etapa-15/antes-depois.md) e [docs/etapa-16/antes-depois.md](etapa-16/antes-depois.md); o resumo por problema, em [etapa-16-resumo.md](etapa-16-resumo.md).

## Antes de apresentar (10 minutos antes)

1. Rodar o smoke test contra a publicação. O resultado deve terminar com "verificações aprovadas" e código de saída 0.
   ```powershell
   .\.venv\Scripts\python.exe scripts\smoke_test.py --backend https://API --frontend https://APP --expect-environment production
   ```
2. Abrir as abas na ordem do roteiro e carregar cada uma uma vez, para "aquecer" a API serverless (a primeira leitura da planilha é a mais lenta):
   - `/` (Início) e `/fila`
   - `/skus/CI-0041` (Resumo) e `/skus/CI-0041?tab=evidencias`
   - `/capacidade`
   - `/carteira` e `/parceiros`
   - `/modelo`
   - `/validacao`
   - `/auditoria`
3. Se for registrar uma decisão ao vivo, a publicação precisa estar com `WRITE_ENABLED=true`. Depois da apresentação, limpe os dados de teste (veja [Deploy](deploy-vercel-supabase.md)).
4. **Plano B:** se a API cair, o Guia de uso (`/guia`) funciona sem a API e contém o fluxo resumido.

## 0:00–0:45 — O problema em uma frase

**Tela:** `/` (Início), bloco "Decisões de hoje"; depois `/fila`.

- O Caderno Inteligente vende para parceiros e vê o sell-in, mas só tem sell-out em 20% dos pares parceiro–SKU. O PCP precisa decidir **hoje** o que produzir, quanto e onde há risco.
- **Decisões de hoje:** 26 decisões vencem nos próximos 7 dias (até 21/09), cada uma com a alavanca (alocar, antecipar OP, produzir, renegociar, rever OP) e o prazo. Prazo vencido vira "decidir hoje".
- **A fila não ordena mais por contagem de sinais, e sim por dinheiro em risco:** primeiro a faixa de urgência (17 SKUs têm pedido confirmado sem cobertura), depois o valor em reais. O 1º é o CI-0004 (R$ 59,1 mil observados em pedidos mais R$ 63,4 mil estimados pela previsão). O CI-0047, em descontinuação, era o 2º por contagem de sinais e agora é o 17º.
- No total, 21 pedidos de 17 SKUs ficam sem cobertura na data prometida: **6.626 un. e R$ 401,6 mil**. São valores observados na carteira, a preço vigente.

## 0:45–1:45 — CI-0041: quem atender primeiro

**Tela:** `/skus/CI-0041` → "Quem atender primeiro" (no Resumo); depois `?tab=evidencias`, bloco "Plano de suprimento".

- **O problema:** 1.046 un. prometidas para 13 e 14/09 (PED-041-1 de KA-05, 512 un.; PED-041-2 de KA-02, 534 un.), contra estoque de 132. A OP-7840 só conclui em 08/10 e nem uma ordem liberada hoje chega antes de 05/10 (lead time de 21 dias).
- **O que o sistema faz:** como **nenhuma produção nova chega a tempo**, a pergunta deixa de ser "quanto produzir" e vira "quem atender com o estoque que existe". O rótulo é **Priorizar parceiro**, não Priorizar produção: atender o KA-05 primeiro (132 un. agora e as 380 restantes em 05/10) e o KA-02 depois (534 un. em 08/10, com a OP-7840). A pontuação por pedido está no "?" (urgência, canal, tamanho do pedido).
- **Honestidade sobre o dado:** nenhum dos dois pedidos tem sell-out do parceiro, então a cobertura não pesa; urgência e tamanho do pedido decidem, e o motivo diz isso. **914 un. e R$ 63,9 mil** ficam sem cobertura na data prometida.
- **Em paralelo:** renegociar os prazos e garantir uma ordem nova de 800 un. liberada já (cascata: demanda até 02/11 de 1.824 + segurança de 202 − estoque de 132 − OPs no prazo de 1.200 = 694, arredondado ao lote de 400).
- **Mensagem:** é uma **sugestão** sobre pedidos já confirmados. Nada é reservado, a previsão nunca é distribuída entre clientes e a decisão fica com o PCP.
- **Outros disputados:** CI-0004, CI-0005, CI-0027 e CI-0049, todos com ordem de atendimento.

## 1:45–2:45 — Linha Escolar e a Volta às Aulas

**Tela:** `/capacidade` (botão "Ver capacidade" na fila).

- **O que não cabe:** a previsão sazonal pede **20.800 un.** de Escolar nos picos e a linha tem **12.960 un.** livres até o fim do calendário (03/01). Antes da Etapa 16, o que viesse depois ficava "a confirmar" e a Volta às Aulas ficava sem avaliação.
- **Capacidade estimada, sempre rotulada:** de 04/01 até o fim do horizonte o sistema estima a capacidade (capacidade máxima menos a média dos compromissos das últimas 8 semanas) e mostra as semanas com outra cor e a legenda "estimada: além do calendário da base". É estimativa, **não** capacidade informada pela empresa.
- **Resultado:** o pico continua **não cabendo**: 12.970 un. sem programação no cenário central e 13.600 no conservador (menor capacidade observada). A falta de dezembro é observada; as ordens de 2027 de CI-0014, CI-0016 e CI-0041 ficam como "não cabe nem na capacidade estimada" (falta apenas estimada).
- **Quem é afetado:** CI-0014, CI-0016, CI-0025 e CI-0041, com pedidos de KA-02, KA-05 e Marketplace.
- **O que decidir:** antecipar a produção, terceirizar ou repriorizar clientes. As premissas estão no "?".

## 2:45–3:45 — Até onde vemos o consumidor

**Tela:** `/carteira` (bloco "Quanto da venda ao consumidor é observado"); depois `/parceiros` (bloco "Risco por região").

- **O número que o desafio pede:** **75,1%** das unidades faturadas nos últimos 12 meses têm venda ao consumidor **observada**. Nos canais diretos (E-commerce, Marketplace, Loja própria) o faturamento é a venda ao consumidor: 100%. Nos parceiros KA só vale o sell-out informado: 22,5% no varejista e 19,8% no distribuidor. O resto aparece como "sem visibilidade", nunca como venda zero.
- **Antes**, os canais diretos saíam como "dados insuficientes" com 0% de cobertura. Agora são venda direta observada, sem estoque intermediário. As **23 linhas KA** que têm pedido e nenhum sell-out continuam como lacuna real: a lista "pedir sell-out" (começa em KA-02 · CI-0014, R$ 112,7 mil em pedidos) está em Auditoria.
- **Risco por região:** Centro-Oeste, Sul, Nacional, Nordeste e Sudeste somam os mesmos R$ 401,6 mil sem cobertura (a maior concentração em valor é o Centro-Oeste, R$ 130,4 mil).
- **Aviso entre fontes (Dados da planilha):** o sell-in dos KAs é bem maior que o faturado registrado para eles (KA-05: 6,88 vezes), então o sistema usa Sell_In e Sell_Out para o parceiro e o faturamento só para o total do SKU.

## 3:45–5:00 — Por que confiar, e onde está a IA

**Tela:** `/modelo`; `/validacao`; `/auditoria` › Cobertura de regras.

- **A IA que já existe, contada com honestidade:** a previsão é aprendida dos dados (sazonalidade e nível por SKU) e foi testada contra modelos de machine learning de mercado (statsforecast, scikit-learn, LightGBM e Prophet) no mesmo protocolo, com meses de pico. **O modelo sazonal simples venceu:** erro de 8,0% contra 13,3% do melhor concorrente (AutoARIMA) e 36,4% do Prophet. Por isso ele é o oficial: explicável, auditável e o mais preciso na base. Não há LLM nem texto gerado no produto.
- **Previsão:** erro médio de 8,0% contra 18,9% de repetir o último mês; nos meses de pico, 7,9% contra 26,8%.
- **Casos de teste:** **34 de 34** aprovados. Os casos-alvo da Etapa 16 (canal direto, SKU disputado, desempate por estoque acumulado, pico estimado) foram gravados **antes** do código. Os revistos (VC-07, VC-10, VC-20 e VC-29) estão no histórico de ajustes, com o motivo.
- **Regras que não dispararam (Auditoria › Cobertura de regras):** Ampliar mix, Recomendar recompra e Reativar têm **zero disparos na base, e o sistema diz por quê**. A regra existe e não disparou por causa disto:
  - **Ampliar mix** e **Reativar:** `Vendas_24m` tem faturamento em 24 de 24 meses em 150 de 150 pares canal × SKU, então não há SKU sem venda nem canal parado;
  - **Recomendar recompra:** o Sell_In é contínuo (50 de 50 pares com envio em 12 de 12 meses), então não há lacuna de recompra.
  Cada uma tem um caso congelado (VC-14, VC-15, VC-16) que prova que a regra funciona quando o dado existe. Não se criou dado falso para forçar o disparo.
- **Impacto, sem prometer o que não foi medido:**
  - o tempo de análise agora é medido automaticamente (do abrir o SKU ao registrar a decisão); hoje há **0 registros**, então **nenhum ganho de processo é afirmado** — a comparação com as 22 h por semana só abre com 20 registros;
  - "valor em risco endereçado" soma o valor observado dos SKUs com decisão registrada (hoje R$ 0, sem decisões) e não é dinheiro recuperado;
  - a pauta Modelo × S&OP aponta 52 divergências acima de 20% em 32 SKUs (out a dez/26) para revisão; o erro do S&OP não é mensurável porque a base só traz meses futuros.
- **Fechamento:** toda sugestão exige revisão humana. Nada cria, antecipa, reduz OP nem reserva estoque sozinho, e a decisão fica registrada em Decisões.

## Perguntas prováveis

| Pergunta | Resposta curta |
|---|---|
| Por que tantas "faltas inevitáveis" (21)? | Na base, o estoque costuma durar menos que o lead time e os pedidos vencem antes de qualquer produção nova. Quando há pedido afetado, ele aparece com a data esperada e a ordem de atendimento |
| Por que a fila mudou de ordem? | Ordenar por contagem de sinais dizia quantos problemas o SKU tem, não quanto está em jogo. Agora a ordem é faixa de urgência e valor em risco (o estimado pesa 0,5); a pontuação de sinais continua visível e desempata |
| O que é "Priorizar parceiro" no SKU? | Pedido sem cobertura disputado por 2 ou mais clientes: a decisão é quem atender primeiro com o estoque existente. Não distribui previsão nem estoque entre parceiros que não têm pedido |
| Por que o sell-out quase não pesa na alocação? | Só 2 dos 22 pedidos afetados têm sell-out do parceiro. Sem dado, a cobertura não é inferida. O motivo de cada pedido diz isso |
| A capacidade depois de janeiro é real? | Não: é estimada (capacidade máxima menos a média dos compromissos das últimas 8 semanas), com um cenário conservador ao lado. Serve para saber se há risco, não para prometer capacidade |
| Por que Ampliar mix, Recompra e Reativar nunca aparecem? | O dado não tem as lacunas que disparam essas regras. A Auditoria mostra o número que comprova e o caso de teste que prova a regra. Ausência de SKU no painel de sell-out não vira oportunidade |
| O WAPE de 8,0% é melhor que o MAPE de 31%? | Não dá para comparar: são métricas e previsões diferentes. A base não tem o realizado do forecast comercial |
| O pico de novembro foi testado? | Não diretamente: o modelo exige 15 meses de histórico, então o teste rolante cobre os picos de janeiro e fevereiro. Novembro é conferido por um caso congelado contra o realizado de 2025 |
| O estoque do parceiro é real? | É estimado na planilha. A conta fechar mostra coerência entre as abas, não inventário físico; por isso o rótulo é "Investigar" |
| A IA reduz as 22 horas por semana? | Ainda não foi medido. O tempo de análise é registrado automaticamente, mas há 0 registros; com 20, a Validação libera a comparação |
| O que falta para uso real? | Teste com usuários, dados reais (vínculo pedido–OP, capacidade informada depois de dezembro, sell-out dos KAs), autenticação e limiares aprovados pela empresa |
