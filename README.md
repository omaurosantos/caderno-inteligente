# Caderno Inteligente

Protótipo de apoio à decisão do PCP em uma cadeia B2B2C. Ele lê uma base XLSM sem alterá-la e, a partir dela:

- valida os dados e calcula indicadores e regras auditáveis;
- ordena SKUs para atenção;
- prevê a demanda (6 meses, com sazonalidade) e projeta o estoque dia a dia para sugerir ações operacionais datadas (por SKU), verificar a capacidade de cada linha e sugerir ações comerciais (por parceiro);
- registra as decisões humanas.

**Nenhuma saída é uma decisão automática.** Cada prioridade e recomendação mostra motivos, evidências, origem dos dados, limitações, nível de confiança e exige revisão humana. Dado ausente é tratado como ausente, nunca como zero, e dados globais (estoque do CD, produção, capacidade, forecast) não são distribuídos entre parceiros.

## O que o protótipo responde

| Pergunta do PCP | Onde |
|---|---|
| O que exige atenção agora e por quê? | Início e Planejamento › Fila operacional: ordem por faixa de urgência e valor em risco em reais (observado × estimado), com a soma transparente de pesos de onze regras como pontuação de sinais; o motivo diz a faixa, o valor e quando a falta começa |
| Quais decisões precisam ser tomadas hoje? | Início › Decisões de hoje: o que decidir, em qual SKU e até quando (alavanca e prazo) |
| Quem atender primeiro quando o estoque não cobre todos? | Detalhe do SKU › "Quem atender primeiro" (ordem de atendimento por pedido, com os componentes da pontuação) e Comercial › "Risco por região": sugestão sobre pedidos confirmados, que não reserva estoque |
| Até onde vemos o consumidor? | Comercial › Parceiros: 75,1% das unidades faturadas têm venda ao consumidor observada (venda direta de E-commerce, Marketplace e Loja própria mais sell-out informado pelos KAs); o resto é "sem visibilidade" |
| Preciso produzir? Quanto? Quando? | Fila operacional (ação, quantidade a liberar nas próximas 4 semanas) e Detalhe do SKU › Evidências › "Plano de suprimento": pedidos afetados, OPs a antecipar, reduzir ou cancelar, ordens planejadas com data de liberação e projeção semanal |
| Quanto vou produzir em cada mês? | Fila operacional: gráfico de produção planejada por mês de liberação (liberar agora × depois), no total ou na família filtrada; plano sugerido, não ordem liberada |
| Onde a produção não cabe? | Planejamento › Capacidade (botão "Ver capacidade" na fila): ordens planejadas encaixadas na capacidade livre de cada linha e semana, com o que fica sem programação e os pedidos afetados; depois do calendário da base, a capacidade é estimada e rotulada como tal |
| Algum parceiro tem risco ou oportunidade? | Comercial: oportunidades ordenadas por menor cobertura de estoque, com a matriz parceiro–SKU com sell-in, sell-out, estoque estimado, estoque acumulando ("não repor") e sugestão comercial |
| Quanto vamos faturar nos próximos meses? | Financeiro › Faturamento previsto: faturamento estimado (previsão em unidades × preço vigente), sempre rotulado como estimativa, com erro do teste e, no SKU, o cálculo |
| Qual a ação do desafio para cada SKU, parceiro ou canal? | Fila operacional, Comercial e Canais diretos: rótulo (Produzir, Repor, Priorizar produção, Priorizar parceiro, Ampliar mix, Recomendar recompra, Monitorar, Investigar, Sem ação necessária) com evidências e filtro; a legenda está no Guia |
| Como vão os canais diretos? | Comercial › Canais diretos: faturamento observado, tendência, carteira e sugestão por SKU, sem estoque por canal; achados entre abas em Dados da planilha |
| Que evento do calendário vem aí e quando decidir? | Início e Fila operacional: alertas de eventos com data de decisão (início − lead time); no SKU, evidência histórica e cenário com evento, sempre como estimativa |
| O que o modelo de previsão faz e quais premissas usa? | Confiança › Modelo de previsão: o que é previsto, premissas, erro medido e comparação com outros modelos (statsforecast, scikit-learn, LightGBM, Prophet) |
| Quanto confiar na análise? | Confiança › Validação e Bastidores › Dados da planilha: erro da previsão em meses normais e de pico, cobertura de sell-out, divergência do cadastro (inclusive ABC e sell-in × faturado), casos congelados (34 de 34) e falhas conhecidas |
| Quais regras existem e não dispararam? | Bastidores › Auditoria › Cobertura de regras: disparos por regra e, para as que não dispararam (Ampliar mix, Recomendar recompra, Reativar), o motivo com o número que o comprova; mais os 23 pares KA para pedir sell-out |
| Onde a IA ajuda e qual o impacto? | Confiança › Modelo de previsão (a previsão aprendida dos dados, testada contra statsforecast, scikit-learn, LightGBM e Prophet; o modelo sazonal simples venceu) e Validação (valor em risco endereçado, pauta Modelo × S&OP e tempo de análise medido; nenhum ganho de processo é afirmado antes de 20 registros) |
| Por que a prioridade mudou? | Bastidores › Execuções: comparação entre snapshots, com decomposição do score |
| O que foi decidido? | Acompanhamento › Casos (status, responsável e prazo editáveis) e Histórico de decisões: ação, efeito do dado do parceiro e tempo de análise |

