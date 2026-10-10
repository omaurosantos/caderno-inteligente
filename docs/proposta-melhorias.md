# Proposta de melhorias: Caderno Inteligente

**Autor:** Jonatas · **Data:** 08/10/2026 · **Status:** para aprovação

Esta proposta reúne as mudanças discutidas para o protótipo. Nada foi implementado ainda. A execução acontece em um **fork**, com um ambiente de teste próprio, e cada fase volta ao repositório original como um pull request separado, que pode ser aceito ou recusado de forma independente.

## Resumo

| Fase | O que muda | Onde | Esforço |
|---|---|---|---|
| 1 | Telas: Início como painel, Financeiro paginado, lista de SKUs no menu | Frontend | Baixo a médio |
| 2 | Indicador de estoque projetado (agregando a projeção que já existe) | Backend + frontend | Baixo |
| 3 | Planilha migrada para banco de dados, login e cadastro de SKU | Backend + banco + frontend | Alto |
| 4 | Refatoração visual (gráficos e estilo) | Frontend | Médio |

Fases 1 e 2 não dependem do banco e podem ser aprovadas sozinhas. A fase 3 é a única que muda a fonte de dados.

---

## Fase 1: Telas

### 1.1 Início como painel

**Hoje:** o Início responde só "o que olho primeiro": o primeiro SKU da fila, uma frase com os números e a fila de 5. Isso segue uma decisão recente do redesign "folha pautada", que tirou os cartões da tela (`docs/criterio-de-clareza.md`).

**Proposta:** manter essa resposta no topo, para respeitar o critério de clareza, e montar o painel logo abaixo, com:

- **Indicadores de ruptura**: SKUs com risco de ruptura, abaixo do prazo de produção e abaixo da segurança. A API já entrega (`rupture_sku_count`, `below_lead_time_count`, `below_safety_stock_count`).
- **Indicador de estoque projetado**, descrito na fase 2.
- **Os 5 primeiros SKUs com ruptura**, com link para a fila filtrada.
- **As 5 principais oportunidades de reposição** por parceiro, com link "ver todas" para `/parceiros`. A página Comercial continua existindo; o Início mostra um resumo.
- **O gráfico do Financeiro** (faturamento observado × estimado, em R$), reaproveitando o componente `RevenueTrend`, sem alterações.

**Atenção:** o Início passa a carregar também o faturamento e as oportunidades. Cada bloco deve carregar e falhar de forma independente, como já faz o cartão de faturamento, para que um erro não derrube a tela.

### 1.2 Financeiro

- **Filtros no topo**, acima do cartão de resumo. Hoje ficam abaixo dele, embora o filtro de família também altere o resumo.
- **Lista de SKUs paginada, 10 por página**, com navegação entre páginas, no lugar do "ver mais" de 25 em 25 (`RevenueForecastPage.tsx`).

### 1.3 Lista de SKUs no menu

**Hoje:** a página do SKU (`/skus/:sku`) já é dedicada e tem 4 abas: Resumo, Evidências, Parceiros e Impacto financeiro. Só se chega a ela pela fila ou por links.

**Proposta:** nova entrada "SKUs" no menu, com a lista completa (busca e filtro por família), levando à página do SKU. As abas existentes ficam como estão e podem receber mais detalhes. Os botões de adicionar e excluir entram nessa tela na fase 3.

---

## Fase 2: Estoque projetado

**Revisado em 08/10, após o fork:** a versão atual do repositório já tem o plano de suprimento da Etapa 15. Ele projeta o estoque de cada SKU **por dia**, de 14/09/2026 até o fim da previsão, resumido por semana (`docs/calculations.md`, seção 4):

```text
estoque projetado = estoque atual + entradas (OPs e ordens planejadas) − demanda (carteira + previsão, sem dupla contagem)
```

A regra simplificada que tínhamos discutido não é mais necessária. A fase passa a ser só **agregar o que já existe** para o Início:

- SKUs com **falta projetada** (estoque projetado negativo) no horizonte e a primeira semana de falta;
- SKUs que ficam **abaixo do estoque de segurança**;
- volume de **produção planejada** (o gráfico de produção da fila já soma as ordens planejadas por mês; ver `docs/spec-grafico-producao.md`).

**Mudanças no backend:** agregados novos no `GET /api/overview` a partir de `projection`, documentados em `docs/api.md`, com testes e atualização de `frontend/src/test/contract-keys.json`. Nenhum cálculo novo.

---

## Fase 3: Banco de dados, login e cadastro de SKU

