# Fase 3: base no banco, login e cadastro de SKU

Origem: [proposta-melhorias.md](proposta-melhorias.md), fase 3. A planilha continua sendo a fonte padrão e a base dos testes. Nada muda enquanto `DATA_SOURCE` não for `banco`.

## O que entrou

| Parte | Onde |
|---|---|
| Uma tabela por aba (12 obrigatórias + `Precos_Produtos`), versão dos dados, trilha de alterações e usuários | `supabase/migrations/004_dataset_and_auth.sql` |
| Leitura e escrita da base no banco (PostgreSQL ou SQLite local) | `src/caderno_inteligente/dataset_store.py` |
| Senha (scrypt) e token assinado (JWT HS256), só com a biblioteca padrão | `src/caderno_inteligente/auth.py` |
| Rotas de login e cadastro | `backend/registry.py` |
| Fonte configurável e recálculo pela versão | `backend/main.py` (`DATA_SOURCE`, `load_source`, `_pipeline_signature`) |
| Importação única da planilha e criação de usuários | `scripts/import_workbook.py`, `scripts/create_user.py` |
| Login, adicionar, editar, excluir e reativar na lista de SKUs | `frontend/src/components/SkuRegistry.tsx`, `frontend/src/pages/SkuListPage.tsx` |

## Como os dados ficam no banco

- Cada linha de aba vira uma linha da tabela `sheet_<aba>` com o registro em `data` (jsonb, chaves iguais às colunas da planilha). `dataset_sheets.columns` guarda a ordem e o tipo de cada coluna.
- A API remonta exatamente os DataFrames que `load_workbook` lê da planilha. O teste `test_database_returns_exactly_the_frames_the_workbook_gives` compara aba por aba, e `test_database_source_gives_the_same_ranking_as_the_spreadsheet` compara o ranking. Cálculos, ranking e previsão não mudam.
- A coluna `sku` de cada tabela (normalizada em maiúsculas) serve para filtrar e indexar. Em `sheet_produtos`, `active = false` é a exclusão lógica.

## Versão dos dados

`dataset_version.version` aumenta a cada importação e a cada alteração de SKU, na mesma transação. A assinatura do cache do pipeline passa a ser `("banco", versão)` no lugar da data e do tamanho do XLSM:

- a instância que gravou recalcula já na próxima consulta;
- as outras instâncias consultam a versão no máximo a cada 5 s (`VERSION_CHECK_SECONDS`) e recalculam quando ela muda.

## Cadastro de SKU

- O formulário cobre o que o pipeline cruza com `Produtos`: produto, família, curva ABC, prazo de produção, lote mínimo, estoque atual, estoque de segurança e venda média por dia. Uma alteração grava as linhas do SKU em `Produtos`, `Estoque_Atual` e `Lead_Times`. As colunas que o formulário não cobre (por exemplo, `Coleção/Versão` e `Local`) são preservadas.
- Derivados, na mesma unidade da planilha: cobertura em dias = estoque ÷ venda média por dia, arredondada (0 sem venda cadastrada), e demanda média mensal = venda média por dia × 30.
- A família precisa existir na base, porque a capacidade e as linhas dependem dela.
- Validação: os campos têm tipos e limites no Pydantic. Depois, a API aplica a alteração a uma cópia da base inteira e roda `validate_dataset` (as regras de `schemas.py`). A gravação é recusada se surgir um erro que a base não tinha antes (chave duplicada, valor negativo, SKU órfão).
- **Exclusão lógica:** o SKU sai de todas as abas no cálculo (fila, previsões, detalhe e registro de novos casos). Casos, decisões e execuções que já o citam ficam como estão. Reativar devolve o SKU com os dados de antes.
- Toda alteração fica em `sku_changes`, com usuário, ação, antes e depois.
- Um SKU novo não tem histórico de vendas. A previsão fica como "dados insuficientes" até haver vendas na base, como já acontece com SKUs sem histórico.

## Login

**Login desligado por enquanto:** `AUTH_REQUIRED` é `false` por padrão. O cadastro de SKU fica liberado para quem abre a lista de SKUs, e as alterações são registradas como `sem-login` em `sku_changes`. O login continua implementado e testado: para religá-lo, configure `AUTH_REQUIRED=true` e `AUTH_SECRET` e crie os usuários com `scripts/create_user.py`.

