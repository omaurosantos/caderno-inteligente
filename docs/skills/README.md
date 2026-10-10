# Skills de design

Pasta para as skills usadas na refatoração visual (fase 4 da proposta de melhorias).

Cada skill fica em uma subpasta própria, com o arquivo `SKILL.md` e, se houver, suas referências:

```text
docs/skills/
  nome-da-skill/
    SKILL.md
    references/...
```

## Regras para aplicar uma skill neste projeto

- O sistema visual atual (tokens no topo de `frontend/src/styles.css`) é a base. Uma skill pode propor mudanças, mas elas entram nos tokens, não em estilos soltos por componente.
- Os testes `contrast.test.ts`, `legibility.test.ts` e `clarity.test.tsx` precisam continuar passando. Se uma mudança exigir alterar um teste, a justificativa vai no pull request.
- O critério de clareza (`docs/criterio-de-clareza.md`) continua valendo: em 5 segundos, a pessoa sabe o que fazer a seguir.