## Arquitetura

```text
XLSM somente leitura → núcleo Python determinístico → FastAPI (cache do pipeline) → React + TypeScript + Vite
                                                         └→ SQLite local / PostgreSQL (Supabase) em produção
```

Detalhes, módulos, mapa de rotas, rewrite e cabeçalhos da Vercel estão em [Arquitetura](docs/architecture.md).

## Requisitos

- Python 3.11, 3.12 ou 3.13 (recomendado: 3.12; 3.14 não é suportado);
- Node.js 18 ou superior (recomendado: 20 ou mais recente) e npm.

## Preparar o ambiente

No PowerShell, a partir da raiz do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
npm install
cd ..
```

## Executar

Use dois terminais.

```powershell
# Terminal 1 — API
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2 — frontend
cd frontend
npm run dev
```

Acesse `http://127.0.0.1:5173`. O Vite encaminha `/api` para `127.0.0.1:8000`.

### Benchmark de modelos (opcional)

Compara a previsão oficial com statsforecast, scikit-learn, LightGBM e Prophet nas mesmas datas de avaliação e grava a rodada em `runtime/benchmarks.db`, exibida em Confiança › Modelo de previsão. As bibliotecas ficam fora da API publicada.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe scripts\benchmark_models.py                 # modelos rápidos (cerca de 1 minuto)
.\.venv\Scripts\python.exe scripts\benchmark_models.py --include-slow  # inclui Prophet (dezenas de minutos)
```

## Interface

O menu tem 8 entradas (Início, Planejamento, SKUs, Financeiro, Comercial, Acompanhamento, Confiança, Bastidores) e o botão **Ajuda** (guia) na barra superior. As rotas agrupadas aparecem como abas e continuam abrindo por URL. Não há grupo "Avançado": Cenários fica em Planejamento e Execuções em Confiança.

| URL | Menu · página |
|---|---|
| `/guia` | Ajuda: trilhas por papel (PCP, Comercial, Gestão), glossário e perguntas frequentes. Funciona com a API fora do ar |
| `/` | Início: primeiro da fila e o porquê, 3 números e fila de atenção |
| `/fila` | Planejamento › Fila operacional: gráfico de produção planejada por mês; posição, SKU, ação, quantidade, motivo principal e exceções; por padrão, só os que pedem atenção; filtros na URL (`busca`, `familia`, `acao`, `rotulo`, `confianca`, `ordem`, `todos`) |
| `/prioridades` e `/previsoes` | Redirecionam para `/fila` e mantêm os mesmos parâmetros |
| `/faturamento` | Financeiro › Faturamento previsto: estimativa em reais (sempre rotulada como estimativa), famílias, SKUs e filtros `busca` e `familia` |
| `/capacidade` | Planejamento › Capacidade: situação de cada linha, o que não cabe até a necessidade, picos e semanas; aberta pelo botão "Ver capacidade" da fila |
| `/skus/:sku` | Planejamento › Detalhe compartilhável: ação sugerida e botões "Registrar decisão" e "Criar caso" no topo; abas `?tab=resumo\|evidencias\|parceiros\|impacto` |
| `/parceiros` | Comercial › Oportunidades, ordenadas por urgência; filtros `busca`, `regiao`, `canal`, `ordem`. Os endereços antigos `?aba=parceiros` e `?aba=diretos` redirecionam para `/carteira` e `/canais` |
| `/carteira` | Comercial › Parceiros: cobertura de dados de sell-out e sugestões por parceiro; filtros `busca`, `regiao`, `canal`, `rotulo`, `ordem` |
| `/canais` e `/canais/:canal` | Comercial › Canais diretos (faturamento, tendência, carteira) e o detalhe por SKU de cada canal, com filtros `sinal` e `busca` |
| `/parceiros/:codigo` | Matriz parceiro–SKU com evidências mensais na própria linha |
| `/casos` | Acompanhamento › Casos (entrada do grupo): edição de status, responsável e prazo; filtros `status` e `responsavel`; aceita `?sku=` |
| `/qualidade` | Bastidores › Dados da planilha: integridade, lacunas e cobertura de sell-out |
| `/cenarios` | Planejamento: simulação de 2 pesos sem alterar o ranking oficial; abre pelo botão "Simular pesos" da fila |
| `/execucoes` | Bastidores › Execuções: `?base=&alvo=` compara duas execuções |
| `/decisoes` | Acompanhamento › Histórico de decisões; registrar exige escolher o SKU (ou vir de `?sku=`) |
| `/validacao` | Confiança › Validação: resumo, 3 números, falhas conhecidas e 2 abas, com exportação CSV e impressão |
| `/modelo` | Confiança › Modelo de previsão: o que é previsto, premissas, erro medido e modelos comparados no benchmark |
| `/auditoria` | Bastidores › Auditoria (blocos recolhidos): casos de teste congelados, verificações de segurança, limitações, histórico de ajustes e método comercial |

Rotas inexistentes mostram uma página 404. O `frontend/vercel.json` redireciona deep links para o `index.html`, permitindo abrir ou atualizar qualquer URL interna.

## Validar

Tudo de uma vez, a partir da raiz:

```powershell
.\scripts\validate.ps1
```

Comandos individuais:

```powershell
# Testes Python: núcleo, API, persistência, segurança, contrato com o frontend e smoke test
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider
```

```powershell
# Frontend: typecheck, Vitest + Testing Library + axe-core, testes node, build e varredura de segredos no bundle
cd frontend
npm run check
```

Durante o desenvolvimento, `npm run test:watch` reexecuta os testes do frontend. Os testes usam fixtures sintéticas (`frontend/src/test/fixtures.ts`). O arquivo `frontend/src/test/contract-keys.json` lista os campos que o frontend lê e é validado contra a API real por `tests/test_frontend_contracts.py`.

## Configuração

| Item | Onde |
|---|---|
| Pesos do ranking | `config/prioritization_weights.json` |
| Limiares das regras | `config/rule_thresholds.json` |
| Limiares comerciais | `config/commercial_thresholds.json` |
| Fator de eventos (teto, janela de linha de base, antecedência) | `config/event_factors.json` |
| Canais diretos (janela da tendência, faixa neutra, inatividade) | `config/direct_channel_thresholds.json` |
| Rótulos de ação (fila de atenção, janela de evento, reposições, recompra) | `config/challenge_actions.json` |
| Linha de base, casos congelados e histórico de ajustes da validação | `config/validation_center.json` |
| Motor de previsão (cadeia oficial, horizonte, teto sazonal, protocolo de avaliação com pico) | `config/forecast_engine.json` |
| Plano de suprimento (data de planejamento, janela de decisão, cobertura-alvo, excesso projetado) | `config/supply_plan.json` |
| Alocação de estoque escasso (pesos de urgência, canal direto, cobertura e pedido pequeno; atendimento parcial) | `config/allocation.json` |
| Valor em risco e faixas (peso da falta estimada, janela da faixa 2, limites da curva ABC medida) | `config/prioritization_impact.json` |
| Capacidade estimada além do calendário (método, cenário, janela de 8 semanas; `enabled: false` desliga) | `config/capacity_extension.json` |

Variáveis de ambiente do backend (exemplo em `.env.example`):

| Variável | Padrão | Efeito |
|---|---|---|
| `DATABASE_URL` | — | Secreta. PostgreSQL/Supabase pelo Transaction Pooler; sem ela, SQLite em `runtime/` |
| `CORS_ORIGINS` | `localhost:5173` e `127.0.0.1:5173` em desenvolvimento | Origens exatas, sem caminho e sem curinga. Em produção, sem valor, nenhuma origem externa é aceita |
| `APP_ENV` | `development` | `production` retorna erros genéricos com código de referência |
| `DEMO_MODE` | `false` | `true` exibe aviso de dados fictícios que podem ser apagados |
| `WRITE_ENABLED` | `true` | `false` bloqueia decisões, casos, execuções e cadastro de SKU (403); consultas e simulações continuam |
| `DATA_SOURCE` | `planilha` | `banco` lê as abas do banco (importadas com `scripts/import_workbook.py`) e habilita o cadastro de SKU ([fase 3](docs/fase-3-banco-e-cadastro.md)) |
| `AUTH_REQUIRED` | `false` | `true` exige login no cadastro de SKU. Por enquanto, o cadastro fica liberado |
| `AUTH_SECRET` | — | Secreta (32+ caracteres). Assina o login do cadastro de SKU; em produção, sem ela o login fica desligado |
| `AUTH_TOKEN_HOURS` | `8` | Validade da sessão de login (1 a 24 h) |
| `LOG_LEVEL` | `INFO` | Nível de log; os logs nunca imprimem `DATABASE_URL` |

No frontend, `VITE_API_URL` é a URL pública da API (com `https://`). Sem ela, o frontend usa `/api`. O cache do backend é invalidado automaticamente quando a planilha ou os arquivos de pesos e limiares mudam. Nunca versione arquivos `.env` reais.

