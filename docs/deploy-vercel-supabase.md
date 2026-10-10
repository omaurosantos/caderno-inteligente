# Deploy com Vercel e Supabase

Este guia pressupõe que todas as mudanças locais foram testadas. Ele não contém credenciais reais e não deve receber senhas em commits.

## 1. Supabase

1. Crie um projeto.
2. Abra o SQL Editor e execute, nesta ordem, `supabase/migrations/001_initial.sql`, `supabase/migrations/002_run_comparison.sql` e `supabase/migrations/003_challenge_action.sql`. A 002 e a 003 são aditivas e podem ser executadas mais de uma vez: a 002 adiciona a coluna opcional `runs.comparison`; a 003, a coluna opcional `feedback.challenge_action` (sem ela, a decisão é gravada sem o rótulo do desafio).
3. Em **Connect**, escolha **Transaction pooler**.
4. Copie a connection string da porta `6543` e acrescente `sslmode=require` se ainda não estiver presente.
5. Confirme no Table Editor que RLS está habilitado e que não existem políticas públicas nas quatro tabelas.

Formato esperado:

```text
postgresql://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:6543/postgres?sslmode=require
```

## 2. Backend na Vercel

Importe o repositório e mantenha a raiz como Root Directory. A Vercel encontra o FastAPI por meio de:

```toml
[tool.vercel]
entrypoint = "backend.main:app"
```

Configure somente no projeto backend:

```text
DATABASE_URL=<connection string do Transaction Pooler>
CORS_ORIGINS=https://DOMINIO-DO-FRONTEND.vercel.app
LOG_LEVEL=INFO
APP_ENV=production
DEMO_MODE=true
WRITE_ENABLED=true
```

- `APP_ENV=production` oculta detalhes internos nas respostas de erro; a causa fica no log da Vercel, já sem `DATABASE_URL`.
- `DEMO_MODE=true` exibe o aviso de publicação de demonstração.
- Para uma publicação aberta sem registro de dados, use `WRITE_ENABLED=false`: decisões, casos e execuções retornam 403 e a interface desabilita os formulários.
- Para limpar dados de demonstração, execute `supabase/maintenance/reset_demo_data.sql` no SQL Editor ou `python scripts/reset_demo_data.py --postgres --confirm` com `DATABASE_URL` no ambiente do terminal (gera backup JSON antes).

Depois do deploy, valide:

```text
GET https://DOMINIO-DO-BACKEND.vercel.app/api/health
```

O retorno deve indicar `status: ok`, `database: ok` e `persistence: postgres`.

Para ler a base do banco e habilitar o login e o cadastro de SKU (fase 3), rode também a migração `004_dataset_and_auth.sql`, importe a planilha e configure `DATA_SOURCE=banco` e `AUTH_SECRET`. O passo a passo está em [fase-3-banco-e-cadastro.md](fase-3-banco-e-cadastro.md).

## 3. Frontend na Vercel

Importe o mesmo repositório em um segundo projeto e configure:

```text
Root Directory: frontend
Framework: Vite
Build command: npm run build
Output directory: dist
```

Variável do frontend:

```text
VITE_API_URL=https://DOMINIO-DO-BACKEND.vercel.app/api
```

Essa variável é pública por definição e deve conter apenas a URL da API, sempre com `https://`, porque a CSP do frontend só permite conexões HTTPS externas. Nunca use prefixo `VITE_` em senhas ou chaves privilegiadas.

O `frontend/vercel.json` já define o rewrite da SPA (`/(.*)` → `/index.html`), que permite abrir ou atualizar qualquer rota interna, e os cabeçalhos de segurança (CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy` e `Permissions-Policy`). Não é preciso configurar nada no painel.

## 4. Ajuste final de CORS

Após conhecer o domínio definitivo do frontend, atualize `CORS_ORIGINS` no projeto backend e faça novo deploy. Separe múltiplas origens por vírgula.

Não use `*`: a API possui operações de escrita. CORS também não substitui autenticação.

## 5. Smoke test automatizado (somente leitura)

Depois de publicar backend e frontend, rode a partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --backend https://DOMINIO-DO-BACKEND.vercel.app --frontend https://DOMINIO-DO-FRONTEND.vercel.app --expect-environment production
```

Acrescente `--expect-readonly` se a publicação usa `WRITE_ENABLED=false` e `--expect-demo` se usa `DEMO_MODE=true`. O script usa só a biblioteca padrão do Python e verifica:

- **Backend:**
  - health, planilha empacotada e persistência;
  - `X-Request-ID` e `nosniff`;
  - `/api/system` sem dados de conexão e com os modos esperados.
- **Dados:**
  - overview e ranking sequencial;
  - detalhe do primeiro SKU com revisão humana obrigatória;
  - SKU inexistente → 404;
  - uma previsão por SKU.
- **Comercial e validação:**
  - parceiros, detalhe e matriz parceiro–SKU;
  - Central de validação com 8 casos e planilha igual à congelada.
- **Segurança:**
  - CORS aceita o frontend e recusa origem desconhecida;
  - uma sondagem de escrita com SKU inexistente deve ser recusada (422, ou 403 em somente leitura) e **nunca grava dados**.
- **Frontend:**
  - rewrite da SPA em `/`, `/guia`, `/prioridades`, `/previsoes`, `/validacao`, `/execucoes?…`, `/skus/:sku`, `/parceiros/:codigo` e em uma rota inexistente;
  - CSP, `X-Frame-Options` e `nosniff`;
  - bundle acessível e sem segredos.

O script termina com `N/N verificações aprovadas` e código de saída 0. Qualquer `FALHA` retorna código 1 e indica o item.

### Conferência manual complementar

1. Abra a Visão geral, uma prioridade e um parceiro no navegador e confira o console (nenhuma violação de CSP).
2. Execute um cenário.
3. Se a escrita estiver habilitada:
   - crie e atualize um caso, registre uma decisão e registre uma execução;
   - faça redeploy do backend e confirme que os registros continuam presentes;
   - depois, limpe os dados de teste (`supabase/maintenance/reset_demo_data.sql` ou `scripts/reset_demo_data.py --postgres --confirm`).
4. Revise os logs da Function: não devem conter a `DATABASE_URL`.

## 6. Desenvolvimento local

Sem `DATABASE_URL`, o backend usa automaticamente os bancos SQLite em `runtime/`. O proxy do Vite mantém `/api` apontando para `127.0.0.1:8000`, portanto `VITE_API_URL` também é opcional localmente.

Para testar deliberadamente com Supabase, defina `DATABASE_URL` apenas na sessão local ou em um `.env` não versionado. O projeto não carrega `.env` automaticamente; exporte a variável no terminal ou use a configuração da sua IDE.