**Hoje:** o Supabase guarda só o que as pessoas registram (execuções, casos, histórico e decisões). SKUs, estoque, vendas, pedidos e ordens vêm da planilha `.xlsm`, lida em modo somente leitura (`ingestion.py`). Não existe endpoint de cadastro de SKU, e a API **não tem login**.

### 3.1 Migração da planilha

1. **Tabelas:** uma por aba validada em `schemas.py` (12 abas: Produtos, Vendas_24m, Estoque_Atual, Carteira_Pedidos, Ordens_Producao, Capacidade_Semanal, Sell_In, Sell_Out, Forecast_Comercial, Calendario_Eventos, Parceiros_Canais, Lead_Times), mais Precos_Produtos, que é opcional. Entram como novas migrações em `supabase/migrations/`.
2. **Script de importação**, rodado uma vez: lê a `.xlsm` com a ingestão e as validações atuais e grava nas tabelas.
3. **Fonte configurável:** uma variável de ambiente escolhe entre planilha e banco. O backend monta os mesmos DataFrames de hoje, então cálculos, ranking e previsão não mudam. A planilha continua sendo a base dos testes.

### 3.2 Login

Antes de qualquer endpoint de cadastro, adicionar autenticação. Hoje, com `WRITE_ENABLED=true`, qualquer pessoa com o link consegue gravar.

Opções a decidir no início da fase (a escolhida foi a autenticação própria, ver [fase-3-banco-e-cadastro.md](fase-3-banco-e-cadastro.md)):

- **Autenticação própria no FastAPI:** tabela de usuários no mesmo banco, senha com hash e token JWT. Sem dependência externa.
- **Provedor externo** (por exemplo, Auth0 ou Clerk): menos código, mas um serviço a mais para configurar.

### 3.3 Cadastro de SKU

- Endpoints para criar, editar e excluir SKU, com as mesmas validações de `schemas.py`.
- **Versão dos dados:** a API calcula tudo ao iniciar e guarda em memória. Cada alteração incrementa um número de versão no banco, e a API recalcula quando ele muda. Sem isso, instâncias já em execução continuariam mostrando dados antigos.
- **Exclusão:** decidir entre exclusão lógica (marcar como inativo, preservando o histórico de casos e decisões) e exclusão definitiva. A recomendação é a **exclusão lógica**.
- Os botões de adicionar e excluir ficam na lista de SKUs da fase 1.3.

### 3.4 Hospedagem

- **Banco único no Supabase:** as tabelas da base ficam no mesmo Supabase que já guarda execuções, casos e decisões, pelo Transaction Pooler (porta 6543). Não há um segundo banco.
- **Vercel continua atendendo a API:** segue como função, agora lendo do banco. O tempo de cálculo é o mesmo de hoje, dentro do limite de 60 s.

---

## Fase 4: Refatoração visual

- Por último, depois que as telas estiverem estáveis.
- Gráficos: o atual fica como está até escolhermos referências visuais melhores.
- O protótipo já tem um sistema visual ("folha pautada", tokens em `frontend/src/styles.css`) e testes automáticos ligados a ele: `contrast.test.ts`, `legibility.test.ts` (escala de 5 tamanhos) e `clarity.test.tsx`. Qualquer mudança de estilo precisa passar nesses testes ou atualizá-los junto, com justificativa.

---

## Como vamos trabalhar

1. **Fork** do repositório na conta do Jonatas.
2. **Ambiente de teste próprio:** dois projetos Vercel (backend e frontend) e um PostgreSQL no Railway, com as migrações rodadas. Nenhuma gravação no banco do original.
3. **Uma branch e um pull request por fase.** O fork é sincronizado com o original antes de cada PR.
4. URLs e chaves do ambiente de teste ficam só em variáveis de ambiente, nunca no código.
5. Cada PR passa em `npm run check` e nos testes Python, e traz capturas de tela em 1440 px e 375 px (critério do projeto).

## Decisões para aprovação

- [ ] Fase 1: Início como painel, mantendo a resposta "o que olhar primeiro" no topo
- [ ] Fase 1: Financeiro com filtros no topo e 10 SKUs por página
- [ ] Fase 1: lista de SKUs no menu
- [ ] Fase 2: indicadores do Início a partir da projeção diária existente
- [ ] Fase 3: migrar a planilha para o banco
- [ ] Fase 3: login antes do cadastro de SKU (autenticação própria ou provedor externo)
- [ ] Fase 3: exclusão lógica de SKU
- [ ] Fase 3: tabelas da base no mesmo Supabase de hoje, API mantida na Vercel
- [ ] Fase 4: refatoração visual por último, respeitando os testes de estilo
