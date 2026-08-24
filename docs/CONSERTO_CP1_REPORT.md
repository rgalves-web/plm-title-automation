# CONSERTO DEFINITIVO — CHECKPOINT 1
**Data:** 2026-08-23 · **Branch:** `conserto-definitivo` (de `sistema-operavel`) · **Executor:** Code
**Ordem:** `docs/CODE_INSTRUCTIONS_CONSERTO_DEFINITIVO.md` · **Doc governante:** `docs/ARQUITETURA_GOVERNANTE.md`

Etapas A, B e C executadas. Sintética re-rodada de ponta a ponta com chamadas reais
(`unidade → continuar → ship → publicar`, em cópia sob `data/units/_cp1_sintetica/`).
**Parado aqui, aguardando aceite do operador antes da Etapa D.**

---

## 1. Suíte

- Antes de começar: **899 passed**. Ao fechar o checkpoint: **915 passed** (16 testes novos de
  plumbing em `tests/test_minorh_conserto.py` — fórmulas, hash, teto, horas, kit, publicar,
  quarentena, write-roots, trilha). Nenhum teste afirma conclusão de title.

## 2. O que foi entregue por etapa

### ETAPA A — governança e conhecimento
- **A1** CLAUDE.md reescrito pela Cowork, committed na base da branch; suíte verde sem ajuste.
- **A2** 24 fichas `regra-cliente` em `knowledge_okf/` (Manual Técnico v1.0 caps. 6–12, 15, 16, 19
  + SOP §§1–10, com fonte S##/capítulo, data e supersessão declarada onde há — ex.: estrutura de
  pastas S10 21/07 substitui S01 16/07). Tipo novo `regra-cliente` adicionado ao OKF e aos schemas
  de `write_knowledge`.
- **A2 precedentes imediatos** — 8 fichas tipo `veredito` (o que a Rodada 1 perguntou e o Manual
  responde), visíveis ao `get_precedent`: Client = BKV Corp. · Acquisition = Project Emirates ·
  Operator = EOG/per project log · Disclaimer `ABC, LLC`→`BKV Corp.` · Agreements sem JOA =
  `N/A`+dashes · Advisory-only fora de Outstanding Curative · memo-only = MISSING LEASE em
  Potential Defects · bloco MISSING DOCUMENTS no Summary.
- **A3** 4 fichas operacionais das retrospectivas: árvore CourthouseDirect/Cooke,
  RECORDING multi-condado, protocolo de captura do viewer, formato da aba Missing Files.

### ETAPA B — a caneta protegida e o teto
- **B1** `src/examinador/formulas.py` + recusa viva em `ship._dispatch_escrita`: escrita (ou
  branco) em célula de fórmula devolve ao modelo o erro nomeado
  `"<aba>!<célula> contém fórmula do template — não escreva; o valor verificado pertence à célula
  branca correspondente"`. Nunca vira branco silencioso. `write_workbook` tem a mesma proteção em
  camada defensiva (faixa de branco preserva as fórmulas por dentro; recusas listadas em
  `formulas_preservadas.json`).
- **B2** Hash ordenado de `{(aba, célula, fórmula)}` do arquivo re-lido do disco comparado ao do
  template em todo save; divergência = exceção (`FormulaAlterada`), ship aborta. O hash entra em
  `AUDITORIA.json` (seção `formulas`).
- **B3** `cmd_ship` roda inteiro dentro de `write_scope(<unit>/_minorh)` (reaproveitado de
  `src/knowledge/write_roots.py`); manifest em `_minorh/write_manifest.json` (13 escritas na
  rodada real). Escrita fora do root = exceção (testado).
- **B4** Teto duro `MINORH_TETO_UNIT_USD` (default **25**), conferido antes de cada sessão de
  modelo; orçamento de cada sessão = `min(teto_do_comando, teto_unit − acumulado)`.
- **B5** `minorh horas <h> ["nota"]` grava no estado; `minorh estado` imprime $ e horas.

