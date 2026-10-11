# Etapa 16 — Resumo

Fecha as lacunas do Desafio 3 apontadas na análise de aderência (P1 a P8). Especificação: [discovery-etapa-16.md](discovery-etapa-16.md). Decisões e exceção à regra de não distribuir dados globais: [decisions.md](decisions.md). Comparação completa antes × depois: [etapa-16/antes-depois.md](etapa-16/antes-depois.md). Números da base atual (SHA-256 `03fa0ed4…803f`, planejamento em 14/09/2026), medidos pela API.

## O que mudou por problema

| Problema | O que mudou | Antes → depois |
|---|---|---|
| **P1** Canais diretos tratados como "sem visibilidade" | Linhas de canal direto viram venda observada (`canal_direto`), sem estoque intermediário; `/api/b2b2c/visibility` lista os canais diretos e traz a jornada até o consumidor | Linhas de canal direto como dado insuficiente: 22 → 0. Cobertura dos canais diretos: 0% → 100% (KAs seguem em 20%). Venda ao consumidor observada: não calculada → 75,1% (328.111 un.; direto 100%, varejista 22,5%, distribuidor 19,8%) |
| **P2** Ranking sem impacto | Ordem por faixa de urgência, valor em risco ponderado e só então pontuação de sinais; curva ABC medida ao lado da do cadastro | 1º da fila: CI-0041 → CI-0004 (R$ 59,1 mil observados, R$ 99,2 mil ponderados). CI-0047 (descontinuação): 2º → 17º. SKUs por faixa 1/2/3/4: 17/12/5/9. `ABC_REGISTRY_DIVERGENCE`: 37 SKUs |
| **P3** Excesso de "Priorizar produção" | Tabela de decisão por alavanca (`lever`), prazo (`decide_by`) e bloco "Decisões de hoje" | Priorizar produção: 26 de 50 SKUs → 12 (24%), todos com alavanca real. Maior rótulo: 52% → 30% (teto exigido: 40%). Descontinuados como Priorizar produção: 1 → 0. Faltas só na previsão (5) com "estimada" no motivo: 0 → 5. Decisões de hoje: 26 |
| **P4** Capacidade acaba antes do horizonte | Semanas estimadas até o fim do horizonte, cenário central e conservador | SKUs com capacidade "a confirmar": 37 → 0. Linha Escolar: pico segue `insuficiente` (12.970 un. sem programação no central, 13.600 no conservador) |
| **P5** Falta alocar produto escasso | Módulo `allocation.py`, `/api/allocation` e `/api/allocation/regions`, bloco "Quem atender primeiro" | SKUs disputados com ordem de atendimento e Priorizar parceiro: 0 de 5 → 5 de 5. Risco por região: inexistente → 5 regiões somando 6.626 un. e R$ 401.632,40 (17 SKUs, 21 pedidos) |
| **P6** Ampliar mix, Recompra e Reativar nunca disparam | `/api/rules/coverage` explica cada regra com zero disparos e o caso de referência; lista de pares KA para pedir sell-out | Regras com zero explicadas: 0 → 3 de 3 (VC-14, VC-15, VC-16). Pares KA × SKU com pedido e sem sell-out listados: 0 → 23 |
| **P7** Inconsistências menores | (a) texto do teto sazonal vem de `ratio_bounds`; (b) projeção do parceiro entra nas linhas "Repor"; (c) avisos entre fontes | (b) 11 linhas "Repor" com 3 evidências (dias até acabar, quantidade para 30 dias, WAPE de 26%). (c) `SELLIN_BILLING_DIVERGENCE` em 5 KAs (KA-05: 6,88 vezes) e `BILLING_UNIFORM_SPLIT` (0,92 a 1,03 da mediana) |
| **P8** IA e impacto mensurável | Narrativa honesta da IA no roteiro; tempo de análise automático; valor em risco endereçado; pauta Modelo × S&OP | Casos congelados: 30 → 34 de 34 passam. Pauta S&OP: 52 divergências acima de 20% em 32 SKUs. Registros com tempo de análise: 0 → 0 (a medição passa a ser automática; nenhum ganho de processo é afirmado) |

## Limitações

