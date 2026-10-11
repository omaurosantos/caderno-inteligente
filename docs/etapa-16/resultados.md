# Etapa 16 — Resultados medidos (antes → meta → obtido)

Fonte dos números: `antes.json` (linha de base, antes de qualquer mudança) e `depois.json` (fim da Etapa 16), gerados por
`scripts/snapshot_decisions.py` na mesma planilha (hash idêntico). A comparação completa está em `antes-depois.md`.
Medidas que não existiam antes da etapa aparecem como "não existia", nunca como zero.

## Metas da seção 6 do discovery

| Métrica | Antes | Meta | Obtido | Meta |
|---|---|---|---|---|
| Linhas comerciais de canal direto como "dados insuficientes" | 22 | 0 | 0 (de 22 linhas dos 3 canais diretos) | Atendida |
| Cobertura exibida dos canais diretos | 0% | 100% (fonte: venda direta) | 100% nos 3 canais (E-commerce, Marketplace, Loja própria), fonte `faturamento_direto` | Atendida |
| Participação das unidades com venda ao consumidor observada | não calculada | exibida no mapa da jornada | 75,1% (246.389 de 328.111 un.): direto 100%, varejista 22,5%, distribuidor 19,8% | Atendida |
| SKUs com "Priorizar produção" | 24 de 43 (55,8%) | ≤ 40% da fila, todos com alavanca de produção | 10 de 43 (23,3%); 0 sem alavanca de produção | Atendida |
| Descontinuados como Priorizar produção | 1 (CI-0047, 2º lugar) | 0 | 0 (CI-0047 caiu para o 17º lugar, último da faixa 1) | Atendida |
| SKUs disputados com ordem de atendimento | 0 de 5 | 5 de 5 | 5 de 5 (CI-0004, 0005, 0027, 0041, 0049), todos com motivo por pedido | Atendida |
| Resumo de risco por região | inexistente | presente | 5 regiões em `/api/allocation/regions`; as regiões somam o total (6.626 un., R$ 401.632,40) | Atendida |
| SKUs com capacidade "a confirmar" | 30 (discovery) | 0 (com o método ligado) | 0 de 50 SKUs; 36 `ok_estimado`, 1 `insuficiente_estimado` | Atendida |
| Regras com zero disparos explicadas | 0 | todas | 3 de 3 com motivo (`zero_reason`) entre 21 regras | Atendida |
| Decisões com tempo de análise | 0 | automático em toda decisão nova | Mecanismo ligado no detalhe do SKU (`analysisTimer.ts`); ainda 0 registros com tempo na base, porque nenhuma decisão nova foi gravada. `analysis_time.comparison_allowed` segue falso (mínimo de 20) | Atendida no mecanismo; ganho de tempo não medido |
| Casos congelados | 30 aprovados | 34, todos aprovados ou revistos com registro | 34 de 34 aprovados, 0 pendentes (VC-31 a VC-34 incluídos) | Atendida |

## Observações sobre os números do discovery

- **"24 de 43" mede a fila, não os 50 SKUs.** No `antes.json`, 26 dos 50 SKUs tinham o rótulo; 24 são da fila de 43. Os 24 do discovery estão certos; a meta usa a fila.
- **Capacidade "a confirmar".** O discovery dizia 30; o handoff da Onda 1 mediu 37. O `antes.json` guarda só o nível de família, então a linha de base de SKU não é recomputável pelo snapshot. O resultado (0) não depende dessa divergência.
- **SKUs com falta.** São 17 (o discovery dizia 16 entre as faltas inevitáveis; o 17º é CI-0033, `antecipar_op`).
- **Cobertura dos canais diretos.** A cobertura por parceiro KA continua em 20,0% (sell-out por parceiro); só os canais diretos chegam a 100%.
- **Pico da família Escolar** continua `insuficiente` (falta observada em dez/26), por ser mais grave que a estimada; VC-29 segue aprovado.
- **Linha de BILLING_UNIFORM_SPLIT.** Faixa medida de 0,92 a 1,03 (o discovery dizia 0,94).
- **Ranking.** CI-0004 lidera a fila (R$ 90,8 mil ponderado); CI-0041 caiu para 2º (observado maior, estimado menor). Não é CI-0041 no topo, como o discovery supunha.

## Rótulos na fila (depois)

`monitorar` 14, `priorizar_producao` 10, `produzir` 9, `priorizar_parceiro` 5, `investigar` 5 (total 43).
Nenhum rótulo passa de 40% da fila.

## O que não mudou (por desenho)

Previsão somada, faturamento estimado de 3 meses, SKUs na fila (43) e quantidade sugerida agora (22.900 un.) são idênticos ao antes:
a etapa muda a priorização, os rótulos e a visibilidade, não o motor de previsão nem a ação operacional por SKU.
