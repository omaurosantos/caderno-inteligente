# Regras comerciais — Etapas 4, 15.5 e 16

Estas regras são demonstrativas e independentes das regras operacionais. Desde a Etapa 15.5, um único sinal sobe para o SKU: estoque acumulando no parceiro (`PARTNER_STOCK_BUILDUP`), que entra no score e na evidência da OP a rever. Os demais não alteram score, ranking, previsão ou quantidade. Os limites não foram validados pela empresa.

## Granularidade e origem

- Chave mensal: `Cliente + SKU + Mês` em Sell_In/Sell_Out, normalizada para mês civil.
- Join externo `one_to_one` apenas nas chaves reais. Chaves duplicadas, valores negativos/não finitos e vínculos órfãos bloqueiam a análise comercial.
- O universo de pares é a união dos vínculos de Sell_In, Sell_Out e Carteira_Pedidos. Não existe produto cartesiano de parceiros e produtos.
- Produtos fornece somente SKU/nome; Parceiros_Canais fornece cadastro/região/canal. Não há leitura de quantidades de estoque global, previsão global ou capacidade para distribuir por parceiro.
- Cada par expõe histórico mensal, natureza declarada do sell-out, estoque estimado e pedidos identificados por código/data/status.
- Quantidade de carteira representa pedidos registrados não encerrados, sem inferir saldo após entregas parciais. Status cancelado, concluído, entregue e faturado são excluídos. Na fonte atual, todos os 53 pedidos estão Confirmados.
- Ausência em sell-in/out/estoque permanece `null`; zero observado permanece zero. Carteira zero significa ausência de pedido no recorte de documentos carregado, não ausência de vendas.

## Referência e cálculos

A referência reproduzível é o maior mês de Sell_In/Sell_Out. **Não é a data atual.** Na base atual, é agosto/2026. A atualidade mede diferenças contra esse mês; não afirma que o dado esteja atualizado em outubro/2026.

A janela recente padrão é junho–agosto/2026. Totais de sell-in e sell-out apresentam seus próprios meses observados. A diferença comparável usa somente a interseção de meses com ambas as quantidades não nulas:

`diferença = soma(sell-in nos meses comparáveis) − soma(sell-out nos mesmos meses)`.

Não se subtraem totais de períodos distintos. A proporção usa `abs(diferença) / sell-out comparável`. Se sell-out comparável for zero, a proporção é nula, sem infinito; divergência exige diferença absoluta mínima.

O estoque estimado é o valor do último registro com sell-out, não a soma dos estoques mensais. Sua data é exposta separadamente. Se o estoque desse registro estiver ausente, não se substitui silenciosamente pelo de um mês anterior.

`cobertura estimada em dias = estoque estimado / (média mensal de sell-out observado / 30)`.

O mês de 30 dias é uma aproximação explícita, não uma previsão. Média zero ou ausente deixa cobertura nula. Zero observado entra na média. Nunca se usa estoque do CD, giro global ou forecast global nesse cálculo.

**Janela de acúmulo (Etapa 15.5).** Nos últimos `buildup_months` meses (6):

- `sell_through_window = sell-out ÷ sell-in` da janela;
- `stock_start` = estoque estimado do mês anterior à janela, e `stock_growth = (estoque final − inicial) ÷ inicial`;
- `stock_identity_consistent`: a conta `estoque(t) = estoque(t−1) + sell-in(t) − sell-out(t)` fecha em todos os meses comparáveis, com tolerância de `stock_identity_tolerance` unidade(s). Na base atual, ela fecha nos 50 pares com sell-out.

## Configuração

Arquivo independente: `config/commercial_thresholds.json`. Lido em cada consulta comercial; não precisa invalidar o cache do pipeline operacional.

| Parâmetro | Padrão | Significado |
|---|---:|---|
| recent_months | 3 | Meses da janela de análise |
| minimum_sell_out_months | 3 | Mínimo de meses observados para recomendar |
| maximum_age_months | 1 | Idade tolerada contra a referência da base |
| reposition_coverage_days | 30 | Cobertura máxima para avaliar reposição |
| excess_coverage_days | 90 | Cobertura mínima dos sinais de excesso e acúmulo |
| minimum_excess_stock | 100 | Estoque estimado mínimo para excesso e acúmulo |
| divergence_ratio | 0,5 | Proporção mínima de divergência |
| minimum_divergence_quantity | 50 | Diferença absoluta mínima de divergência |
| buildup_months | 6 | Janela de acúmulo (meses) |
| buildup_max_sell_through | 0,90 | Sell-through máximo para acúmulo |
| buildup_min_stock_growth | 0,30 | Crescimento mínimo do estoque para acúmulo |
| stock_identity_tolerance | 1 | Tolerância da conta de estoque (unidades) |

O limiar `low_monthly_sell_out` (giro ≤ 30 un./mês para haver excesso) saiu na Etapa 15.5: ele impedia qualquer sinal de excesso nos pares reais.

## Sinais e ações

- `INSUFFICIENT_PARTNER_DATA`: menos meses recentes que o mínimo, estoque ausente ou natureza não declarada. Não recomenda reposição.
- `STALE_PARTNER_DATA`: último sell-out antigo contra a referência, ou mês sem observação na janela recente. Solicita atualização; bloqueia reposição.
- `SELLIN_SELLOUT_DIVERGENCE`: amostra comparável mínima e diferença absoluta/proporcional relevante, **só quando a conta de estoque não fecha** (ou não pode ser conferida). Se fecha, a diferença é estoque acumulado, não erro de registro. É investigação, não prova de erro ou previsão de vendas.
- `PARTNER_STOCK_BUILDUP` (Etapa 15.5): dados suficientes e atuais, estoque ≥ mínimo e cobertura ≥ limite (ou sem giro), sell-through ≤ 0,90 e estoque crescendo ≥ 30% na janela. Ação: **não repor; acionar sell-out com o parceiro**.
- `REPOSITION_OPPORTUNITY`: amostra suficiente, sem descontinuidade, giro positivo e cobertura estimada até o limite. Ação: avaliar reposição; não há quantidade autorizada.
- `PARTNER_EXCESS_RISK`: estoque estimado mínimo e cobertura alta (ou giro zero), **sem** acúmulo recente. Ação: monitorar estoque alto no parceiro.

