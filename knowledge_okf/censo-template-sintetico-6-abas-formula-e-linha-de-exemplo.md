---
concept: censo-template-sintetico-6-abas-formula-e-linha-de-exemplo
type: layout
sources:
- MAPA DO TEMPLATE de _cp1_sintetica (6 abas)
- 'censo declarado em _cp1_sintetica: 60'
- runsheet-e-cadeia-suplementar-vazia-quando-nada-e-posterior-a-cert-date (aba Runsheet
  = 1 célula de nota)
links:
- ddr-template-structure-summary
- ddr-template-structure-lease-review
- ddr-template-structure-ownership-worksheet
- ddr-template-structure-runsheet
- template-dados-de-exemplo-a-e-carroll
- runsheet-e-cadeia-suplementar-vazia-quando-nada-e-posterior-a-cert-date
unit: ''
confidence: alta — conta reproduzida em duas unidades do mesmo template
---

## Como contar o denominador do template sintético de 6 abas

**Fórmula por aba = linhas que o registro declara × campos do cabeçalho.**

| Aba | Linhas vêm de | Campos/linha |
|---|---|---|
| Summary | 1 (a unidade) | 4 — só as células B2..B5; A1..A5 são rótulos fixos, **não** são campos |
| Lease Review | nº de leases do **Exhibit "A"** (inclusive os sem cópia) | 7 |
| Ownership - Worksheet | nº de tratos do **Exhibit "C"** | 4 (A-D) |
| Runsheet | instrumentos **pós cert date** (em geral 0) | 5, ou **1** se contar só a célula de nota |
| Wells | linhas de dados do CSV do RRC | 6 |
| Curative | requirements do title opinion **+ itens abertos pelo landman** | 3 |

### Três armadilhas de contagem
1. **`E2 = =SUM(B2:B99)`** na Ownership é fórmula do template, não campo de pesquisa. Não entra no denominador; se entrar, o auditor pede citação para um número que ninguém pesquisou.
2. **Curative não é só o parecer.** Itens que o landman levanta no cotejo (ex.: divergência de book/page) são linhas legítimas e **aumentam** o denominador. Declare quantas linhas contou e por quê.
3. **Runsheet:** decida a aba pelo cert date **antes** de contar (veredito P1). Diga na ficha do censo se contou 0 ou 1.

### Higiene obrigatória
`Lease Review` A2/B2 chegam com dado de **outra unidade** ("0888888-001 / Amostra De Outra Unidade"). Tem de ser sobrescrito pela primeira linha real ou apagado. Dado de unidade alheia no arquivo do cliente é pior que branco.
