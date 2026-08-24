---
concept: pull-list-de-cartorio-derivada-do-exhibit-a-vs-pastas-de-files
type: regra
sources:
- k1402139 (decl of pooled unit- josh b unit-unit agreement)/unit dec - josh b unit
  - rec.tif pp. 3-4 (Exhibit "A", 67 leases)
- inventário de FILES/ da unidade _josh_b_replay2 (1131 documentos)
- PEDIDOS.md de _josh_b_replay2, item PED-003 (13 leases)
links:
- cartorio-courthousedirect-arvore-e-busca
- precedente-lessor-igual-numero-de-lease-diferente-nao-funde
- dpu-eog-exhibit-a-layout-e-custo-ocr-vs-imagem
unit: ''
confidence: alta — derivada célula a célula em Josh B
---

## Como derivar a pull list de cartório no dia 1, sem abrir um único lease

O Exhibit "A" da DPU dá, por lease: `EOG LEASE NO. | LESSOR | LESSEE | DATE | VOL. | PAGE`. As pastas de FILES/ são nomeadas `NNNNNNN-NNN (lessor-oil & gas)` — o MESMO número do exhibit com hífen no lugar da barra. Logo:

**pull list = { leases do Exhibit "A" } − { pastas de FILES/ que contêm de fato o lease }**

Custa 2 leituras em `imagem` (as páginas do Exhibit "A") e ZERO leituras de lease. Feito em Josh B: 67 leases → 13 sem arquivo.

### Três armadilhas que inflam ou escondem a lista
1. **Pasta existe, lease não.** `0220604-026` só tem COA; `0220750-018` só tem 'stale check'; `0220936-006` só tem carta de extensão; `0220953-005` tem bonus/plat/ownership report mas **nenhum** `lease.tif`. Conferir o CONTEÚDO da pasta, não o nome dela.
2. **Mesmo lessor, número diferente NÃO é o mesmo lease** (`precedente-lessor-igual-numero-de-lease-diferente-nao-funde`). Josh B: Exhibit "A" traz `0221851/004 METHODIST CHILDRENS HOME`, e FILES/ tem `0221795-048 (methodist childrens home)`. São leases distintos → 0221851/004 entra na pull list. Idem `0222981/056 CHOCTAW ENERGY LP` contra as quatro pastas Choctaw existentes (0220568-014, 0221122-006, 0221123-035, 0221124-008).
3. **Pastas de FILES/ que NÃO estão no Exhibit "A"** (em Josh B: 0126714-182, 0190087-018, 0190427-098, 0220563-003, 0220568-014, 0220570-005, 0221122-006, 0221123-035, 0221795-048...) são de OUTROS units do mesmo dump multiunidade. Não são perímetro: não viram linha de DDR e não viram pedido.

### Empacotamento
Todos os itens do mesmo condado recebem `onde` idêntico (ex.: "cartório de Montague — CourthouseDirect") e viram UMA sentada. Listar diretório antes de pagar visualização é verificação gratuita (`cartorio-courthousedirect-arvore-e-busca`). Anotar no `metodo` a lista de volumes envolvidos: o operador abre a árvore uma vez por volume, não uma vez por lease.
