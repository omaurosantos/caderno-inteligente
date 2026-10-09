# Decisões técnicas

## 2026-09-28 — Etapa 1

- O arquivo XLSM original é uma fonte somente leitura e não será copiado, salvo ou sobrescrito pelo protótipo.
- As abas têm cabeçalho na linha 3; a ingestão usa `skiprows=2` de forma explícita.
- Ausência de sell-out representa falta de observação, não quantidade vendida igual a zero.
- A validação expõe erros e avisos; não corrige silenciosamente dados ou regras de negócio.
- A normalização, os indicadores e as regras determinísticas permanecem fora desta etapa.

## 2026-09-28 — Etapa 2

- A normalização opera sobre cópias internas: SKU é padronizado em maiúsculas e tipos numéricos e de data são convertidos após a validação.
- A visão de indicadores é uma tabela por SKU; chaves operacionais são agregadas por SKU e capacidade por família.
- Cobertura calculada permanece ao lado da cobertura informada, permitindo auditar divergências; nenhuma delas é substituída silenciosamente.
- `projected_stock_quantity` é um indicador de conciliação de volumes, não uma decisão de produção.
- Capacidade semanal não é alocada a pedidos/OPs nesta etapa, pois a fonte não fornece essa relação.

## 2026-09-28 — Etapa 3

- As regras são sinais determinísticos e auditáveis; não geram ordem de produção nem recomendação autônoma.
- Excesso de cobertura usa limite configurável de 90 dias e conflito de capacidade usa ocupação média familiar acima de 90%.
- A regra de data compara a primeira data prometida e a primeira conclusão prevista do SKU, pois não há vínculo pedido–OP na fonte.
- A ausência de sell-out gera somente um sinal de baixa visibilidade e não altera o volume de vendas.

## 2026-09-28 — Etapa 4

- A priorização é uma soma de pesos por regra, mantidos em configuração e exibidos como evidência.
- A saída é uma ordenação de atenção, não uma solução ótima, recomendação autônoma ou liberação de produção.
- A confiança é baixa sem sell-out observado e média quando há observação, pois a cobertura B2B segue parcial.

## 2026-09-30 — Consolidação da interface

- React/Vite passa a ser a interface principal; o app Streamlit da V1 foi usado só na transição e removido em 2026-10-07.
- O frontend deve comunicar carregamento, erro, vazio e sucesso explicitamente.
- A navegação móvel usa drawer e não mantém largura fixa de sidebar.
- O detalhe do SKU apresenta evidências, origem e limitações sem transformar o ranking em recomendação autônoma.
- O pipeline da API é cacheado e invalidado por mudanças na fonte ou nas configurações, evitando leituras concorrentes repetidas do XLSM.

## 2026-09-30 — Contexto operacional do ranking

- A prioridade permanece em uma linha por SKU e recebe contexto operacional sem criar alocação por parceiro, canal ou semana.
- A data crítica é a menor data disponível entre a primeira promessa e a primeira conclusão prevista; sua origem é exposta separadamente.
- A lacuna operacional usa `máximo(0, carteira - estoque atual - produção aberta)` e não representa uma ordem recomendada.
- Ausência de sell-in ou sell-out é retornada como `null` e descrita em `missing_data`, nunca convertida silenciosamente em venda zero.

## 2026-09-30 — Impacto do dado do parceiro

- O feedback registra separadamente a ação humana e o efeito declarado dos dados do parceiro.
- Feedbacks antigos são preservados e marcados como `nao_utilizado`; nenhuma influência é inferida retroativamente.
- O indicador de decisões influenciadas soma apenas `aumentou_confianca` e `alterou_decisao`.
- O tempo de análise é opcional, inteiro e não negativo.

## 2026-10-01 — Publicação com Vercel e Supabase

- Frontend e backend são publicados como dois projetos Vercel do mesmo repositório, preservando a separação atual.
- SQLite continua como fallback local; `DATABASE_URL` seleciona PostgreSQL em ambientes publicados.
- Casos e histórico usam a mesma transação para impedir gravações parciais.
- O backend usa o Transaction Pooler do Supabase com prepared statements desabilitados, adequado a Functions de curta duração.
- O frontend conhece apenas `VITE_API_URL`; senhas e connection strings nunca usam o prefixo público `VITE_`.
- O XLSM permanece empacotado e somente leitura. Migração para Storage e autenticação ficam fora do protótipo.

