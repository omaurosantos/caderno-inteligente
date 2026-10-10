# Fase 4: refatoração visual

Origem: [proposta-melhorias.md](proposta-melhorias.md), fase 4. Só estilo: nenhuma tela, rota, texto, cálculo ou estrutura de gráfico mudou. Skill de referência: [skills/frontend-design](skills/frontend-design/SKILL.md), aplicada dentro das regras de [skills/README.md](skills/README.md).

## Direção

**Ficha de ordem de produção num caderno de PCP.** O sistema "folha pautada" continua (papel, tinta, pauta, cor só para urgência, revisão, ok e ação principal), agora com um ponto de vista mais marcado:

| Elemento | Antes | Agora |
|---|---|---|
| Papel | Cinza azulado (`#f4f6f9`) | Papel offset quente (`#f2efe7`) com quadriculado de caderno a 4,5% de opacidade |
| Barra do menu | Branca, aba ativa em pílula escura | Faixa de tinta, como o cabeçalho impresso de uma ficha; a aba ativa é um recorte de papel |
| Rótulos curtos | Archivo | Martian Mono condensada em caixa alta ("carimbo"): sobrescrito, cabeçalhos de tabela, posição na fila, nome da seção |
| Seções | Título solto | Fio de tinta de 2 px abrindo cada seção |
| Primeiro da fila (Início) | Cartão com margem vermelha | Canhoto de OP: margem de urgência, picote tracejado antes da ação e furos de destaque; sombra sólida de tinta |
| Botões | Planos | Contorno de tinta com sombra sólida que "afunda" ao clicar |
| Indicadores | 18 px | 22 px condensado, fio de tinta à esquerda |
| Entrada da página | Sem movimento | Os blocos sobem em sequência (50 ms entre eles), a resposta primeiro; desligado com `prefers-reduced-motion` e na impressão |

Gráficos: ver "Gráficos com Recharts" abaixo.

## Regras mantidas

- **Cor:** a paleta nova não acrescenta cor de significado. O azul (`--pen`) continua só para ação principal e links; vermelho, âmbar e verde, só para estado. As tintas de fundo foram aquecidas para combinar com o papel.
- **Tipografia:** a escala de cinco tamanhos não mudou. A mono só aparece em rótulos curtos; nomes longos de indicadores ficam em Archivo para não quebrar nem gritar.
- **Clareza:** nenhuma mudança de estrutura; `clarity.test.tsx` passa sem alteração.

## Testes

- `contrast.test.ts`: todos os pares existentes passam com a paleta nova. Entram quatro pares para a faixa de tinta (menu, aba ativa e barra do celular).
- `legibility.test.ts` e `clarity.test.tsx`: sem alteração.
- `npm run check`: verde.

## Correção incluída

O botão do menu do celular (hambúrguer) aparecia também no desktop, porque `.icon-button { display: grid }` vinha depois de `.menu-button { display: none }` no arquivo. O seletor passou a ser `.topbar .menu-button`.

## Matriz parceiro–SKU sem rolagem lateral

A matriz (Comercial, detalhe do parceiro e aba Parceiros do SKU) passou a caber na largura da página em qualquer tela de 621 px para cima; abaixo disso já vira cartões. Tabela com colunas de largura fixa (`table-layout: fixed`), cabeçalhos que quebram linha, números centralizados e o botão de evidências numa coluna própria. Medido em 1440, 1280, 1024, 900, 840 e 768 px, com e sem evidência aberta: a tabela e a página não rolam de lado.

Na mesma medição apareceram dois estouros fora da matriz, também corrigidos:

- **Menu entre 821 e 1180 px:** os oito grupos passavam da faixa de tinta. O espaçamento diminui abaixo de 1180 px e, entre 821 e 960 px, o texto do menu usa `--text-meta`.
- **Cartão de oportunidade no celular:** com a evidência aberta, a tabela mensal alargava a página para 482 px. O cartão agora usa `minmax(0, 1fr)` e a tabela rola dentro dele.

