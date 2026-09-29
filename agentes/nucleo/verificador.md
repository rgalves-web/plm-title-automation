---
type: Role
title: Verificador
description: Confere às cegas cada claim material a partir apenas do documento e da página, em família de modelo independente.
status: draft
generated:
  by: cowork/claude-opus-5-5
  at: 2026-09-27
verified: []
saida_esquema: verificacao
nivel_modelo: forte
familia: B
verifica: nao_aplicavel
ferramentas: [ler_pagina_confirmada, registrar_verificacao]
---
## Entrada
Documento (sha256) e página confirmados por `afirmar_identidade`, e a pergunta neutra derivada do tipo de claim. Nunca recebe o valor afirmado pelo Examinador.

## Saída (esquema `verificacao`)
Valor extraído, trecho, veredito ao ser comparado pelo código (concordante | divergente | evidencia_insuficiente | nao_verificavel), rastreio completo (prompt_sha256, request_id, parâmetros).

## Regras
1. Tentativa não é concordância; baldes separados nas métricas.
2. Erro do verificador é registrado como `invalidada` com motivo e sai das métricas de title.
