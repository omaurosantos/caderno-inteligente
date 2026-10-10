# Arquitetura

```text
XLSM (somente leitura, empacotado no deploy) ── ou ── tabelas por aba no banco (fase 3, DATA_SOURCE=banco)
        │
        ▼
Núcleo Python determinístico — src/caderno_inteligente/
  ingestão → validação → normalização → indicadores → regras → priorização
                                         └→ previsão → recomendação operacional
                                         └→ visão parceiro–SKU (comercial)
        │
        ▼
FastAPI — backend/  (pipeline em cache, routers aditivos, segurança)
        │                              │
        ▼                              ▼
React + TypeScript + Vite        SQLite local / PostgreSQL (Supabase)
frontend/                        decisões, casos, histórico e execuções
```

O protótipo apoia o PCP com sinais auditáveis. Nenhum componente libera produção, altera a planilha ou grava configuração oficial.

## Núcleo Python (`src/caderno_inteligente/`)

| Módulo | Responsabilidade |
|---|---|
| `ingestion.py`, `validation.py`, `transformations.py` | Leitura das abas com cabeçalho na linha 3, validação sem correção silenciosa e normalização em cópias internas |
| `indicators.py` | Uma linha por SKU: cobertura, carteira, produção aberta, datas, sell-in/out, capacidade familiar ([cálculos](calculations.md)) |
| `rules.py`, `prioritization.py` | Sete regras determinísticas e soma transparente de pesos ([regras](rules.md), [priorização](prioritization.md)) |
| `forecasting.py`, `recommendations.py` | Previsão mensal (média móvel 3m × sazonal 12m, holdout de 3 meses) e ação/quantidade sugerida por SKU ([Semana 3](semana-3-modelo-preditivo.md)) |
| `partner_insights.py` | Pares parceiro–SKU reais, sinais e ações comerciais ([regras comerciais](commercial-rules.md)) |
| `validation_center.py` | Linha de base, baseline de previsão, casos congelados e comportamento seguro ([Semana 4](semana-4-validacao-v2.md)) |
| `run_comparison.py`, `runs.py` | Snapshot versionado e comparação entre execuções |
| `partner_stock_projection.py` | Projeção de estoque no parceiro com erros de sell-in e sell-out; só API, sem tela |
| `model_card.py` | Cartão do modelo oficial: o que prevê, premissas, erro e limitações |
| `model_benchmark.py`, `benchmark_store.py` | Benchmark de modelos (statsforecast, scikit-learn, LightGBM, Prophet) contra o oficial e histórico das rodadas em SQLite local; fora do pipeline oficial |
| `persistence.py`, `postgres_persistence.py`, `feedback.py`, `cases.py` | Mesmo contrato em SQLite e PostgreSQL |
| `dataset_store.py`, `auth.py` | Fase 3: abas no banco (mesmos DataFrames da planilha), cadastro de SKU com exclusão lógica, versão dos dados e login ([fase 3](fase-3-banco-e-cadastro.md)) |

## Backend (`backend/`)

- `main.py` monta o pipeline e o mantém em **cache em memória**. O cache é protegido contra reconstruções concorrentes e invalidado quando mudam a data ou o tamanho do XLSM, dos pesos ou dos limiares. Com `DATA_SOURCE=banco`, o XLSM dá lugar à versão dos dados no banco.
- Routers aditivos:
  - `partners.py`: visão comercial;
  - `validation.py`: Central de validação;
  - `run_comparisons.py`: comparação de execuções;
  - `registry.py`: login e cadastro de SKU (fase 3);
  - `model_benchmark.py`: cartão do modelo e rodadas do benchmark;
  - `partner_stock_projection.py`: projeção de estoque no parceiro (sem tela).
- `security.py` reúne:
  - ambiente (`APP_ENV`);
  - modo demonstração (`DEMO_MODE`);
  - escrita desabilitável (`WRITE_ENABLED`);
  - CORS validado;
  - limite de corpo de 16 KB;
  - erros genéricos em produção com `X-Request-ID`;
  - cabeçalhos de segurança;
  - filtro que remove `DATABASE_URL` dos logs.
- A persistência usa SQLite em `runtime/` localmente. Quando `DATABASE_URL` existe, usa o Transaction Pooler do Supabase, com prepared statements desabilitados.
- O contrato completo dos endpoints está em [API](api.md).

## Frontend (`frontend/src/`)

- **Organização:**
  - contratos em `types*.ts`;
  - acesso à API em `api.ts`;
  - componentes em `components.tsx` e `components/`;
  - hooks em `hooks/`;
  - uma página por arquivo em `pages/`;
  - orquestração em `App.tsx`.
- **Carregamento por rota:** cada página consulta só o que exibe. As páginas usam `React.lazy`, e as leituras são canceladas ao trocar de rota.
- **Robustez:** um error boundary por rota evita tela em branco quando a página falha ou um chunk deixa de existir após um deploy.
- **Páginas estáticas:** o Guia e a 404 não consultam a API.
- **Modo da publicação:** o modo vem de `GET /api/system` e só é consultado em páginas com dados. Ele gera o aviso de demonstração ou de somente leitura e desabilita os formulários quando a escrita está bloqueada. O servidor continua aplicando a regra em qualquer caso.
- **Acessibilidade:**
  - título da aba por rota;
  - link "Pular para o conteúdo";
  - foco no título após cada navegação;
  - gaveta móvel com foco e tecla Esc;
  - contraste WCAG AA nos tokens de cor.

### Mapa de rotas

