# Priorização transparente

A priorização é uma **ordenação de atenção**, não uma solução ótima e não uma decisão automática de produção.

## Ordem oficial da fila (Etapa 16.3)

A fila deixou de ordenar só pela soma de pesos, que mede **quantos** sinais um SKU tem e não **quanto** está em jogo. A ordem agora é lexicográfica, e cada passo se explica numa frase:

1. **Faixa de urgência** (`urgency_tier`), de 1 a 4, ↑;
2. **Valor em risco ponderado** (`value_at_risk.weighted = observed + 0,5 × estimated`), ↓;
3. **Pontuação de sinais** (a soma de pesos abaixo, agora chamada `attention_score`), ↓;
4. **Código do SKU**.

| Faixa | Significado | SKUs na base atual |
|---|---|---:|
| 1 | Pedido confirmado sem cobertura (dado observado, depois da alocação) | 17 |
| 2 | Ação de produção nas próximas 4 semanas, ou falta projetada só na previsão | 12 |
| 3 | Rever OP ou excesso | 5 |
| 4 | Produzir no horizonte ou monitorar | 9 |

Na faixa 3, o desempate usa `value_at_risk.excess` (capital parado) ↓ antes dos sinais, porque o excesso é o valor dessa faixa.

**Valor em risco**, sempre em reais e separado por natureza:

- `observed`: unidades que ficam sem cobertura na data prometida, **depois da alocação** ([cálculos](calculations.md#35-alocação-de-produto-escasso-allocationpy)), × preço vigente. Sem alocação, usa os pedidos afetados do plano (`observed_basis`);
- `estimated`: falta projetada só na demanda prevista até o fim da cobertura × preço. Peso 0,5 (`estimated_weight`, em `config/prioritization_impact.json`);
- `excess`: valor do estoque excedente ou da redução de OP sugerida;
- produto em descontinuação só conta o `observed`; preço ausente deixa o valor `null`, nunca zero.

**Curva ABC medida:** `abc_measured` (80% e 95% do faturamento dos últimos 12 meses) aparece ao lado da `abc_registry` do cadastro. Só 13 de 50 SKUs coincidem; a divergência vira o aviso `ABC_REGISTRY_DIVERGENCE` (37 SKUs) e **a ABC não entra na ordenação**.

**Motivo na fila:** começa pela faixa e pelo valor, por exemplo "Pedido confirmado sem cobertura · R$ 59,1 mil em risco (KA-02, KA-05)".

**Na base atual:** CI-0004 lidera (ponderado R$ 99,2 mil: R$ 59,1 mil observados e R$ 80,3 mil estimados), seguido de CI-0041 (R$ 69,4 mil). CI-0041 tem o maior valor **observado** (R$ 63,9 mil), mas o estimado menor, por isso fica em 2º. CI-0047, em descontinuação, era o 2º por contagem de sinais e agora é o 17º, o último da faixa 1.

## Pontuação de sinais

A pontuação de cada SKU é a soma dos pesos das regras ativas. Os pesos ficam em [config/prioritization_weights.json](../config/prioritization_weights.json), fora do código.

| Regra | Peso |
|---|---:|
| Estoque abaixo da segurança | 10 |
| Pedido sem produção | 9 |
| Falta antes da reposição (`PROJECTED_SHORTFALL`) | 9 |
| Cobertura abaixo do lead time | 8 |
| Produção posterior à promessa | 8 |
| Não cabe na capacidade (`CAPACITY_SHORTFALL`) | 7 |
| OP de produto saindo de linha (`OP_FOR_DISCONTINUED`) | 6 |
| Estoque acumulando no parceiro (`PARTNER_STOCK_BUILDUP`) | 6 |
| Excesso depois da OP (`PROJECTED_EXCESS`) | 5 |
| Excesso de cobertura | 3 |
| Baixa visibilidade de sell-out | 2 |

Os pesos das regras do plano foram gravados na Etapa 15.0, antes do código que as emite.

## Confiança

- **Baixa:** SKU sem sell-out observado; a lacuna é explicitada.
- **Média:** há sell-out observado, mas a cobertura da rede de parceiros permanece parcial.

Nenhum caso recebe confiança alta enquanto a cobertura de sell-out B2B permanecer parcial.

Cada linha do ranking expõe score, motivos, evidências, origem dos dados e uma ressalva de uso.

## Desempate e posição

Dentro da mesma faixa e do mesmo valor em risco, o ranking ordena por score decrescente e, em caso de empate, pelo código do SKU. Assim, um SKU pode mudar de posição sem mudar de score, quando outros SKUs entram, saem, mudam de faixa ou de valor.

## Prioridade não é ordem de produção

A prioridade indica **o que analisar primeiro**. A ação e a quantidade vêm do plano datado, calculado separadamente. Na base atual, o segundo da fila (CI-0041) tem 1.046 un. prometidas para 13–14/09 contra estoque de 132 e OP só em 08/10: a ação é **falta inevitável** (renegociar os pedidos PED-041-1 e PED-041-2 e garantir a OP), com ordem nova de 800 un. Como dois clientes disputam o mesmo estoque, o rótulo do desafio é **Priorizar parceiro** ("atender KA-05 antes de KA-02"), não Priorizar produção: nenhuma produção nova chega a tempo. Até a Etapa 15.3, esse mesmo SKU aparecia como "sem ação necessária"; nenhum SKU da fila fica mais sem ação quando há falta projetada.

## Explicar uma mudança de prioridade

Em `/execucoes?base=&alvo=`, a comparação entre duas execuções decompõe a diferença de score em sinais adicionados, sinais removidos e pesos alterados (fórmula em [cálculos](calculations.md#7-comparação-entre-execuções-run_comparisonpy)). Desde a Etapa 16.3, ela também diz se a posição mudou por faixa, por valor em risco, por sinais ou porque outros SKUs se moveram (`position_driver`).
