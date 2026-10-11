# Etapa 16 — Decisões antes × depois

Gerado por `scripts/snapshot_decisions.py --comparar` a partir de `antes.json` (início da Etapa 16.0) e `depois.json` (fim da 16.7), na mesma planilha.

## Ações por SKU

| Ação | Antes | Depois |
|---|---|---|
| `antecipar_op` | 1 | 1 |
| `atraso_inevitavel` | 21 | 21 |
| `produzir` | 21 | 21 |
| `produzir_validar_capacidade` | 2 | 2 |
| `rever_op` | 5 | 5 |

## Top 10 da fila

| # | Antes | Ação antes | Depois | Ação depois | Sugerido agora |
|---|---|---|---|---|---|
| 1 | CI-0041 | `atraso_inevitavel` | CI-0004 | `atraso_inevitavel` | 1.600 |
| 2 | CI-0047 | `atraso_inevitavel` | CI-0041 | `atraso_inevitavel` | 800 |
| 3 | CI-0017 | `atraso_inevitavel` | CI-0011 | `atraso_inevitavel` | 600 |
| 4 | CI-0025 | `atraso_inevitavel` | CI-0017 | `atraso_inevitavel` | 200 |
| 5 | CI-0037 | `atraso_inevitavel` | CI-0025 | `atraso_inevitavel` | 0 |
| 6 | CI-0049 | `atraso_inevitavel` | CI-0005 | `atraso_inevitavel` | 1.000 |
| 7 | CI-0004 | `atraso_inevitavel` | CI-0002 | `atraso_inevitavel` | 0 |
| 8 | CI-0002 | `atraso_inevitavel` | CI-0027 | `atraso_inevitavel` | 600 |
| 9 | CI-0015 | `atraso_inevitavel` | CI-0049 | `atraso_inevitavel` | 600 |
| 10 | CI-0018 | `atraso_inevitavel` | CI-0020 | `atraso_inevitavel` | 900 |

## Previsão, cobertura e casos-alvo

| Indicador | Antes | Depois |
|---|---|---|
| Previsão somada nov/26 (un.) | 36.203 | 36.203 |
| Previsão somada jan/27 (un.) | 33.896 | 33.896 |
| Faturamento estimado 3 meses (R$) | 5.612.822 | 5.612.822 |
| SKUs na fila | 43 | 43 |
| Quantidade sugerida agora (un.) | 22.900 | 22.900 |
| CI-0041: posição · ação · cobertura (dias) | 1 · `atraso_inevitavel` · 5 | 2 · `atraso_inevitavel` · 5 |
| CI-0050: posição · ação · cobertura (dias) | 11 · `rever_op` · 9 | 30 · `rever_op` · 9 |
| CI-0047: posição · ação · cobertura (dias) | 2 · `atraso_inevitavel` · 9 | 17 · `atraso_inevitavel` · 9 |
| CI-0048: posição · ação · cobertura (dias) | 18 · `rever_op` · 8 | 33 · `rever_op` · 8 |
| CI-0009: posição · ação · cobertura (dias) | 29 · `rever_op` · 110 | 32 · `rever_op` · 110 |
| CI-0014: posição · ação · cobertura (dias) | 17 · `atraso_inevitavel` · 30 | 19 · `atraso_inevitavel` · 30 |
| CI-0004: posição · ação · cobertura (dias) | 7 · `atraso_inevitavel` · 15 | 1 · `atraso_inevitavel` · 15 |
| KA-02 · CI-0009: ação comercial | `conter_reposicao` | `conter_reposicao` |
| KA-03 · CI-0001: ação comercial | `monitorar_excesso_parceiro` | `monitorar_excesso_parceiro` |
| Casos congelados (aprovados / total / pendentes) | 30 / 30 / 0 | 34 / 34 / 0 |

## Capacidade (depois)

| Família | Livre no calendário | Sem programação | Situação | Pico: necessidade · situação |
|---|---|---|---|---|
| Clássico | 39.240 | 540 | `insuficiente` | 18.000 · `ok_estimado` |
| Escolar | 12.960 | 12.970 | `insuficiente` | 20.800 · `insuficiente` |
| Planner | 22.560 | 1.520 | `insuficiente` | 10.000 · `ok_estimado` |
| Acessórios | 122.000 | 0 | `ok_estimado` | 18.600 · `ok_estimado` |
| Executivo | 23.940 | 0 | `ok_estimado` | 3.000 · `ok_estimado` |
| Refis | 136.500 | 0 | `ok_estimado` | 14.500 · `ok_estimado` |

## Etapa 16 — medidas das metas

`não existia` = campo ausente no snapshot (nunca tratado como zero).

| Medida | Antes | Depois |
|---|---|---|
| Linhas de canal direto como dados insuficientes | 22 | 0 |
| SKUs da fila | 43 | 43 |
| SKUs com Priorizar produção | 24 | 10 |
| Priorizar produção sobre a fila | 55,8% | 23,3% |
| Priorizar produção sem alavanca de produção | não existia | 0 |
| Descontinuados com Priorizar produção | 1 | 0 |
| SKUs disputados | não existia | 5 |
| SKUs disputados com ordem de atendimento | não existia | 5 |
| Participação da venda ao consumidor observada | não existia | 75,1% |
| Regiões no resumo de risco | não existia | 5 |
| SKUs com capacidade a confirmar | não existia | 0 |
| Regras com zero disparos | não existia | 3 |
| Decisões de hoje (janela de planejamento) | não existia | 26 |
| Regras com zero disparos explicadas | não existia | 3 de 3 |
| Casos congelados aprovados / total | 30 / 30 | 34 / 34 |

## Ordem de atendimento dos SKUs disputados (depois)

| SKU | Ordem | Pedidos com motivo | Último |
|---|---|---|---|
| CI-0004 | KA-02 > KA-05 | 2 | KA-05 |
| CI-0005 | Marketplace > KA-04 | 2 | KA-04 |
| CI-0027 | KA-01 > KA-05 | 2 | KA-05 |
| CI-0041 | KA-05 > KA-02 | 2 | KA-02 |
| CI-0049 | KA-02 > KA-01 | 2 | KA-01 |

## Rótulos na fila (depois)

| Rótulo | SKUs |
|---|---|
| `investigar` | 5 |
| `monitorar` | 14 |
| `priorizar_parceiro` | 5 |
| `priorizar_producao` | 10 |
| `produzir` | 9 |

## Cobertura por parceiro (depois)

| Parceiro | Fonte de visibilidade | Cobertura |
|---|---|---|
| KA-01 | `sell_out_parceiro` | 20,0% |
| KA-02 | `sell_out_parceiro` | 20,0% |
| KA-03 | `sell_out_parceiro` | 20,0% |
| KA-04 | `sell_out_parceiro` | 20,0% |
| KA-05 | `sell_out_parceiro` | 20,0% |
| E-commerce | `faturamento_direto` | 100,0% |
| Marketplace | `faturamento_direto` | 100,0% |
| Loja própria | `faturamento_direto` | 100,0% |
