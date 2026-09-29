---
type: Lesson
title: Filtro de abstract do CountyRecords deve ser 'begins with'
description: O filtro 'exact' perde lançamentos indexados com sufixos de bloco e seção.
status: draft
generated:
  by: cowork/claude-opus-5-5
  at: 2026-09-28
verified: []
funcao: pesquisador
escopo: {pacote: title-texas-surface, fonte: CountyRecords}
sources:
  - resource: "projeto Claude PURPLE LAND MGMT: claude/BBT-SNN-1129_CHECKPOINT_CLAUDE_2026-09-28.md"
    id: ck1129
---
Na busca por abstract no CountyRecords, o filtro "exact" perde lançamentos codificados com sufixos, como `2808;D6;30`. Com "begins with", o A-2808 retornou 62 documentos no BBT-SNN-1129 [^ck1129].

**Regra:** buscar por abstract com "begins with" e registrar o modo do filtro na busca negativa. Busca negativa feita com "exact" não prova ausência.

[^ck1129]: checkpoint 28/09/2026, frente 1.
