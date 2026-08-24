# ORDEM — ETAPA F: CONSERTO DE CUSTO + REPLAY 2 DA JOSH B (fecha o CP3)
**Data:** 2026-08-24 · **Autor:** sessão Cowork · **Aprovada pelo operador.**
Continuação da ordem `CODE_INSTRUCTIONS_CONSERTO_DEFINITIVO.md`, mesma branch, mesmas regras
(LLM-first; caneta protege bytes; checkpoints com aceite). Motivada pelo `CONSERTO_E_STATUS.md`:
o replay 1 mediu um fluxo com corpus incompleto e dois bugs hoje consertados — o número de custo
colhido não condena o teto de $25; condena o fluxo que o replay 1 rodou. Esta etapa conserta o
fluxo e repete a prova.

**Decisões do operador registradas:** medição parcial aceita como resultado do CP3-medição;
NENHUMA exceção de teto para terminar o ship do replay 1 (estado preservado como artefato);
replay 2 com orçamento fresco de US$ 25 na unidade nova.

## F0 — Corpus completo (a causa raiz nº 1)
A premissa "TOs/JOA só existem no gabarito" é FALSA — verificado pela Cowork nos bytes:
`BKV122TX - Project Emirates\JOSH B UNIT\FILES\` contém, como arquivos do cliente, fora do kit
entregue: os zips de TO `T0140692`, `T0141177`, `T0141504`, `T0141636`, `T0141702`, `T0141729`,
o `T-O ORIG W.S. SCARBOROUGH A-669 50AC.PDF`, a DPU `K1402139` e os assignments `K1400440` e
`K1401501`, além de well files do RRC (`viewW1PdfFormAction*.pdf`, `PR*.tif`, CSVs).
- Montar `data/units/_josh_b_replay2/` por hardlink a partir da MESMA fonte do replay 1 **mais**
  esses arquivos (dedup por md5 — várias cópias `(1)`/re-downloads são byte-idênticas).
- O gabarito (`1. Landman Submitted`, `docs/JOSH_B_*`) continua fora e quarentenado, com sonda.
- Redeclarar populações em `POPULACOES.md` ANTES de rodar.

## F1 — `continuar` apresenta o delta, não o inventário
Hoje cada `continuar` recoloca ~1.100 nomes de documentos no contexto. Conserto (plumbing de
montagem de prompt, nenhuma decisão): o prompt lista APENAS (a) documentos entrados em FILES/
desde o último comando, (b) respostas novas, (c) contagens agregadas do resto
("inventário: 1.132 docs, 27 abertos, lista via list_documents"). O inventário completo continua
acessível pela ferramenta `list_documents` — quem decide abrir continua sendo o modelo.

## F2 — Triador barato e leitura em camadas (alavancas da ARQUITETURA §6, nunca implementadas)
- `MINORH_MODELO_TRIADOR` (default Haiku atual): sessão barata de inventário/classificação —
  para cada documento não aberto, rótulo + 1 linha + confiança, gravados na memória com citação.
  O Examinador (Opus) recebe o mapa do Triador e abre só o que julgar necessário. Continua IA
  decidindo — só muda o preço da cabeça em cada papel; a atribuição de papéis é configuração.
- `read_page`: texto antes de imagem SEMPRE que houver camada de texto; imagem só quando o texto
  não bastar (já é escolha do modelo — garantir que o modo texto é tentado primeiro e que o
  resultado por página entra no cache GLOBAL, `data/_page_cache`, com hit contado no log).
- Verificar e reportar o prompt caching Anthropic no laço (system + prefixo estáveis): o
  replay 1 registrou `cache_leitura` baixo demais para 44 turnos — medir hit-rate antes/depois.

## F3 — Memória em lote
Ferramenta `gravar_campos` (plural): uma chamada carrega N campos, cada um com valor + citação +
confiança próprios (mesma semântica e validação do `gravar_campo`, que permanece). Idem
`declarar_brancos` para faixas com o mesmo motivo/dono. Corta o overhead de um turno por campo.

## F4 — Replay 2 (a prova, de novo, agora com o fluxo certo)
`minorh unidade data/units/_josh_b_replay2` → papel de operador nas MESMAS regras do replay 1
(mover só o que existe no disco; responder só o registrado — os precedentes das P1–P3 do
replay 1 agora existem e devem ser aplicados via `get_precedent`, não reperguntados) →
`continuar` até convergir ou até a margem exigir parada → `ship` completo (correção +
reauditoria + regra de embarque + kit) → `compare.py`.

**Aceite do CP3 (inalterado + adições):**
- ≥90% das células do DDR à mão cobertas (escrita-com-citação OU branco-com-motivo-e-dono);
- 0 célula reprovada embarcada; auditoria 100% com `gpt-5.6-terra` (família B, sem carimbo);
- custo total do replay 2 ≤ US$ 25 — ao bater o teto, parar e reportar, nunca estourar;
- hash de fórmulas idêntico; kit completo; quarentena provada no log;
- conflito `62 vs 67` resolvido pela auditoria;
- **amostra explicada das reprovações da rodada 1 do auditor** (≥5 células): defeito real ×
  ruído de calibração, com a página citada em cada veredito;
- relatório `CONSERTO_CP3_REPORT.md` com: custo por comando, hit-rate dos caches, tokens do
  Triador × Examinador, horas de operador, e a comparação honesta replay 1 × replay 2.

## Fora desta etapa
Nada nas units entregues; nada de automação de navegador; o estado do replay 1 fica intacto
(`_josh_b_replay` + `_minorh/`) como artefato de medição — não apagar, não "terminar".
Achados que não movem o CP3 → `docs/BACKLOG.md`.