## 2026-10-04 — Previsão de demanda e recomendação operacional

- A previsão mensal compara média móvel de três meses e sazonal ingênuo de doze meses para cada SKU.
- Os três últimos meses são preservados como holdout e o menor WAPE escolhe o modelo; histórico insuficiente não gera previsão zero.
- A tendência compara os três meses recentes com os três anteriores e usa uma faixa de 10% para evitar classificar pequenas oscilações.
- A recomendação usa o maior valor entre previsão do próximo mês e carteira para reduzir dupla contagem.
- Estoque de segurança, estoque atual, produção aberta e lote mínimo permanecem visíveis no cálculo.
- Capacidade por família é apenas um alerta de revisão, pois a fonte não comprova viabilidade por SKU e semana.
- O resultado é aditivo ao detalhe do SKU e não altera regras, score ou ranking oficial.
- Toda recomendação exige revisão humana e não cria ordem de produção.
- Feedbacks são registrados para validação, mas não retreinam o modelo automaticamente no V1.

## 2026-10-04 — Visão consolidada de previsão e recomendação

- A visão consolidada possui uma rota aditiva própria e somente leitura, sem ampliar o contrato do carregamento inicial do dashboard.
- O endpoint usa o pipeline cacheado e a função existente de recomendação; fórmulas não são duplicadas no frontend ou na rota.
- Todos os SKUs são exibidos, inclusive os não presentes no ranking, sem fabricar posição ou score.
- Busca, filtros e ordenação acontecem no navegador devido ao pequeno volume atual; paginação permanece fora do MVP.
- O detalhe continua centralizado no drawer e é carregado apenas quando solicitado.
- Quantidade sugerida permanece separada da prioridade oficial, capacidade não é tratada como garantia e revisão humana continua obrigatória.

## 2026-10-05 — Rotas e modularização da V2

- Cada página existente recebe uma rota real com `react-router-dom`, sem alterar contratos ou cálculos do backend.
- O detalhe do SKU passa do drawer para `/skus/:sku`, preservando as mesmas evidências, previsão, recomendação e revisão humana.
- Filtros relevantes usam query parameters para permitir compartilhamento e navegação pelo histórico.
- O Guia de uso permanece estático e não depende do carregamento da API.
- As páginas são separadas em módulos e carregadas sob demanda; o carregamento específico por rota das demais áreas fica para a Etapa 2.
- O frontend usa rewrite de SPA na Vercel para que deep links sejam atualizáveis e compartilháveis.
- Detalhe de parceiro e Validação continuam reservados às etapas que possuem dados e critérios próprios; nenhuma granularidade é criada apenas para preencher uma rota.

## 2026-10-05 — Central de validação da Semana 4

- A validação é uma rota aditiva e somente leitura; não altera pesos, limiares, modelos, ranking, regras ou a planilha.
- Linha de base da empresa (22 h/semana, MAPE 31%, 89% no prazo com meta de 96%, 78% de aderência) e meta de 8 h/semana aparecem separadas do que o protótipo recalcula.
- Pedidos no prazo e aderência ao plano ficam como não recalculáveis: a base não traz entregas nem produção realizada. O forecast comercial da base cobre somente meses futuros, por isso o MAPE informado também não é recalculado; o WAPE do protótipo é exibido como métrica diferente, não comparável diretamente.
- A baseline explícita da previsão é o último mês observado repetido no holdout. Ela não participa da seleção do modelo; empate conta como não superou.
- Os oito casos representativos são congelados em `config/validation_center.json` com o hash da planilha. Seis usam SKUs ou pares reais; dois são sintéticos porque a base não contém exemplo, e isso é exibido como lacuna.
- O tempo de análise registrado não é comparado com a linha de base antes de 20 registros com minutos.
- Exportação em CSV e impressão são feitas no navegador, sem dependência nova.

## 2026-10-05 — Comparação entre execuções