O menu agrupa as rotas em 8 entradas: Início; Planejamento (`/fila`, `/capacidade`, `/cenarios`); SKUs (`/skus` e o detalhe `/skus/:sku`); Financeiro (`/faturamento`); Comercial (`/parceiros`, `/carteira`, `/canais`, `/parceiros/:codigo`, `/canais/:canal`); Acompanhamento (`/casos`, `/decisoes`); Confiança (`/validacao`, `/modelo`); Bastidores (`/auditoria`, `/execucoes`, `/qualidade`). Os endereços antigos `?aba=parceiros` e `?aba=diretos` redirecionam para `/carteira` e `/canais`. Todos os estilos estão em `frontend/src/styles.css` (tokens no topo).

| URL | Página | Dados consultados |
|---|---|---|
| `/guia` | Guia de uso | Nenhum (funciona com a API fora do ar) |
| `/` | Início — o primeiro SKU da fila no topo e, abaixo, o painel: indicadores de ruptura, 5 SKUs com risco de ruptura, 5 oportunidades de reposição e o gráfico de faturamento. Oportunidades e faturamento carregam e falham cada um por si | `overview`, `priorities`, `config`, `events`, `commercial-recommendations?action=avaliar_reposicao`, `revenue-forecast` |
| `/fila` | Fila operacional — filtros `busca`, `familia`, `acao`, `rotulo`, `confianca`, `sinal` (`ruptura`), `ordem`, `todos` na URL; junta posição e ação pelo SKU no cliente; gráfico de produção planejada por mês, que segue o filtro de família | `priorities`, `forecasts`, `config`, `events`, `production-plan` |
| `/faturamento` | Faturamento previsto — filtros `busca`, `familia` no topo (a família também restringe o resumo); SKUs paginados de 10 em 10 | `revenue-forecast` |
| `/skus` | Lista de SKUs — filtros `busca`, `familia`; paginada de 10 em 10; cada linha abre `/skus/:sku` | `forecasts` |
| `/prioridades`, `/previsoes` | Redirecionam para `/fila` (mesmos parâmetros) | Nenhum |
| `/skus/:sku` | Detalhe do SKU (compartilhável), abas em `?tab=`; o contexto comercial só carrega na aba Parceiros | `priorities/{sku}`, `commercial-recommendations?sku=` (aba Parceiros) |
| `/casos` | Casos — edição por linha (`PUT cases/{id}`), filtros `status`, `responsavel` | `cases`, `priorities`, `config` |
| `/qualidade` | Dados da planilha | `data-quality` |
| `/parceiros` | Comercial › Oportunidades — filtros `busca`, `regiao`, `canal`, `ordem` | `partners`, `commercial-recommendations?action=avaliar_reposicao` |
| `/carteira` | Comercial › Parceiros — filtros `busca`, `regiao`, `canal`, `rotulo`, `ordem` | `partners` |
| `/canais` | Comercial › Canais diretos | `direct-channels` |
| `/parceiros/:codigo` | Detalhe do parceiro — filtros `sku`, `acao`, `qualidade`, `offset` | `partners/{codigo}`, `partners/{codigo}/skus` |
| `/cenarios` | Simulação de cenários | `config`, `POST scenarios` |
| `/execucoes` | Execuções; comparação em `?base=&alvo=` | `runs`, `run-comparisons` |
| `/decisoes` | Histórico de decisões (feedback do PCP) | `feedback`, `priorities`, `config` |
| `/validacao` | Central de validação (resumo, falhas e 2 abas; a aba de modelos inclui o laboratório de previsão) | `validation/summary`, `forecast-lab` |
| `/modelo` | Confiança › Modelo de previsão: o que o modelo prevê, premissas, erro e modelos comparados | `model-benchmark` |
| `/auditoria` | Auditoria: casos de teste, verificações, limitações, ajustes e método comercial | `validation/summary`, `partners?limit=1` |
| `*` | Página não encontrada | Nenhum |

Códigos de SKU e de parceiro são codificados na URL com `encodeURIComponent`, por exemplo `/parceiros/Loja%20pr%C3%B3pria`.

## Publicação (Vercel + Supabase)

O deploy usa dois projetos Vercel do mesmo repositório.

- **Backend:**
  - Root Directory na raiz, com entrypoint `backend.main:app` (definido em `pyproject.toml`);
  - `vercel.json` empacota `config/**`, `data/source/**` e `src/caderno_inteligente/**`;
  - a Function não escreve no filesystem.
- **Frontend:**
  - Root Directory `frontend`, build `npm run build` e saída `dist`;
  - o `frontend/vercel.json` define as regras abaixo.

### Regras do `frontend/vercel.json`

- **Rewrite:** `"source": "/(.*)" → "/index.html"`. Abrir ou atualizar qualquer rota interna entrega a SPA, e o React Router resolve a página. Arquivos existentes em `dist/` continuam sendo servidos diretamente.
- **Cabeçalhos:**
  - `Content-Security-Policy` sem `unsafe-inline` e com `connect-src 'self' https:`, porque o domínio da API varia;
  - `X-Content-Type-Options: nosniff`;
  - `X-Frame-Options: DENY`;
  - `Referrer-Policy: no-referrer`;
  - `Permissions-Policy`.

O passo a passo, as variáveis e o smoke test estão em [Deploy com Vercel e Supabase](deploy-vercel-supabase.md).

## Testes

- **Python:** `pytest` cobre núcleo, API, persistência, segurança, contrato com o frontend e o próprio smoke test.
- **Frontend:** `npm run check` executa, em ordem:
  1. typecheck;
  2. Vitest + Testing Library + axe-core (rotas, teclado, estados, acessibilidade, contraste e contratos);
  3. testes `node --test`;
  4. build;
  5. varredura de segredos no bundle.
- **Contrato entre as camadas:** `frontend/src/test/contract-keys.json` lista os campos que o frontend lê. O arquivo é validado contra as fixtures no Vitest e contra a API real no pytest.