- **A alocação é uma sugestão** sobre pedidos confirmados: não reserva estoque nem altera pedidos, nunca distribui previsão e exige revisão humana. Só 2 dos 22 pedidos afetados têm sell-out do parceiro, então urgência, canal e tamanho do pedido decidem quase tudo.
- **A capacidade além do calendário é estimada**, não informada pela empresa. `insuficiente_estimado` não gera `CAPACITY_SHORTFALL` nem muda o score.
- **O valor em risco usa o preço mais recente da base**; o estimado (falta só na previsão) pesa 0,5. O valor endereçado é soma observada, não dinheiro recuperado.
- **Ampliar mix, Recomendar recompra e Reativar continuam sem disparar** na base, porque o dado não tem as lacunas que as acionam. Não se criou dado sintético para forçá-las.
- **As 23 linhas KA sem sell-out continuam como lacuna real**, e 80% dos pares parceiro–SKU não têm sell-out. A jornada de 75,1% depende do faturado: o sell-out dos KAs é limitado ao faturado do par, e sell-in e faturamento não fecham.
- **Nenhum ganho de processo é afirmado:** há 0 registros de tempo de análise; a comparação com as 22 h por semana só abre com 20.
- **Resumo por LLM (D7) ficou fora do escopo.**
- A ordem da fila mudou de critério: execuções anteriores continuam comparáveis (`ranking_basis`), mas a posição não é comparável diretamente com a das etapas anteriores.

## Commits sugeridos (por subetapa)

O usuário commita ao fim de cada onda. Sugestão, na ordem:

| Onda | Mensagem |
|---|---|
| 0 | `chore(etapa-16.0): linha de base, casos-alvo e texto do teto sazonal` |
| 1 | `fix(etapa-16.1): canais diretos com visibilidade observada e mapa da jornada` |
| 1 | `feat(etapa-16.5): capacidade estimada além do calendário` |
| 1 | `feat(etapa-16.2/16.3/16.4): núcleos de alocação, impacto e alavancas (sem ligação)` |
| 2 | `feat(etapa-16.2): alocação de estoque escasso por pedido, parceiro e região` |
| 2 | `feat(etapa-16.3): fila por urgência e valor em risco, ABC medida` |
| 2 | `fix(etapa-16.4): rótulos por alavanca de decisão e decisões de hoje` |
| 2 | `feat(etapa-16.6): cobertura de regras, pedido de sell-out e projeção no parceiro` |
| 3 | `feat(etapa-16): telas de alocação, fila por valor, capacidade estimada e cobertura` |
| 4 | `feat(etapa-16.7): impacto mensurável, comparação final e roteiro` |

## Rodada de revisão (verificação independente e code review)

O verificador aprovou P1–P6 e as metas mensuráveis; o code review apontou 12 achados, sem nenhum crítico. Corrigido:

- configuração inválida de alocação, impacto ou capacidade estimada não derruba mais a API: a camada cai para o comportamento anterior (ordem por sinais, capacidade só do calendário) com aviso, e o cache continua valendo;
- valor em risco endereçado sem decisões ou com a persistência fora do ar sai `null` com motivo (antes, R$ 0);
- faltas só na previsão passam a ter valor estimado pela maior ruptura antes da chegada da OP (CI-0015: R$ 30,0 mil; antes, R$ 0). Com isso, CI-0004 lidera com R$ 99,2 mil ponderados e CI-0041 vem em 2º com R$ 69,4 mil;
- canais diretos calculados uma vez por versão da base: `/api/partners` caiu de cerca de 5,3 s para 1,2 s e `/api/rules/coverage` de 7,9 s para 1,7 s;
- a assinatura do cache inclui os limiares comerciais, de canais diretos e da projeção do parceiro;
- a nota da alocação não conta canal direto como sell-out do parceiro; "Atender A antes de B" usa clientes distintos; faixa 3 sem OP a reduzir mostra excesso ausente, não R$ 0; "Decisões de hoje" traz `requires_human_review`; o texto da capacidade estimada lê `lookback_weeks` em vez de fixar 8 semanas; o tempo de análise é zerado ao trocar de SKU.

Aceito sem correção: o pico da Escolar sai `insuficiente` (falta observada em dezembro, mais grave que a estimada) e SKUs com ordem planejada fora da janela de 4 semanas saem como Monitorar.
