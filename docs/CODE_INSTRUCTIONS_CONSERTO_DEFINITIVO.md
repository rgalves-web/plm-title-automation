# ORDEM DE TRABALHO — CONSERTO DEFINITIVO (ordem única, 3 checkpoints)
**Data:** 2026-08-23 · **Autor:** sessão Cowork do operador · **Aprovada pelo operador (Renato) com os parâmetros de `docs/ARQUITETURA_GOVERNANTE.md`** — leia esse doc primeiro; ele prevalece sobre qualquer outro.

**Objetivo em uma frase:** o `minorh` vira o caminho único de produção — uma unit roda do início ao fim por ele, sem retrabalho, com teto de US$ 25/unit, kit de submissão completo, auditoria em duas famílias de modelo — provado pelo replay da Josh B.

**Regras da ordem:**
- BRANCH: `conserto-definitivo`, a partir de `sistema-operavel`. Branch-only; nada na main.
- Suíte verde antes de começar e em cada checkpoint. Comportamento novo exige teste novo — de plumbing, nunca de julgamento (nenhum teste afirma conclusão de title).
- **Nenhuma decisão de title em Python.** Se um trecho escolhe, compara fato, calcula interesse ou aprova conteúdo, ele não entra. A fronteira do permitido é a §2 do doc governante (propriedades da caneta).
- Em cada CHECKPOINT: parar, escrever o relatório da etapa em `docs/CONSERTO_CP<N>_REPORT.md` com artefatos (relatório sem artefato não fecha), e **esperar aceite registrado do operador** antes de seguir.
- Os módulos aposentados (`src/knowledge/*`, `src/dd/*`) não voltam ao caminho de decisão. É permitido **extrair plumbing** deles (cópia de árvore de arquivos, leitura de estrutura de template, md5/round-trip) para funções novas sem julgamento — citando a origem no docstring.

---

## ETAPA A — Governança e conhecimento (sem código de decisão)

**A1. CLAUDE.md.** Já reescrito pela sessão Cowork (committed junto com esta ordem). Confira que a suíte não referencia invariantes removidos; ajuste testes de *documentação* se houver, nunca afrouxe gate de bytes.