### ETAPA C — ship completo
- **C1** Kit carbon-copy em `_minorh/ship/kit/1. Landman Submitted/` (7 pastas da spec +
  checklist). A **alocação** de cada arquivo é sessão do modelo (`alocar_arquivo`/`nao_alocar`,
  com fichas); a **cópia/nomeação** é plumbing com md5 round-trip (origem citada:
  `kit_builder.build_tree`). Arquivo sem decisão aparece como pendência no
  `RELATORIO_KIT.json` — nunca some. `minorh publicar` copia o kit para
  `<UNIT>/SUBMISSION PLM/`, recusa se já existir, md5 100%.
  Checklist: com template presente, o modelo projeta Yes/No/Notes da memória e as células passam
  pela mesma auditoria; sem template (caso da sintética), a ausência é **declarada** no relatório
  do kit — nunca embarca checklist em branco.
- **C2** Quarentena por **identidade**: caminho que casa com padrão de gabarito é bloqueado
  **salvo** se estiver sob um `allow_root` declarado (os write-roots da rodada). O kit do próprio
  run em `_minorh/ship/kit/1. Landman Submitted/` é legível; o kit entregue à mão segue
  bloqueado. Testado com os dois casos.
- **C3** Auditor de família B: mecanismo pronto (`OPENAI_API_KEY` no `.env`, modelo por
  `MINORH_AUDITOR_OPENAI`); **ainda não exercitado — ver §5**.
- **C4** Trilha `DD_Audit_Trail` ganhou coluna `SUPERSEDIDA POR` (`supersedida_por: <seq>`) nas
  entradas substituídas; histórico intacto.

## 3. A rodada real da sintética (números e artefatos)

Unidade: `data/units/_cp1_sintetica/` (cópia da fixture; 5 leases declaradas no Exhibit "A",
3 presentes no início, template com célula de fórmula `Ownership - Worksheet!E2 = =SUM(B2:B99)`).

| Passo | O que aconteceu | Custo real |
|---|---|---|
| `minorh unidade` | censo **60**, 57 escritos com citação, 1 branco, 7 pendentes; 3 PEDIDOS (leases −005 e certidão −003, probate Ana Souza); 1 PERGUNTA (divergência Pg. 3 vs Pg. 33) | **$1.2700** |
| operador (Code) | lease −005 gerada e movida a `FILES/` (PED-001); P1 **ficou aberta** — não há resposta registrada do operador, e resposta não se inventa | 0.2h registradas |
| `minorh continuar` | 1 documento novo processado; 64 escritos; ficha global `exhibit-a-da-dpu-vs-recital-recorded-do-lease` atualizada pelo modelo (cotejo −004 confere; 4 batem, 1 diverge) | **$0.5331** |
| teto (B4) | `MINORH_TETO_UNIT_USD=1 minorh ship` → recusa limpa: acumulado $1.80 ≥ $1, lista de pendências, instrução de exceção; **$0 gasto** (`_saida_teto.txt`) | $0 |
| 1º `minorh ship` | projeção + auditoria ok; **caiu no kit** (bug de path relativo/absoluto em `kit.montar`) — consertado; custo Opus dessa tentativa não havia sido persistido (ver §4) | **$0.8702** registrado (auditor) |
| 2º `minorh ship` | fim a fim: 59 células auditadas (**100% das vivas**, 31 de estrutura declaradas), rodada 1 reprovou 8, correção + reauditoria → **0 reprovadas, 0 células reprovadas embarcadas**; kit **9/9 md5**; hash de fórmulas **idêntico** (`a00c5258…`, `AUDITORIA.json → formulas.identico: true`) | **$2.4580** |
| `minorh publicar` | `SUBMISSION PLM/` criado, round-trip **9/9 md5**; segunda tentativa → `KitCongelado`, nada escrito | $0 |

**Acumulado da unidade: $5.1313** (bem abaixo do teto de $25). Horas do operador: 0.2h.