- Os snapshots passam a gravar um payload versionado com previsão e recomendação por SKU e cobertura por parceiro cadastrado, exatamente como calculados. Nenhum valor global é distribuído entre parceiros.
- A comparação só lê o que cada snapshot preservou. Execuções antigas são comparáveis apenas no ranking; as demais seções são recusadas com explicação, nunca recalculadas retroativamente.
- A diferença de score é decomposta em sinais adicionados, removidos e pesos alterados, usando os pesos gravados em cada execução. Quando a soma não fecha, o item é marcado como não explicado em vez de ocultado.
- A coluna `runs.comparison` é opcional. No PostgreSQL, o adaptador detecta a migração 002 e mantém o registro funcionando antes dela, sem o payload ampliado.
- A rota de comparação é `/api/run-comparisons`, porque `/api/runs/compare` seria capturada pela rota existente `/api/runs/{run_id}`.

## 2026-10-05 — Testes do frontend, acessibilidade e robustez

- Vitest 3.2 foi escolhido por ser compatível com o Vite 6.0.11 já fixado; o Vitest 5 exigiria atualizar o Vite, o que ficou fora do escopo. Testing Library, jsdom e axe-core são dependências apenas de desenvolvimento e não entram no bundle.
- `npm run check` executa typecheck, testes Vitest, testes `node --test` existentes, build e verificação de segredos no `dist/`. O build da Vercel continua sendo `npm run build`, sem executar testes.
- Os testes usam somente fixtures sintéticas tipadas pelos contratos do frontend. Um arquivo de campos compartilhado é validado nas duas pontas: fixtures no Vitest e API real no pytest.
- A acessibilidade é verificada com axe-core em todas as rotas, em viewport móvel e desktop, exigindo zero violações de qualquer gravidade. Como o jsdom não calcula cores nem layout, o contraste é testado a partir dos tokens do CSS e foi conferido com axe no Chromium real.
- `--slate-500` mudou de `#718096` (4,0:1 sobre branco) para `#5b6b7f` (≥ 5:1), cumprindo WCAG AA para texto pequeno. Nenhuma outra cor foi alterada.
- Cada rota fica dentro de um error boundary: resposta malformada ou chunk indisponível após um deploy não apagam a aplicação inteira.

## 2026-10-05 — Segurança e modo de demonstração

- A configuração é feita só por variáveis de ambiente (`APP_ENV`, `DEMO_MODE`, `WRITE_ENABLED`, `CORS_ORIGINS`). Os padrões preservam o comportamento local atual; valor desconhecido de `APP_ENV` é tratado como produção (falha fechada).
- A escrita é bloqueada no servidor (403). A interface apenas reflete o estado. Simulações continuam liberadas porque não persistem nada.
- A limpeza de dados de demonstração não é exposta por API. Ela é um procedimento operacional (script com simulação por padrão, confirmação explícita e backup JSON, ou SQL no Supabase).
- Decisões e casos passam a exigir SKU existente na base, para não aceitar registros que não correspondem a nenhum item analisado.
- Logs passam por um filtro que remove `DATABASE_URL`, connection strings e senhas, inclusive em tracebacks.
- O frontend publica CSP sem `unsafe-inline` (estilos dinâmicos do React usam CSSOM) e `connect-src 'self' https:`, porque o domínio da API varia por publicação.
- O Vite foi atualizado de 6.0.11 para 6.4.3 (mesma série), corrigindo o aviso *high* do servidor de desenvolvimento. O react-router permanece em 6.30.6, a última da série 6. O retorno do detalhe do SKU passou a aceitar só caminhos internos (`isInternalPath`).
- Autenticação (Supabase Auth e perfis) continua fora desta etapa, como previsto no plano.

## 2026-10-05 — Documentação, deploy e demonstração

- A documentação de referência é a listada no README: arquitetura, API, cálculos, regras, priorização, regras comerciais, deploy e decisões. Os planos antigos (`docs/plano-*.md`) ficam como histórico.
- O relatório da Semana 4 registra números datados, com o hash da planilha. A fonte de verdade contínua é a Central de validação.
- O smoke test pós-deploy é um script somente leitura, sem dependências externas. A única requisição de escrita usa um SKU inexistente e precisa ser recusada, então o script pode ser rodado contra produção sem gravar dados.
- O roteiro de demonstração segue os cinco blocos do plano e usa exemplos reais da base: CI-0041 (prioridade alta sem produção), CI-0014 (produzir após validar capacidade) e KA-01/CI-0011 (reposição no parceiro).
- O teste moderado com usuários permanece pendente; seu protocolo está documentado.