Precedência da ação: atualizar dado antigo/descontínuo → dados insuficientes → investigar divergência → não repor (acúmulo) → avaliar reposição → monitorar estoque alto → monitorar estoque.

Monitoramento também é a ação de acompanhamento quando há dados suficientes e nenhuma exceção. Nesse caso, a justificativa diz explicitamente que monitorar não afirma excesso.

As sete ações possíveis são: Avaliar reposição; Não repor, acionar sell-out com o parceiro; Monitorar estoque alto no parceiro; Monitorar estoque do parceiro; Investigar divergência; Solicitar atualização dos dados; Sem recomendação por dados insuficientes. Todas exigem revisão humana.

Na base atual: KA-02 · CI-0009 é o único acúmulo (vendeu 59% do que recebeu em 6 meses; estoque 595 → 931 un.; 355 dias de giro) e 10 pares têm estoque alto estável.

## Rótulos de ação do desafio

As ações acima continuam sendo a fonte. Um segundo campo, `challenge_action`, traduz cada par para o vocabulário do desafio sem alterá-las: `avaliar_reposicao` → **Repor**; `conter_reposicao` → **Investigar** (acúmulo: não repor e investigar o giro com o parceiro); `monitorar_excesso_parceiro` → **Monitorar**; `monitorar_estoque` → **Monitorar** (ou **Recomendar recompra** quando o par vende mas está sem sell-in acima do próprio ritmo); `investigar_divergencia`, `solicitar_atualizacao` e `dados_insuficientes` → **Investigar**. No nível do parceiro, **Priorizar parceiro** exige 2 ou mais pares **Repor**, com pelo menos um SKU entre os 10 primeiros da fila de atenção.

Desde a Etapa 16.4, "Priorizar parceiro" também sai do nível do SKU: quando um pedido confirmado sem cobertura é disputado por 2 ou mais clientes, a decisão é **quem atender primeiro** com o estoque existente ("Atender KA-05 antes de KA-02"), vinda da alocação ([cálculos](calculations.md#35-alocação-de-produto-escasso-allocationpy)). Os 5 SKUs disputados (CI-0004, CI-0005, CI-0027, CI-0041 e CI-0049) saem com esse rótulo e a alavanca `alocar`. O critério do parceiro (2 ou mais pares Repor e um SKU entre os 10 primeiros) continua valendo para o parceiro. Parceiro sem sell-out suficiente nunca recebe oportunidade inferida. Detalhes e limiares em [Etapa 13](historico.md).

## Canais diretos nas linhas comerciais (Etapa 16.1)

E-commerce, Marketplace e Loja própria vendem ao consumidor: o faturamento de `Vendas_24m` **é** a venda observada. As 22 linhas desses canais (`row_kind = "direct"`, `visibility_source = "faturamento_direto"`) têm `action = "canal_direto"`, dado `sufficient` com natureza "Observado (faturamento direto)", estoque estimado `null` e o motivo "sem estoque intermediário: o estoque que atende o canal é o do CD". Não aplicam cobertura, acúmulo nem divergência, que pressupõem estoque no parceiro, e não são dado insuficiente. O rótulo é o da sugestão do canal (`direct_channels.py`), normalmente Monitorar, ou Investigar quando o canal cai de verdade. Cobertura exibida: 100% nos canais diretos, contra 20% nos parceiros KA.

As 23 linhas KA com carteira e sem sell-out suficiente continuam `dados_insuficientes`: a lacuna real não some. Elas saem como Investigar com o sinal `SELL_OUT_REQUEST`, e a lista completa (ordenada pelo valor do pedido) fica em `GET /api/rules/coverage`.

## Projeção para frente nas linhas "Repor" (Etapa 16.6)

A projeção de estoque do parceiro ([cálculos](calculations.md#51-projeção-de-estoque-no-parceiro-partner_stock_projectionpy)) entra como evidência nas linhas com sell-out suficiente (`forward_projection`): dias até o estoque acabar se a empresa parar de enviar, quantidade para fechar o próximo mês com 30 dias e o erro medido do sell-out (WAPE de 26%). As 11 linhas "Repor" da base ganham três evidências e uma quantidade sugerida, **sempre estimada**. Não é autorização de envio e exige revisão humana.

## Avisos entre fontes (Etapa 16.1)

O sell-in dos parceiros KA é muito maior que o faturado registrado para eles (5 KAs acima da razão 1,25; KA-05 em 6,88 vezes), e o faturamento por cliente é quase proporcional entre clientes (participação entre 0,92 e 1,03 da mediana). Por isso o sistema usa Sell_In e Sell_Out para o parceiro e `Vendas_24m` para o total do SKU, e **não** usa o faturamento por cliente como peso estratégico ou padrão por parceiro. Os avisos `SELLIN_BILLING_DIVERGENCE` e `BILLING_UNIFORM_SPLIT` aparecem em Dados da planilha.

## Decisões por parceiro

O feedback existente possui SKU e efeito genérico do dado de parceiros, mas não código do parceiro. A API retorna atribuição indisponível e itens nulos. Não associa feedback a todos os parceiros que compartilham o SKU. Não foi criada migração ou alteração no contrato de feedback.
