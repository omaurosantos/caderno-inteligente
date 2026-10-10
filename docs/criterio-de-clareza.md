# Critério de clareza por tela

Substitui o orçamento de palavras como critério principal de "a tela está boa". O orçamento de volume (`frontend/src/test/volume-budget.json`) continua como rede de segurança contra regressão, mas não decide mais se uma tela foi aprovada.

**Critério único:** em 5 segundos, a pessoa sabe o que fazer a seguir.

Cada tela tem uma pergunta, uma resposta que aparece primeiro e uma ação principal. O que não ajuda a responder fica atrás de um clique (linha aberta, aba, bloco recolhido).

| Tela | Pergunta | Resposta que aparece primeiro | Ação principal |
|---|---|---|---|
| Início (`/`) | O que olho primeiro? | O primeiro SKU da fila e o porquê, em uma frase; o painel (indicadores, gráficos de falta semanal e de produção planejada, ruptura, oportunidades, faturamento) vem abaixo | Abrir evidências do SKU |
| Fila (`/fila`) | Qual SKU analisar, o que fazer e quanto? | Uma linha por SKU: ação e quantidade à direita, motivo abaixo, margem pela urgência | Abrir o SKU |
| SKUs (`/skus`) | Onde está o SKU que procuro? | A lista com busca e família | Abrir o SKU |
| SKU (`/skus/:sku`) | O que fazer com este SKU? | A ação sugerida e a conta da quantidade | Registrar decisão |
| Oportunidades (`/parceiros`) | Onde repor primeiro? | A lista, da menor cobertura de estoque para a maior | Ver evidências da linha |
| Parceiros (`/carteira`) | Quanto sei de cada parceiro? | A lista com cobertura de dados e sugestões | Abrir o parceiro |
| Canais diretos (`/canais`) | Quanto vendem os canais próprios? | A frase com a participação no faturamento e a lista | Abrir o canal |
| Faturamento (`/faturamento`) | Quanto se estima faturar? | O total estimado, rotulado como estimativa | Abrir o SKU |
| Validação (`/validacao`) | Quanto confiar? | O veredito em uma frase | Abrir a Auditoria |

## Como é verificado

1. **Automático** (`frontend/src/test/clarity.test.tsx`): um título de página por tela, no máximo duas ações principais, no máximo dois avisos antes da resposta, e, na fila, no máximo três selos por linha, ação e quantidade sempre presentes e a margem de urgência definida.
2. **Visual, a cada tela entregue:** screenshot em 1440 e 375 de largura. A pessoa que revisa tenta responder a pergunta da tabela acima em 5 segundos. Se não consegue, a tela não está pronta.

## Regras de cor (urgência é o único destaque)

- **Margem vermelha:** sinal principal crítico. **Margem âmbar:** sinal principal alto, exceção (dados insuficientes, capacidade a validar, confiança baixa) ou a ação pede validação. **Margem tracejada:** o SKU não tem previsão; a ausência não vira zero nem cor de estado.
- **Azul:** só a ação principal e links.
- **Selos:** cinza por padrão. Cor de selo só para urgência (vermelho), revisão e confiança baixa (âmbar), validado (verde) e recomendação/previsto (azul).
