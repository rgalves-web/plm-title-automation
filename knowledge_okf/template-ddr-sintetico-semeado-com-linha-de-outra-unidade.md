---
concept: template-ddr-sintetico-semeado-com-linha-de-outra-unidade
type: formulario
sources:
- 'mapa do template de _cp2_sintetica: aba `Lease Review` A2 = "0888888-001", B2 =
  "Amostra De Outra Unidade"'
- 'search_corpus("0888888") em _cp2_sintetica: zero ocorrências em nomes e camada
  de texto'
- 'dpu - josh sintetico unit - rec.pdf p.2 (Exhibit "A": "Five (5) leases in total",
  todos 0999001-00x)'
links:
- precedente-divergencia-de-referencia-de-registro-resolve-se-no-cartorio
- category-to-ddr-lease-review
unit: ''
confidence: média — fato observado com certeza; o tratamento aguarda veredito do operador
  (PERGUNTAS.md P1 de _cp2_sintetica)
---

## O template do DDR chega com a linha 2 da aba `Lease Review` SEMEADA

Observado em _cp2_sintetica: `Lease Review` A2 = "0888888-001", B2 = "Amostra De Outra Unidade" — um lease que **não existe no corpus da unidade** e **não consta do Exhibit "A"** da DPU.

### Por que importa nas 300 unidades
1. **Não contar no censo.** A linha semeada não é linha do Exhibit "A"; contá-la infla o denominador e cria 7 células sem fonte possível.
2. **Não tentar sustentá-la com citação.** Não há documento — qualquer valor ali é reprovado na auditoria.
3. **Não sobrescrever em silêncio** enquanto não houver veredito: apagar conteúdo pré-carregado pelo cliente é destruição de informação; preservá-lo é publicar lease de outra unidade. As duas opções custam caro se erradas.

### Verificação barata (1 chamada)
`search_corpus("<prefixo do lease semeado>")` — se der zero ocorrências no corpus inteiro, está confirmado que é estrangeiro à unidade. Não gaste leitura de página nisso.

### Estado
Pergunta aberta ao operador em _cp2_sintetica (P1): sobrescrever (sujeira de template) × preservar na linha 2 com nota × sobrescrever com nota de rodapé. **Quando a resposta chegar, vira precedente para as 299 restantes** — quem abrir outra unidade e vir o mesmo padrão deve consultar `get_precedent` antes de reperguntar.
