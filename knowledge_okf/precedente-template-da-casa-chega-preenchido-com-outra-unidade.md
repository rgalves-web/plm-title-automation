---
concept: precedente-template-da-casa-chega-preenchido-com-outra-unidade
type: veredito
sources:
- PERGUNTAS.md P1 desta unidade + RESPOSTA do operador, 24/08/2026
- ficha global template-dados-de-exemplo-a-e-carroll
- censo-da-unidade _josh_b_replay
links:
- template-dados-de-exemplo-a-e-carroll
- template-ddr-sintetico-semeado-com-linha-de-outra-unidade
- censo-template-sintetico-6-abas-formula-e-linha-de-exemplo
unit: ''
confidence: alta
---

## VEREDITO (operador, 24/08/2026) — template mapeado que descreve OUTRO ativo = dados de exemplo, não troca de corpus

**Pergunta (P1, unidade `_josh_b_replay`)**: o MAPA do template descrevia duas propriedades alheias ao corpus — (a) "*** Unit 3-11", 636,13 ac, REEVES County, leases Forest Oil/Energen/Anadarko, poços 601H–656H, Wolfcamp/Bone Spring; (b) abas `Ownership - 1H (No FO Option)` e `delete - A.E. Carroll 4H`, 704,04 ac, PANOLA County, WI owner PetroQuest Energy L.L.C., Travis Peak/Bossier — enquanto o corpus (1.132 docs) era integralmente EOG / MONTAGUE / Barnett / JOSH B UNIT 220,0 ac. Zero menções a Reeves, Unit 3-11, Panola ou A.E. Carroll no corpus.

**Resposta**: opção (3). São **DADOS DE EXEMPLO do template da casa**. O template chega **preenchido com dados de OUTRA unidade** e *tudo que não for sobrescrito/limpo sai no entregável*.

### Regra operacional (vale nas 300 unidades)
1. **As COLUNAS do mapa ficam** — elas definem quantos campos cada linha exige (é o multiplicador do censo).
2. **Os DADOS de exemplo saem** — limpar no ship com `record_blank`, e o **motivo tem de dizer o que eram** ("dados de exemplo do template — Panola Co./PetroQuest, ativo alheio a esta unidade").
3. **Não concluir troca de corpus** por divergência template↔corpus. O denominador se deriva do que *o registro da unidade* declara (Exhibit "A"/"C" da DPU, poços), aplicado às colunas do template.
4. Abas prefixadas `delete - ...` são sobra de exemplo por construção: nunca entram no denominador.
5. Divergência dessas nunca é "defeito de título" — é higiene de entregável.

**Antipadrão punido**: herdar o ativo do exemplo (acreage, condado, poços, WI owner) por estar "já preenchido" — publica 636,13 ac de Reeves num relatório de 220,0 ac de Montague.
