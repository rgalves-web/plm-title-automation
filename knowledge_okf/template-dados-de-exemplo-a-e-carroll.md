---
concept: template-dados-de-exemplo-a-e-carroll
type: regra
sources:
- Template DDR da casa (copia entregue na unidade JOSH B UNIT, Montague County)
- 'record_blank aceito com faixa: resposta {"branco_registrado": "Ownership Report!A8:X8"}'
links:
- ddr-template-structure-summary
- ddr-template-structure-ownership-worksheet
- ddr-template-structure-lease-review
- ddr-template-structure-agreements
- ddr-template-structure-runsheet
unit: ''
confidence: alta — verificado celula a celula na unidade Josh B
---

## O template da casa chega preenchido com dados de OUTRA unidade

A copia do template entregue por unidade vem populada com dados de exemplo de **duas** unidades alheias, e nada disso e mascarado o suficiente para ser inofensivo:

- **A.E. Carroll (Panola County, TX; PetroQuest Energy, L.L.C.; Travis Peak/Bossier; 704.04 ac)** — ocupa por inteiro as abas `Ownership - 1H (No FO Option)` (A1:Z44 + C823) e `delete - A.E. Carroll 4H` (A1:Y44 + C823). O proprio nome da segunda aba diz o que fazer com ela.
- **Unidade "*** 3-11" (Reeves County, TX; Forest Oil / Energen / Anadarko / Devon; Bone Spring/Wolfcamp; 636.13 ac)** — ocupa `Summary` B2:B13, `Ownership Report` linhas 8-24 e A1/A3/A5:E5 e a celula orfa C802, `Ownership - Wells` linhas 3-8 e A9, `Lease Review` linhas 2-19 (L1-L18), `Agreements` (dois blocos de JOA inteiros, A2:B19 e A21:B39), `Unit and Pooling Agreements` A2:B8, `Runsheet` A1 e A3:K9, `PLM Title Review` B2:B13.
- `Disclaimer` (B2, B6) e generico e pode ficar.

**Regra:** tudo que nao for sobrescrito ou apagado sai no arquivo do cliente. Um valor de Reeves County num DDR de Montague e defeito grave — pior que branco.

## Truque que economiza centenas de chamadas

`record_blank` **aceita faixa** no campo `celula` (ex.: `"A8:X8"`, `"A1:Z44"`, `"G2:P68"`, `"B5:E5"`), e a resposta confirma a faixa. Isso permite limpar uma aba inteira de exemplo com 1-2 chamadas em vez de ~1000. `write_cell` NAO foi testado com faixa — nao use.

**Ordem importa:** primeiro apague a faixa da linha, depois escreva as celulas comprovaveis dentro dela.

## Armadilha de ferramenta

`write_cell` exige os 6 argumentos (`aba, celula, valor, documento, pagina, trecho, confianca`); faltando qualquer um a chamada estoura com TypeError e a celula NAO e gravada — confira o resultado de cada chamada em lote.