**Limpeza de dados de demonstração:** `python scripts/reset_demo_data.py` apenas conta os registros. Com `--confirm`, faz backup em JSON e limpa. Com `--postgres`, usa a `DATABASE_URL` do ambiente. A planilha nunca é alterada.

## Publicar com Vercel e Supabase

O deploy usa dois projetos Vercel do mesmo repositório:

1. **Backend:** Root Directory na raiz, entrypoint `backend.main:app` (em `pyproject.toml`);
2. **Frontend:** Root Directory `frontend`, framework Vite e saída `dist`.

Antes de publicar:

1. execute `supabase/migrations/001_initial.sql`, `002_run_comparison.sql`, `003_challenge_action.sql` e `004_dataset_and_auth.sql` no Supabase, nessa ordem (a 004 só é usada com `DATA_SOURCE=banco`);
2. configure no backend `DATABASE_URL` (Transaction Pooler, porta 6543), `CORS_ORIGINS` com o domínio exato do frontend e `APP_ENV=production`;
3. se for demonstração aberta, configure também `DEMO_MODE=true` e, opcionalmente, `WRITE_ENABLED=false`;
4. configure no frontend `VITE_API_URL` com a URL do backend seguida de `/api`.

Depois de publicar, rode o smoke test (somente leitura):

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --backend https://URL-DO-BACKEND --frontend https://URL-DO-FRONTEND --expect-environment production
```

Passo a passo completo em [Deploy com Vercel e Supabase](docs/deploy-vercel-supabase.md).

## Documentação

**Produto e demonstração**

- [Roteiro de demonstração — 5 minutos](docs/roteiro-demonstracao.md)
- [Semana 4 — Validação da V2](docs/semana-4-validacao-v2.md)
- [Semana 3 — Modelo preditivo](docs/semana-3-modelo-preditivo.md)

**Referência técnica**

- [Arquitetura e mapa de rotas](docs/architecture.md)
- [API](docs/api.md)
- [Cálculos](docs/calculations.md), [regras](docs/rules.md), [priorização](docs/prioritization.md) e [regras comerciais](docs/commercial-rules.md)
- [Decisões técnicas](docs/decisions.md)
- [Deploy com Vercel e Supabase](docs/deploy-vercel-supabase.md)
- [Fase 3: base no banco, login e cadastro de SKU](docs/fase-3-banco-e-cadastro.md)

**Histórico**

- [Histórico das etapas](docs/historico.md): o que cada etapa da V2 entregou, decisões e limitações
- [Etapa 15 — antes × depois](docs/etapa-15/antes-depois.md)
- [Etapa 16 — resumo](docs/etapa-16-resumo.md), [especificação](docs/discovery-etapa-16.md) e [antes × depois](docs/etapa-16/antes-depois.md)