## 2026-10-07 — Etapa 15: correção do motor de decisão (G1–G5)

Origem: análise crítica de aderência ao PDF do desafio, que encontrou recomendações erradas nos casos centrais da base. Protocolo em [historico.md](historico.md), Etapa 15.0; comparação em [etapa-15/antes-depois.md](etapa-15/antes-depois.md).

- **D1:** o princípio "não alterar previsão, ranking, regras nem quantidade oficial" das etapas 10–14 foi revogado para G1–G5. As mudanças foram versionadas e comparadas antes × depois, e toda alteração de caso congelado foi registrada no histórico de ajustes da validação.
- **D2 — previsão oficial v2:** `seasonal_level` (mês do ano anterior ajustado pelo nível, teto 3,0), sem seleção por SKU, horizonte de 6 meses. Promovida porque atendeu aos quatro critérios fixados antes do teste.
- **D3 — data de planejamento:** 14/09/2026, a primeira semana de `Capacidade_Semanal`.
- **D4 — capacidade:** `CAPACITY_SHORTFALL` (o que não cabe após encaixar as ordens planejadas) substitui `CAPACITY_CONFLICT` (ocupação média); o peso e o limiar antigos saíram da configuração.
- **D5 — rótulos do PDF para os riscos novos:** acúmulo no parceiro → Investigar; estoque alto estável → Monitorar; rever OP → Investigar; falta inevitável e antecipar OP → Priorizar produção.
- **D6 — tela:** rota `/capacidade` em Planejamento, com orçamento de volume próprio. É aberta por botão na fila, sem abas, mantendo a decisão do redesign.
- **Protocolo:** casos-alvo (VC-20 a VC-30), limiares, pesos e origens de avaliação foram gravados antes do código. Quando um caso falhou, nem código nem expectativa foram ajustados para passar; a decisão foi levada ao usuário:
  - cobertura pela previsão dos 3 próximos meses (e não pelas vendas recentes), com o VC-03 passando do CI-0044 para o CI-0040;
  - manutenção da precedência do plano (falta inevitável antes de produzir e de rever OP; ordem planejada antes de monitorar excesso), com VC-03, VC-08 e VC-22 revistos.
- **Fora do escopo:** tendência ano contra ano, alocação de produto escasso entre parceiros e regiões, reconciliação Sell_In × Vendas_24m, recalibração das faixas P10–P90.


## 2026-10-09 — Benchmark de modelos e aba Modelo de previsão

Origem: reunião do grupo que pediu avaliar modelos de machine learning e dar transparência às premissas.

- **Benchmark fora da API:** Prophet, statsforecast, scikit-learn e LightGBM ficam em `requirements-ml.txt` e rodam por `scripts/benchmark_models.py`. A API publicada continua só com `requirements.txt`, porque as bibliotecas somariam de 120 a 320 MB a uma função Python com limite de 500 MB na Vercel.
- **Histórico em SQLite local** (`runtime/benchmarks.db`), não em arquivo versionado nem no Supabase: cada rodada guarda o protocolo, o hash da planilha, o ambiente e um resultado por modelo.
- **Sem cron:** a base é uma planilha que muda pouco. A rodada é refeita quando a planilha muda, e a tela avisa quando a última rodada é de outra planilha.
- **Modelo oficial mantido:** nenhum modelo superou o `seasonal_level` (8,0%) no protocolo de avaliação; o melhor foi AutoARIMA (13,3%) e o Prophet ficou em 36,4%. Detalhes em [cálculos](calculations.md#30-benchmark-de-modelos-model_benchmarkpy-fora-do-pipeline-oficial).
- **Tela:** rota `/modelo` em Confiança, em aba ao lado da Validação, com orçamento de volume próprio, porque a Validação já usa quase todo o seu.

## 2026-10-09 — Projeção de estoque no parceiro só no backend

- **Escopo:** API pronta (`GET /api/partner-stock-projection`), sem tela, até o grupo validar.
- **Método:** média de 6 meses para sell-out e sell-in, a de menor erro medida (26,4% e 28,2%). O cenário sem reposição acompanha o cenário com reposição porque não depende de prever sell-in.
- **Erro sempre exposto:** os erros de sell-in e de sell-out saem em toda resposta, no agregado e por par, para a tela poder mostrar a incerteza se for aprovada.