Com `AUTH_REQUIRED=true`:

- Login próprio no FastAPI, sem serviço externo (decisão da seção 3.2 da proposta). Os usuários ficam em `app_users`, no mesmo banco, e só são criados pelo script. Não há cadastro público.
- Senha com no mínimo 10 caracteres, guardada com scrypt e sal aleatório. O token aceita apenas HS256, expira em `AUTH_TOKEN_HOURS` (padrão 8 h, no máximo 24 h) e, a cada uso, o servidor confere se o usuário continua ativo.
- Cinco tentativas erradas para o mesmo e-mail em 10 minutos bloqueiam novas tentativas (429). O controle fica na memória de cada instância.
- O frontend guarda o token no `localStorage` e o envia só nas rotas de cadastro (`Authorization: Bearer`). Uma resposta 401 encerra a sessão local.
- Decisões, casos e execuções continuam sem login, como antes. A proposta exige login apenas antes do cadastro de SKU.

## Variáveis de ambiente (backend)

| Variável | Padrão | Efeito |
|---|---|---|
| `DATA_SOURCE` | `planilha` | `banco` lê as abas do banco e habilita o cadastro. Valor desconhecido mantém a planilha |
| `AUTH_REQUIRED` | `false` | `true` exige login no cadastro de SKU. Com `false`, o cadastro fica liberado e o formulário de login não aparece |
| `AUTH_SECRET` | — | Secreta, com 32 caracteres ou mais. Sem ela, o desenvolvimento usa um segredo aleatório por processo e a produção desliga o login (503) |
| `AUTH_TOKEN_HOURS` | `8` | Validade do token, entre 1 e 24 h |

O banco é o mesmo da persistência: `DATABASE_URL` quando existe; sem ela, SQLite em `runtime/dataset.db`.

## Passo a passo

### Local (SQLite)

```powershell
.\.venv\Scripts\python.exe scripts\import_workbook.py
.\.venv\Scripts\python.exe scripts\create_user.py --email pcp@exemplo.com --name "PCP"
$env:DATA_SOURCE = "banco"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Publicado (Supabase, API na Vercel)

O banco é o mesmo Supabase que já guarda execuções, casos e decisões. Não há um segundo banco.

1. No SQL Editor do Supabase, rode `supabase/migrations/004_dataset_and_auth.sql` (as 001 a 003 já estão aplicadas). A migração é aditiva e pode ser executada mais de uma vez.
2. Importe a planilha e crie os usuários a partir da sua máquina, com a `DATABASE_URL` do Transaction Pooler (porta 6543) só no ambiente do terminal:

   ```powershell
   $env:DATABASE_URL = "<connection string do Transaction Pooler do Supabase>"
   .\.venv\Scripts\python.exe scripts\import_workbook.py --postgres
   .\.venv\Scripts\python.exe scripts\create_user.py --email pcp@exemplo.com --name "PCP" --postgres
   ```

3. No projeto backend da Vercel, mantenha a `DATABASE_URL` que já existe e acrescente `DATA_SOURCE=banco` e `AUTH_SECRET` (por exemplo, `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
4. Confira `GET /api/system`: deve retornar `data_source: "banco"` e `auth_enabled: true`. Depois, entre pela lista de SKUs.

Sem `DATA_SOURCE=banco`, a API continua lendo a planilha empacotada, mesmo com as tabelas da 004 criadas.

## Limitações conhecidas

- **Hash da fonte:** `source_hash` das execuções, a Central de validação e o Laboratório de previsão continuam calculando o hash do XLSM empacotado, mesmo com `DATA_SOURCE=banco`. Depois de uma alteração de SKU, esse hash não identifica a base usada. A versão dos dados está em `dataset_version`.
- **Abas fora do cadastro:** vendas, pedidos, ordens, sell-in/out, preços e o restante só mudam por uma nova importação (`--replace`), que descarta o cadastro feito pela tela.
- **Bloqueio de login por instância:** na Vercel, cada função tem o seu contador; o limite é por instância, não global.
