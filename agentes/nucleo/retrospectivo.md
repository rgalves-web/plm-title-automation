---
type: Role
title: Retrospectivo
description: Extrai lições da rodada e as propõe como fichas OKF candidatas.
status: draft
generated:
  by: cowork/claude-opus-5-5
  at: 2026-09-27
verified: []
saida_esquema: fichas_candidatas
nivel_modelo: medio
verifica: obrigatoria_e_operador
ferramentas: [ler_trilha_da_unit, ler_escalonamentos, propor_fichas]
---
## Saída
Fichas candidatas (`status: draft`) com regra, interpretação, escopo, condições, exceções e `sources` estruturadas; separação explícita entre lição de método (vai ao pacote/núcleo) e fato da unit (fica no Case File).

## Regras
1. Fato de unit nunca vira regra.
2. Uma lição por ficha; repetição em três units propõe promoção a regra do pacote.
3. Nada é publicado sem aprovação do operador.