**A2. Ingestão do Manual Técnico e do SOP como fichas OKF.** Fontes: `Manual_Tecnico_Sistema_DDR_Project_Emirates.pdf` (caps. 6–12, 15, 16, 19) e `docs/SOP_DDR_PROJECT_EMIRATES.md`. Uma ficha por regra em `knowledge_okf/`, com frontmatter (`type: regra-cliente`, fonte S##/cap., data, supersessão declarada quando uma regra substitui outra). Regras que a Rodada 1 perguntou e o Manual responde viram **precedente imediato**: Client = BKV Corp. · Acquisition = Project Emirates · Operator = EOG ou per project log · Disclaimer `ABC, LLC` → `BKV Corp.` · Agreements sem JOA = `N/A` + dashes · Advisory-only fora de Outstanding Curative · memo-only = MISSING LEASE em Potential Defects · bloco MISSING DOCUMENTS no Summary espelhando o Missing Files log.

**A3. Fichas operacionais das retrospectivas** (docs do projeto "josh"/"unit x", resumidas aqui — gravar como fichas):
- Cartório/CourthouseDirect: árvore `Cooke/Deeds_OPR_ByVolume/<range>/<vol>/<vol>_<pág-inicial>.tif`; listagem de diretório é verificação de existência **gratuita**; reception-only resolve por `Deeds_OPR_ByYearDocId/<ano>/`; a Schedule às vezes cita a última página (buscar arquivo com início ≤ página citada); reception numbers de Cooke reiniciam por ano — sempre com o ano.
- Coluna RECORDING da Lease & Mineral Schedule é multi-condado (strings multi-linha) — ler **county-aware**; leases podem ser dual-recorded (Cooke + Montague, caso Webb B).
- Protocolo de captura do viewer (zoom 1.736, screenshot de recalibração após mudança de modo, costura por correlação, nomeação `L## - book.page - Lessor OGL.pdf`); `find` do Chrome alucina — DOM sempre.
- Aba Missing Files do Project Log: 1 linha por documento, descrição telegráfica ≤67 chars, colunas do master vigente; reler o master imediatamente antes de escrever.

## ETAPA B — A caneta protegida e o teto (plumbing puro)

**B1. Recusa de célula de fórmula.** Em `write_workbook` (ship do minorh e examinador): antes de aplicar o ledger, indexar toda célula do template cuja `.data_type`/valor comece com `=` (ou esteja no conjunto de fórmulas do template carregado). Tentativa de escrita → erro devolvido ao modelo: `"<aba>!<célula> contém fórmula do template — não escreva; o valor verificado pertence à célula branca correspondente"`. A escrita NÃO vira branco silencioso: o modelo redecide.

**B2. Hash de fórmulas antes/depois.** No save: hash ordenado de `{(aba, célula, fórmula)}` do arquivo re-lido do disco comparado ao do template. Divergência = exceção, ship aborta. O hash entra no relatório do kit.

**B3. Write-roots no ship** (`write_roots.write_scope` reaproveitado como plumbing): o ship declara `_minorh/` como root; escrita fora = exceção.

**B4. Teto por unit.** `MINORH_TETO_UNIT_USD` (default **25**). Antes de abrir sessão de modelo, `estado.custo_acumulado()` ≥ teto → recusa com mensagem: acumulado, o que está pendente, e como o operador autoriza exceção (`MINORH_TETO_UNIT_USD=<novo> minorh continuar`). O orçamento passado ao `run_loop` de cada comando = `min(teto_do_comando, teto_unit − acumulado)`.

**B5. Horas do operador.** `minorh horas <horas> ["nota"]` grava no estado; `minorh estado` imprime $ acumulado e horas acumuladas. É a medida do negócio; plumbing puro.

## ETAPA C — Ship completo: kit, publicação, quarentena, auditor B

**C1. Kit carbon-copy no ship.** Após auditoria, montar em `_minorh/ship/kit/1. Landman Submitted/` a árvore da spec (`docs/PLM_PHASE1_SUBMISSION_SPEC.md` + SOP §10): `Leases/`, `PLM Report/DDR - <Unit Name>.xlsx`, `Seller's Files/`, `Title Documents/`, `Title Opinions/`, `Unit Designation/`, `Well Files/`, `Phase I - Checklist.xlsx`. A **alocação** de cada arquivo do corpus a uma pasta é decisão do modelo (já registrada na memória/fichas `category-to-ddr-*`); a **cópia e nomeação** é plumbing (reaproveitar de `submission_packager` só o que copia/nomeia/md5-confere). Checklist: célula alguma afirma o que a rodada não computou — os "Yes/No" e Notes são escritos pelo modelo a partir da memória, auditados como qualquer célula.
- `minorh publicar` — novo comando: copia `_minorh/ship/kit/` para `<UNIT>/SUBMISSION PLM/`, recusando se já existir (pacote entregue é congelado). Round-trip md5 100% após a cópia.

**C2. Correção da quarentena.** O padrão atual bloqueia qualquer caminho `*1. Landman Submitted*`, o que impede o ship de conferir o próprio kit. Regra nova, por identidade e não por nome: quarentenado = caminho **fora dos write-roots da rodada** que case com o padrão de gabarito (kit entregue à mão / `gabarito`). O kit dentro de `_minorh/ship/kit/` é legível pelo próprio run. Teste com os dois casos.

**C3. Auditor OpenAI exercitado.** O operador colocará `OPENAI_API_KEY` no `.env`. Com a chave presente: uma chamada real de auditoria na sintética, e o carimbo de limitação sai dos relatórios (permanece automático quando a chave faltar). Modelo do ramo B configurável por env.

**C4. Trilha com supersessão.** Entradas supersedidas da mesma célula ganham marcador (`supersedida_por: <seq>`) na trilha — cosmético conhecido do handover de 13/08; plumbing de anotação, sem apagar histórico.

### ✅ CHECKPOINT 1 — aceite antes de seguir
Suíte verde. Sintética re-rodada de ponta a ponta (`unidade → continuar → ship → publicar` em cópia): kit completo montado, hash de fórmulas idêntico provado no relatório, tentativa de escrita em célula de fórmula da fixture recusada e redecidida pelo modelo, auditoria com as duas famílias (Anthropic + OpenAI), teto por unit demonstrado (rodar com `MINORH_TETO_UNIT_USD=1` e ver a recusa limpa). Relatório em `docs/CONSERTO_CP1_REPORT.md` com custos reais.

## ETAPA D — Kickoff dia-1 (prompt e precedente, quase zero código)

**D1. Abertura com escopo cruzado e pull list.** No prompt de `cmd_unidade` (SISTEMA/task): junto com o censo, o Examinador produz (a) o cruzamento **Exhibit "A" da DPU × as duas abas do XREF × Lease & Mineral Schedule**, county-aware, com toda divergência virando pergunta ou pedido; (b) a **pull list de cartório desde o dia 1** — todo instrumento do perímetro sem arquivo em FILES/ mas com Book/Page determinístico na Schedule vira item de PEDIDOS.md com referência exata, condado, e caminho provável do viewer (ficha A3); itens agrupados por sentada de busca (invariante "one brief item per decision"). Nada disso é módulo: é instrução + fichas que o modelo consulta.

**D2. PEDIDOS.md empacotado para uma sentada.** O formato de saída agrupa: "cartório de Cooke — 21 itens (tabela vol/pg)", "Drive PLM — pastas X, Y", "RRC — API tal: W-1, G-1, P-12, plat". Meta declarada no doc governante: ≤1h do operador por unit — o PEDIDOS é o instrumento disso.

**D3. `minorh painel`** — novo comando, leitura pura: varre uma pasta-mãe (`BKV122TX - Project Emirates/`), encontra units com `_minorh/estado.json` e imprime uma linha por unit: censo · escritos · brancos · pendentes · pedidos abertos · perguntas abertas · $ · horas · último comando/data. Zero chamada de modelo.

### ✅ CHECKPOINT 2 — aceite antes de seguir
Na sintética (ou num dry-run de abertura da Josh B com teto baixo), o PEDIDOS.md da abertura já contém a pull list com referência determinística e agrupamento por sentada. `minorh painel` mostra ≥2 units. Relatório em `docs/CONSERTO_CP2_REPORT.md`.

## ETAPA E — Replay da Josh B (a prova; Code opera)

**E1. Preparação.** Corpus `data/units/_josh_b_replay` in-place; quarentena ativa sobre o gabarito (`docs/JOSH_B_*`, kit entregue à mão) — **prova de quarentena no log** (lista dos caminhos bloqueados/tentados). Template real da unit na pasta. Populações declaradas ANTES de rodar.

**E2. O laço.** `minorh unidade` → o Code faz o papel de operador SOMENTE para: mover para FILES/ o que o PEDIDOS.md pedir e já existir no disco do replay, e responder PERGUNTAS.md **com as respostas já conhecidas/registradas** (SOP, Manual, fichas; ex.: cert dates 3/3/2010 A-669 e 9/9/2010 A-319 se o operador confirmar — senão, ficam brancos declarados). Nenhuma resposta inventada: pergunta sem resposta registrada fica aberta e vira branco. → `minorh continuar` (quantas vezes preciso) → `minorh ship`.

**E3. Medição.** `compare.py` (alinhamento por identidade) contra `JOSH B UNIT/1. Landman Submitted/PLM Report/DDR - Josh B Unit.xlsx`, lido só pelo harness, fora do run.

**Aceite da prova (números fixados agora):**
- ≥ **90%** das células não vazias do DDR à mão cobertas = escritas-com-citação **ou** brancas-com-motivo-e-dono (branco declarado é cobertura; o critério é o de convergência do fluxo);
- **0** célula reprovada embarcada; auditoria de 100% em duas famílias;
- custo total do replay ≤ **US$ 25**; custo real impresso por comando e acumulado;
- hash de fórmulas idêntico; kit completo em `_minorh/ship/kit/`;
- o conflito interno `62 vs 67` (leases pooled) resolvido pela auditoria, não por conserto manual;
- prova de quarentena no relatório.

### ✅ CHECKPOINT 3 — encerramento
`docs/CONSERTO_CP3_REPORT.md`: os números acima, o log do agente (o que pediu, em que ordem, o que decidiu), divergências vs. DDR à mão amostradas e explicadas, e a lista honesta do que NÃO ficou provado (ex.: busca real de documentos — só a Fase 4 com unit nova prova). Atualizar `docs/WORKBENCH_STATUS.md` (o Code é o dono dele): baseline nova, e rebaixar a histórico o que descreve o estado pré-conserto. A sessão Cowork verifica o resultado pelos bytes antes do aceite final.

---

## Fora desta ordem (não fazer agora)
Automação de navegador para busca; conector Drive; máquina de estados de reviewer; detector de produção como módulo (o julgamento de produção é do Examinador com precedente — ficha, não código); UI do workbench para o painel; qualquer coisa nas units entregues (`SUBMISSION PLM/` congelado). Achado que não move esta ordem → linha no `docs/BACKLOG.md`.
