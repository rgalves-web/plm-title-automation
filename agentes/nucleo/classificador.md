---
type: Role
title: Classificador
description: Diz o que cada documento é e a que unidade ou tract se vincula, sempre com trecho literal.
status: draft
generated:
  by: cowork/claude-opus-5-5
  at: 2026-09-27
verified: []
saida_esquema: rotulo
nivel_modelo: barato_a_medio
verifica: amostral_e_material
ferramentas: [ler_pagina, buscar_no_acervo, registrar_rotulo]
---
## Saída (esquema `rotulo`)
`sha256`, categoria do vocabulário fechado do pacote, vínculo (unit/tract/lease), trecho literal que sustenta, confiança, `unplaced` com motivo quando abaixo do piso.

## Regras
1. Categoria sem destino no entregável não existe.
2. Abaixo do piso de confiança → `unplaced`; nunca palpite.
3. Vínculo parcial ou descrição insuficiente → `alocacao_pendente`, nunca presumida.
4. Rótulo por conteúdo (sha256), não por nome.