**Prova da recusa de fórmula com o modelo real** (`_prova_recusa_formula.json` + `.py`): a tarefa
mandou escrever `E2 = "320.00"`; a caneta devolveu o erro nomeado; o modelo **redecidiu** —
projetou o valor em célula branca (Summary!B4) e `E2` terminou intacta (`=SUM(B2:B99)`).
Custo: $0.1748. Na projeção do ship em si o modelo **não tentou** escrever na célula de fórmula:
o mapa do template agora mostra `E2 = =SUM(B2:B99)` (mudança em `template_map`, `data_only=False`)
e ele desviou sozinho — a recusa exercitada com modelo real fica provada pela sessão dirigida e
por teste de laço roteirizado.

Artefatos (fora do git — `data/units/` é ignorado por invariante): `_saida_unidade.txt`,
`_saida_continuar.txt`, `_saida_teto.txt`, `_saida_ship.txt` (a falha), `_saida_ship2.txt`,
`_saida_publicar.txt`, `_minorh/ship/{DDR.xlsx, AUDITORIA.json, MANIFESTO_LACUNAS.md,
RELATORIO_KIT.json, log_projecao.json, log_correcao.json, log_alocacao.json, ledger.json,
kit/1. Landman Submitted/**}`, `_minorh/write_manifest.json`, `SUBMISSION PLM/**`.

Kit montado (9 arquivos, alocação do modelo): 5 leases `L# - book.page - Lessor OGL.pdf`
(inclusive `L3 - 100.33` — o modelo usou o recital do instrumento, com a divergência em aberto na
pergunta P1), TO em `Title Opinions/Unit Tract 1/`, DPU `200.50.pdf` em `Unit Designation/`,
RRC csv em `Well Files/`, DDR em `PLM Report/`.

## 4. Bugs reais achados pela rodada (e consertados nesta branch)

1. **UnicodeEncodeError derrubava `continuar` depois da sessão paga** (console Windows cp1252 não
   codifica "→") e levava junto o registro do custo. Conserto: `reconfigure(errors="replace")`
   no `main`, "->" no delta, e o custo agora é registrado **antes** de qualquer print do fecho.
   O $0.5331 da execução foi recuperado do `log_continuar.json` e registrado.
2. **`kit.montar` estourava com path relativo** (`record_write` resolve absoluto; `relative_to`
   contra raiz relativa). Conserto: raiz do kit resolvida. Consequência do crash: o custo das
   sessões Opus do 1º ship não tinha sido persistido — **conserto estrutural**: cada sessão do
   ship agora salva `log_*.json` no ato (`ledger.json` idem). O que era conhecido (tokens do
   auditor, $0.8702) foi registrado como execução `ship-interrompido`; o custo Opus daquela
   tentativa não é recuperável e está **declarado** como não medido (estimativa por analogia com
   o 2º ship: ~$1.6 não contabilizados no acumulado).

## 5. O que NÃO ficou provado (pendências para o aceite)

- **Auditoria com as duas famílias**: o `.env` só tem `ANTHROPIC_API_KEY`. Sem `OPENAI_API_KEY`,
  o auditor caiu para a reserva declarada (Sonnet 5, contexto isolado) e o **carimbo de limitação
  está nos relatórios**, como manda a regra. O mecanismo OpenAI está pronto (C3); assim que o
  operador colocar a chave no `.env`, uma chamada real de auditoria na sintética fecha este item.
  **→ ação do operador: `OPENAI_API_KEY` no `.env`.**
- **Checklist projetada de verdade**: a sintética não tem template de checklist; o caminho de
  código existe e a ausência é declarada. Será exercitada no replay da Josh B (Etapa E) com o
  template real.
- A pergunta P1 (precedência Exhibit "A" × recital do lease) segue **aberta** — só o operador
  fixa esse precedente; o registro da −003 está protegido pela ficha (branco/pedido de certidão).

## 6. Custos totais do checkpoint (chamadas reais)

$1.2700 (unidade) + $0.5331 (continuar) + $0.8702 (auditor do ship interrompido) + $2.4580
(ship completo) + $0.1748 (prova dirigida da recusa) = **$5.3061 medidos** (+ ~$1.6 do 1º ship
não persistidos, declarados acima).

---

**Aguardando aceite registrado do operador para seguir à ETAPA D (kickoff dia-1: escopo cruzado,
pull list no PEDIDOS, `minorh painel`).**