## Planejamento: família na barra e 10 SKUs por página

- **Filtro de família** (Clássico, Escolar, Planner…) saiu de "Mais filtros" e foi para a barra principal, ao lado de Buscar e Ação. Continua na URL (`familia`) e filtra também o gráfico de produção planejada.
- **Lista paginada, 10 por página**, só com Anterior/Próxima (mesmo componente do Financeiro e da lista de SKUs). Saiu o "Ver mais" de 25 em 25. Qualquer filtro volta para a página 1; trocar de página leva ao começo da lista.
- Teste: `phase1-screens.test.tsx` ("Planejamento: família na barra e 10 SKUs por página").

## Gráficos com Recharts

`MonthlyBars` (faturamento observado × estimado no Início, no Financeiro, no detalhe do SKU e no canal; produção planejada na Fila) passou a usar Recharts, com as mesmas entradas:

- **Eixo Y com valores:** R$ compacto no faturamento (R$ 800 mil, R$ 1,6 mi), unidades no plano (15 mil). Grade em fio sólido recessivo (`--rule`).
- **Eixo X com os meses;** o ano aparece no primeiro mês e em janeiro. No celular, com muitos meses, o rótulo vai a cada 2 meses para não sobrepor.
- **Dica ao passar o mouse:** mês e valor exato de cada parte (observado/estimado, agora/depois).
- **Mantido:** barra cheia × tracejada, legenda abaixo, parte sem valor não desenhada (nunca vira zero), zero com 1 px, texto acessível. No faturamento, o texto acessível passa a trazer o valor de cada mês.
- Barras com no máximo 28 px, topo arredondado de 4 px e base reta; texto dos eixos e da dica em tokens de texto, nunca na cor da série.

Testes: `production-plan.test.tsx` passa a contar os rótulos dos dois eixos. `volume.test.tsx` deixa de contar os valores dos eixos como números de prosa (são escala, como as células de tabela, que já ficavam fora); os tetos não mudaram. O Vitest pré-empacota o Recharts (`deps.optimizer`) para o primeiro teste de cada arquivo não estourar a espera.

## Gráficos do Início

Abaixo dos indicadores, nesta ordem (o primeiro SKU da fila continua no topo):

1. **SKUs em falta por semana** (linhas retas entre as semanas, `ProjectedStockChart`): sem novas ordens × com o plano, até o fim do horizonte. Forma de ênfase: "com o plano" na cor da ação, "sem novas ordens" em grafite como contexto; valor só no fim de cada linha (o plano nunca passa da base, então os rótulos não colidem) e uma frase com o pico. Dados de `projected_stock.weekly`, agregado novo no `/api/overview` sem cálculo novo ([api.md](api.md)). Sem a série (resposta antiga ou falha), o bloco não aparece.
2. **Produção planejada por mês**: o gráfico da Fila, sem a linha de totais (já estão nos indicadores logo acima); o aviso de meses fora do gráfico continua. Carrega e falha à parte.
3. **Faturamento observado e estimado**: já estava no fim do Início; ganhou os eixos.

Paleta das linhas validada com o validador da skill de dados: separação normal e protan ok; tritan 7,8 (faixa 6–8), por isso o rótulo no fim de cada linha e a legenda como codificação secundária. O grafite reprova o piso de croma de propósito: é o cinza de contexto da forma de ênfase, não uma série categórica.

Orçamento de volume do Início (`volume-budget.json`): blocos 6 → 8 (os dois gráficos), palavras 200 → 215 e números 17 → 20 (título, legenda e a frase do pico). Os demais tetos e as demais telas não mudaram.

## Dependências novas

- `@fontsource-variable/martian-mono` (eixo de largura, OFL), importada em `frontend/src/main.tsx`.
- `recharts@3.10.1` e `react-is@18.3.1` (dependência do Recharts). Fica num arquivo separado (~356 kB, ~100 kB comprimido), baixado só nas páginas com gráfico.
