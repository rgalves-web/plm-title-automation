# Workbench — status de implementação
_Dono: o Code (ordem de 23/08). Baseline vigente abaixo; tudo sob "HISTÓRICO" descreve o estado PRÉ-CONSERTO e vale como registro, não como mapa do sistema._

## CASE FILE — fundação + VS1 · 2026-08-30 (branch `casefile-vs1`)

**Direção nova aceita pelo operador (30/08): o produto se reorganiza em torno de um Case File por Unit** (banco transacional PostgreSQL local + máquina de estados CTO: INDICADA→…→LIBERADA); o `minorh` congela como está e permanece para os replays. Implementado o **Vertical Slice 1 — Unit → Investigation Plan** em `src/casefile/` (doc: `docs/CASEFILE_VS1.md`): `indicar "Josh B Unit"` resolve por NOME; `planejar` = censo determinístico (sha256 completo, sightings, entrega quarentenada por origem, homônimos expostos) → triagem Haiku (rótulos no banco) → Examinador emite **claims com evidência obrigatória** + pesquisas → **Unit Investigation Plan versionado** aguardando `aprovar`/`rejeitar` do operador. Suíte: **966 verdes** (939 + 27 novos; 8 `@postgres` skipam sem `CASEFILE_TEST_DSN`). Smoke real Josh B (sem modelo): censo 1.034 conteúdos/1.633 caminhos em 7s, 50 homônimos com bytes distintos. Banco criado e migrado em 31/08 (role `plm`, senha só no `.env`; superusuário local segue com a senha default do instalador — trocar quando conveniente); 8 testes `@postgres` rodando de verdade. **E7 FECHADO 02/09**: `planejar` real na Josh B concluído por **$10,94 de $25** (3 quedas por 529 da API no caminho, absorvidas por relançador; triagem via Sonnet após o Haiku 529 persistente — 145 rótulos no teto de $3). Resultado: **PLANO_INVESTIGACAO_v1 proposto** com 111 claims (67 lease_in_unit = o denominador do Exhibit "A"), 11 divergências, 12 pesquisas, 4 perguntas ao operador — inclui achado material: o TO do Unit Tract 1, declarado inexistente nas rodadas manuais, ESTÁ no acervo (raiz de FILES/). Aguardando `aprovar`/`rejeitar` do operador. Achados de encanamento no BACKLOG (triagem em lotes; sessão/custo em finally).

## BASELINE — conserto definitivo · 2026-08-24 (branch `conserto-definitivo`)

**O caminho único de produção é o `minorh`** (LLM-first puro, doc governante `ARQUITETURA_GOVERNANTE.md`): `unidade` (Triador Haiku + Examinador Opus) → `continuar` (delta) → `ship` (projeção + auditoria 100% família B OpenAI + regra de embarque + kit carbon-copy) → `publicar` (congelado) · `estado`/`perguntas`/`horas`/`painel`. A esteira determinística (`src/dd`, `src/knowledge`) está congelada — histórico e fonte de plumbing.

- **Etapas A–D + pré-E entregues e aceitas** (CP1 23/08, CP2 24/08): fichas do Manual/SOP + precedentes; caneta protegida (recusa de célula de fórmula com erro nomeado, hash de fórmulas em todo save, write-roots, teto de $25/unit, horas); kit com md5 round-trip e publicar congelado; quarentena por identidade; trilha com supersessão; pull list por sentada no dia 1; `painel`; auditor B `gpt-5.6-terra` calibrado (células ordinais) com tarifa na tabela.
- **Etapa E/F (replays da Josh B)**: CP3-medição — replay 1 (fluxo antigo) 26,7% de cobertura por $19,83; replay 2 (fluxo F: corpus completo dedup, continuar em delta, Triador, texto-antes-de-imagem, memória em lote) 31,7% por $25,21 — `CONSERTO_CP3_REPORT.md`. Robustez comprada pelos replays: retry de transitórios, corte de max_tokens tratado, ledger/vereditos/logs fluem ao disco por turno.
- **Etapa G (projeção barata)**: `write_cells`/`record_blanks` em lote (~18 ações por chamada, custo por ação 6,5× menor), memória em delta na projeção (−23% de contexto/turno), **`minorh ship --continuar`** do ledger salvo, prova de quarentena gravada em `finally` com desfecho. Na Josh B: cobertura **87,3%** (750 células + 73 brancos) com **$33,73 de $35** — auditoria/correção/kit ainda não exercitados no corpus real (limite mensal da conta + margem). Números, divergências explicadas e o que falta em dinheiro: `CONSERTO_CPG_REPORT.md`.
- Suíte: **930 verdes**. Unidades sintéticas de prova em `data/units/_cp1_sintetica` e `_cp2_sintetica`; replays em `data/units/_josh_b_replay{,2}` (artefatos preservados, gitignored).

---
# HISTÓRICO (pré-conserto — não descreve o sistema vigente)
_Snapshot copiado do projeto Claude (Cowork) em 2026-08-11; mantido como registro._

## Fase 1 — Flow spine · **CONCLUÍDA 2026-07-23**
- Commit `2771c7c` em `main`. `src/flow/`: config, evidence_ledger (`derive_allowlist()` só de evidência CONFIRMADA), unit_state (case file versionado), checklist_builder, runner. Aceitação: Maxwell v13 revalidada só do state.yaml → 0 FAIL / 0 MISMATCH. Testes 494→516. ⚠ Backup de `data/units/` fora do git.

## Fase 2 — Workbench UI · **CONCLUÍDA 2026-07-23**
- Commits `762a329`+`0f0a21f`. Testes →530. FastAPI + front fiel ao protótipo; `minorh serve`. Aceitação demonstrada OPEN→SHIP com a Maxwell real. Falta o teste do Renato com as próprias mãos.

## Fase 3 — Learning loop · pendente
Classifier content-first + lessons store + verdicts reaplicados.
**2026-08-11:** superseded/expandida pela arquitetura OKF — ver `docs/OKF_SPEC.md` + `docs/OKF_MIGRATION_PLAN.md` (v1.1) + `docs/CODE_INSTRUCTIONS_OKF.md` (ordem de trabalho).

## BOWEN A UNIT — prova mecânica · **FECHADA 2026-07-28 ✓**
DDR manual (auditoria 27/07) convertido em prova mecânica pelo workbench, em 3 rodadas (commits a1e63fb, 5bc22b7, 005d71b, 14297a6, 5441b22, 553ce8c; testes 530→548):

**Resultado final (verificado externamente no Cowork, bytes frescos do disco):**
- Estrutural: **READY — 0 FAIL** (7.321/7.321 células · 4 PENDING alocação de trato · 1 DECLARED · 2 SANCTIONED, logados)
- Source-truth: **0 MISMATCH · 204 verificadas** (161 confirmed + 8 anchored + 35 semantic) · 543 unverifiable com motivo (era 13/734 antes do resolvedor)
- DDR em disco confirmado: 10 abas visíveis (aba "Ownership - 1H (No FO Option)" excluída via DECLARED EXCLUSION), S15:S38 = 24 frações `=p/q` somando exatamente 1 (era 1,00002283), datas 07/28, trilha 1.096 entradas (backfill incluso).
- Sidecar: `...\PLM Report\DDR - BOWEN A UNIT (PLM) - SOURCE_TRUTH_SPLIT.txt` (gates, DECLARED/SANCTIONED com razões, 204 por documento-fonte, pendências nomeadas).

**Mecanismos novos no sistema (permanentes, testados):** exclusão de aba declarada; sanção de finding como veredito humano persistido (anula-se se a célula mudar); stoplist de falsos-positivos com prova de segurança; resolvedor citação→arquivo (Vol/Pg → tif, título → xlsx tabular); **round-trip check** (`deliverable_io.py`: todo save relido do disco e assertado; gate sempre sobre arquivo em disco).

**Episódio de verificação (lição para ambos os lados):** a 1ª verificação externa reprovou o save por engano — a cópia staged no Cowork era stale (arquivo somente-leitura não foi substituído nas re-leituras; analisou bytes pré-rodada 2×). O Code diagnosticou corretamente com evidência (mtime/contagem de células/única cópia). Correção verificada com bytes frescos. Lições: (Cowork) apagar cópia staged antes de re-verificar e conferir tamanho em bytes contra o reportado; (sistema) o round-trip check nasceu desse falso alarme e fica — provar o disco após cada save.

**Pendências de registro (resultado, não falha):** 10 células → TO ORIGINAL 4/15/2008 A-682 (pedir ao seller — sidecar é o anexo, mensagem já redigida); 8 → memos Vol 356 Motsenbocker; 6 → memos Vol 371 Bates; 27 ORRI narrativo.

## PÓS-28/07 — movimentação do deliverable (registro de 31/07)
Os pacotes Bowen A e Maxwell A foram **reconstruídos no formato carbon-copy da Phase I** (spec PLM de 31/07) e gravados em `<UNIT>\SUBMISSION PLM\` como zips de mesma raiz (extrair juntos = 1 pasta). Verificação: round-trip 94/94 e 28/28 arquivos, md5 100%. O DDR foi **renomeado "DDR - <Unit Name>.xlsx" (conteúdo intocado)** dentro de `1. Landman Submitted\PLM Report\`. As árvores antigas (`Bowen A Unit\1. Landman Submitted` e `SUBMISSION\Maxwell A Unit\...`) ficaram autorizadas a arquivamento/apagamento manual — podem não existir mais. **Implicação para regressão:** o caminho de deliverable no `state.yaml` da Bowen pode estar stale; revalidar contra os bytes do pacote `SUBMISSION PLM` (ou atualizar o state com o novo caminho). Detalhes: `docs/`-companion `PLM_PHASE1_SUBMISSION_SPEC` no projeto Claude.

## Referências
- Protótipo aprovado (grafite quente #1F1E1D, brand v1.1): artifact "minorh-title-workbench" + docs/ do repo.
- Brand guidelines v1.1 no projeto.

---
_Daqui para baixo: seções acrescentadas **no repo** (sincronizar de volta para o Cowork)._

## PR-0 — Housekeeping · **2026-08-11** (branch `pr0-housekeeping`)
Pré-requisito das fases OKF; nada de arquitetura nova. Suíte 548 → **549**.

- **Base única:** `maxwell-lessons-hardening` já estava mergeada em `main` desde 23/07 (`f416900`); as 4 branches antigas viraram tags `archive/<nome>` e foram removidas localmente (ainda existem no remoto — deleção remota é decisão do operador). **Drift registrado:** os 13 commits pós-merge (até `553ce8c`) foram feitos direto na `main`, violando o invariante 4 (branch-only); daqui em diante, branch.
- **Remote** corrigido para `rgalves-web/plm-title-automation.git` (alcançável; `main` remoto == local).
- **`docs/` versionado** com os 8 documentos de arquitetura (specs OKF, flow v2.1, blueprint, status, Phase I, kickoff Josh B, ordem de trabalho) + protótipo HTML.
- **Tesseract unificado:** `src/flow/config.py` é o único ponto de config; `pdf_reader._configure_tesseract` delega a ele (hardcode removido — dívida do SYSTEM_ASSESSMENT §4 fechada).
- **`requirements.txt`** reescrito para o workbench real (fastapi/uvicorn/httpx; streamlit mantido como fallback congelado). **`README.md`** reescrito apontando para `./minorh serve` e `docs/`.
- **`CLAUDE.md`:** invariantes 9–15 (OKF) adicionados; ponteiro de estado passa a ser este arquivo + `docs/`; `FULL_SYSTEM_ASSESSMENT.md`/`SYSTEM_ASSESSMENT.md` viram referência histórica.
- **`as_of` nos gates:** regressão sobre deliverable já entregue fixa a data de envio, para a regra de submission-date não fabricar FAIL meses depois (teste novo). Send-time (`as_of=None`) continua exigindo data de hoje.
- **Caminho da Bowen re-apontado:** o DDR migrou para `BOWEN A UNIT\SUBMISSION PLM\Bowen A Unit\1. Landman Submitted\PLM Report\DDR - Bowen A Unit.xlsx` (movimentação de 31/07 registrada acima). Identidade **provada por round-trip** (abas, 24 frações S15:S38, datas, 1.099 entradas de trilha) antes de atualizar `state.ddr_path`.
- **Segurança:** `.env` não rastreado e ausente de todo o histórico (verificado). **Ação do operador: rotacionar a chave da API Anthropic exposta em anexos de conversa** e atualizar o `.env` local.

**Bloqueio removido no mesmo dia:** os specs 2–4 chegaram (zip do Cowork) — **PR-1 (F0 + F1-mínima) liberado**.

## ★ BASELINE OFICIAL — 2026-08-11 (substitui os números de 28/07)
Toda aceitação de PR daqui em diante compara contra **estes** valores. Medidos com
`as_of` = data de envio de cada deliverable (replay), a partir do `state.yaml`.

| | BOWEN A UNIT | MAXWELL A UNIT |
|---|---|---|
| Estrutural | **READY · 0 FAIL** · 7.339/7.339 células · 4 PENDING · 1 DECLARED · 2 SANCTIONED | **READY · 0 FAIL** · 2.271/2.271 |
| Source-truth | **0 MISMATCH** · **249 verificadas** / 498 unverifiable (747 findings) | **0 MISMATCH** · **101 verificadas** / 199 unverifiable (300 findings) |
| Trilha `DD_Audit_Trail` | **1.099** entradas | — |
| Deliverable | `BOWEN A UNIT\SUBMISSION PLM\Bowen A Unit\1. Landman Submitted\PLM Report\DDR - Bowen A Unit.xlsx` · 428.339 bytes | `MAXWELL A UNIT\…\DDR - MAXWELL A UNIT (PLM) (v13).xlsx` |

### Reconciliação 28/07 → 11/08: causa de cada delta (com evidência)

| Delta | Valor | Causa provada |
|---|---|---|
| Células | 7.321 → **7.339** (+18) | **3 linhas novas de trilha × 6 colunas populadas.** Escritas pelo **Renato em 28/07 21:41** (`CORRECTED`, capturas CourthouseDirect 7/28) limpando as notas stale de "memo não está no pacote" em Lease Review F15/F29 e Ownership Report A2. **Anterior ao repacote de 31/07** — logo o registro "conteúdo intocado" de 31/07 permanece verdadeiro (428.339 bytes antes e depois; round-trip íntegro em abas, frações S15:S38, datas e contagem de trilha). **Não é finding.** |
| Trilha | 1.096 → **1.099** (+3) | As mesmas 3 linhas. |
| Verificadas | 204 → **249** (+45, 0 perdidas) | Quatro TOs novos entraram em **FILES em 31/07 11:11–11:12** + reorganização do pacote por Unit Tract, **e** a correção do resolvedor (abaixo). Fontes das ganhas: 31× `T-O SUPP Bowen A-227 141.5 ac.pdf`, 13× `T-O FIRST SUPP … A-682`, 1× `T-O ORIG … A-227 (cert 02-04-2008)`. |

**Por que `células` e `findings` não somam entre si:** são populações diferentes. O gate estrutural conta **toda célula populada, inclusive `DD_Audit_Trail`**; o source-truth **não emite finding para célula de trilha**. Os +18 caíram inteiramente na trilha → **+0 findings**. `verificadas + unverifiable` = **747 nas duas datas** (204+543 e 249+498). Não comparar as duas contas como se fossem a mesma.

### Lição permanente — o resolvedor de citação nomeava o documento errado
Descoberto **nesta reconciliação**, não em produção. Um número de cobertura que sobe pode estar subindo por motivo errado: 8 células estavam `CONFIRMED` contra `T-O FIRST SUPP … **A-682**` quando a citação dizia `T-O SUPP Bowen **A-227** 141.5 ac (T0140210), cert. 10/18/2008`. Valores de MI (1/2, 1/4) não são distintivos, então o texto do documento errado "confirmava".

Duas causas de raiz, ambas corrigidas (`1a4d749`, `48655b4`):
1. **Citação mutilada** — `Path(citação).stem` lia a data `10/18/2008` como separadores de caminho e reduzia a citação a `"2008"`; o containment então casava por ano. Citação é prosa, não caminho.
2. **Escolha arbitrária** — o containment devolvia o primeiro hit da varredura, tornando a resolução **dependente do layout de pastas**: o repacote de 31/07 mudou silenciosamente qual documento uma citação resolvia.

Regras que ficaram: o **abstract é o discriminador** quando a citação o nomeia (ontologia OKF §2); a citação **lidera com o nome do documento** e o nome indexado mais longo com que ela começa vence; **cópias byte-a-byte são uma identidade** (`(2)` normalizado), com desempate por nome ordenado — nunca por ordem de varredura; ambiguidade real resolve para `None`. Maxwell serviu de controle: **inalterada**, provando ausência de efeito colateral.

### Artefato entregue tocado por replay — registro e cerca (11/08)
Durante a reconciliação, os replays de regressão **regravaram
`DDR - Bowen A Unit_validation.txt` dentro do pacote entregue**
(`BOWEN A UNIT\SUBMISSION PLM\…\PLM Report\`, mtime 11/08 09:32). Dois defeitos
se combinavam: o sidecar era escrito *antes* de a camada de flow aplicar as
sanções — por isso o arquivo dizia `NOT READY — 2 FAIL` enquanto o veredito
registrado era `READY / 0 FAIL` — e o replay escrevia dentro da pasta enviada.
O cabeçalho `REPLAY — as_of=2026-07-28`, criado horas antes, foi o que tornou o
problema visível.

**Decisão do Renato (11/08): não regenerar.** O arquivo **fica como está**; o
DDR nunca foi tocado (428.339 bytes, round-trip íntegro). O `SOURCE_TRUTH_SPLIT`
não está no pacote — ficou na árvore antiga removida em 31/07.

**Cerca instalada (invariante 16):** `<UNIT>\SUBMISSION PLM\` é **read-only**.
`assert_not_frozen()` guarda todo caminho de escrita do repo (save de
deliverable, sidecar de validação, staging do packager) e
`tests/test_flow_frozen_packages.py` falha se um caminho novo aparecer sem a
guarda. Bowen A e Maxwell A seguem apenas como **fixtures de regressão em modo
leitura**. Um replay (`as_of` pinado) tampouco escreve sidecar em lugar nenhum.

### Branches arquivadas — o que cada tag preserva
Tag guarda commit, não conhecimento. Duas estavam integralmente mergeadas; duas tinham trabalho próprio, resumido aqui:

| Tag `archive/…` | Status vs `main` | Conhecimento |
|---|---|---|
| `collin-corrections-lease-detail` | **0 à frente** — integralmente mergeada | nada a preservar |
| `maxwell-lessons-hardening` | **0 à frente** — mergeada em 23/07 (`f416900`) | nada a preservar |
| `maxwell-operational-minorh` | 1 commit (`0f49ad2`) | Reescrita do `app.py` Streamlit (±583 linhas): marca Minorh e **entrada por caminho de pasta** em vez de upload arquivo-a-arquivo. **Superada** pelo workbench FastAPI (`src/webapp`), que implementa a marca a partir do protótipo aprovado e opera por pasta de unidade. `app.py` segue congelado como fallback; não reintegrar. |
| `phase1-conversational-shell` | 2 commits (`81691ce`, `be0f530`) | Pacote `src/agent/` completo (~1.188 linhas + 4 arquivos de teste): `cli`, `orchestrator`, `router`, `registry`, `progress`, `workspace` e `tools/{dd_tool,mor_tool}` — a "casca conversacional" que chama os pipelines existentes como ferramentas (a direção de produto do CLAUDE.md §Product direction). **Não descartado por estar errado**, e sim porque o workbench entregou a operação por UI primeiro. Se a camada conversacional voltar à pauta, **partir deste commit**, não do zero: o padrão tool-wrapper (pipeline determinístico exposto como ferramenta, nunca reescrito) é exatamente o que o OKF pede no S4/S6. |

---

## PR-4 (F4) — classificação por conteúdo, escopo real e o FETCH BRIEF da Josh B · **2026-08-11**

O entregável deste PR não é código testado: é **um brief real e um perímetro real
da Josh B, gerados a frio**, comparáveis com o que foi feito à mão.

### Módulos novos
| Arquivo | O que faz |
|---|---|
| `src/knowledge/vision.py` | Leitura por visão, **página a página**, cache por hash da página + instrução. Recupera o que o OCR determinístico não recupera: o Exhibit "A" da DPU saiu **67/67 leases** por visão contra **13** por tesseract (DPI 350/400/500, psm 4/6 — todos falharam). |
| `src/knowledge/classifier.py` | S4 DROP no schema do flow spec §2. Filename é prior com **teto duro** (`FILENAME_ONLY_CEILING = 0.35`); vocabulário de categorias vem de L1; sem citação verbatim a confiança é capada. |
| `src/knowledge/title_opinion.py` | Cert date por **passe dirigido** (varredura OCR barata → confirmação por visão) e `coverage_delta` entre original e supplemental. |
| `src/knowledge/interest_formula.py` | Fórmula em prosa → `Fraction` exata, ou `Blocking`. Não existe terceiro ramo — em particular, **não existe fallback para a opinião anterior**. |
| `src/knowledge/dpu_reader.py` | Lê a DPU gravada: recording, data efetiva, acres, surveys, Exhibit "A", e os **tratos partidos** (`split_deed_tracts`). |
| `src/knowledge/lease_disposition.py` | A regra do supervisor como dado: memo grava os termos que declara **e** a lease vira MISSING LEASE. |
| `src/knowledge/josh_b_round.py` | A rodada: perímetro + disposições → `fetch_brief.yaml` + o markdown. |

### Aceitação (a) — re-drop frio da Bowen, nomes apagados
13 documentos renomeados para `doc_NNN.<ext>`; nenhuma pista de filename.

- **12/13 classificações corretas por conteúdo.** A única divergência é `PLAT.TIF` → `reference_workbook`: L1 **não tem categoria `plat`** (backlog #8), e o "esperado" que eu tinha escrito (`well_file`) também estava errado.
- **Cert date do original: `February 4, 2008`**, igual ao filename do pacote entregue, extraída da **p.21 de 36**: *"Our opinion covers title through February 4, 2008"*. Não está na capa e não usa a palavra "certify" — a leitura de páginas de rosto devolvia a **data da carta** (17/03/2008), que não é o piso de escopo.
- **Cert date do supplemental: BLOQUEANTE.** O documento não tem frase de certificação. O sistema devolve `cert_date_nao_localizada` **com candidato** `October 18, 2008` (p.24, *"Runsheet … covering the Land from Sovereignty to October 18, 2008"*, `requires_human_verdict: true`) — de onde vem o `10-18-2008` do filename entregue. Um clique adota; o código não adota sozinho.
- **Delta A-226 reproduzido só do conteúdo:** `ENLARGED 141.5 ac -> 262.5 ac; surveys added: A-226`.
- **Memo interno pós-cert-date → `of_record: not_recorded`** (`NOTES.TIF`, `INFO SHEET.TIF`, `VOID CHECK`), nunca elegível ao Runsheet.
- **Defeito real corrigido no caminho:** a carta de encaminhamento. A p.1 da Original Title Opinion é *"Dear Mr. Bynum: Enclosed please find our Original Title Opinion"* e classificava o documento inteiro como `correspondence`. Uma capa não nomeia o documento — `_best_answer` agora prefere a página que nomeia o instrumento.

### Aceitação (b) — rodada real da Josh B, a frio
Namespace de replay `data/units/_josh_b_replay/` (nada escrito na árvore entregue; `frozen_paths` ativo).

- **214 documentos lidos por conteúdo** (114 nas pastas de lease + 100 soltos em `FILES/`), 0 erros. Os soltos foram uma lacuna de cobertura minha, achada e fechada nesta rodada: o **4º title opinion** (`T-O ORIG W.S. SCARBOROUGH A-669 50AC.PDF`, o do Unit Tract 1) estava solto na raiz e o primeiro plano só andava pelas pastas de lease. Arquivo fora do formato esperado é exatamente o arquivo que ninguém lê.
- **Perímetro:** `A-669` e `A-319 Blocks 5 e 6`. Os blocos **não estão na DPU** — vêm da p.1 do title opinion, citados em `blocks_source`. Sem eles, um documento de A-319 Bloco 12 passa no filtro mais barato da rodada.
- **A série 0220936 sai do perímetro com prova documental de três peças**, não por suposição: Exhibit "B" p.5 (a unidade **começa dentro** do Tract 1 do Vol. 217 Pg. 491 e nomeia o Tract 2 apenas como *"occupied Southeast corner"*); o próprio deed Vol. 217 Pg. 491 (Hughes → Yentze, 04/01/1940), cujo **SECOND TRACT** é *"90 acres … part of Section No. 3422, T.E. & L.Co. Lands"* correndo *"with the S.W. Boundary line of the Wm. Scarborough Survey"* — vizinho, não dentro; e o plat do Exhibit "C" p.6, que põe **A-811 fora** do contorno.
- **Achado novo, ainda não verificado:** o Exhibit "B" p.5 parte um **segundo** deed do mesmo jeito, com a polaridade invertida — Vol. 311 Pg. 189, Tract 2 (120 ac) *dentro*, Tract 1 (35 ac) só como canto. Não está no gabarito. Entra no brief como `confirm`, não como conclusão.
- **Disposições das 67 leases:** 34 com instrumento of-record · 16 pasta sem instrumento · 9 sem pasta · 7 fora do perímetro · 1 memo-only.
- **Gate do brief: 0 problemas.** 34 itens, 30 células em branco, **nenhuma órfã** (invariante 18).

### Aceitação (c) — placar de reprodução
**Das 13 conclusões verificáveis do gabarito, o sistema reproduziu 7 sozinho e a
frio, 1 parcialmente, e 5 ainda dependem de você** — e 4 dessas 5 são de estágios
que esta rodada não tentou.

| # | Conclusão do gabarito | Resultado |
|---|---|---|
| 1 | DPU Vol. 611 Pg. 526, efetiva 08/01/2012, 220,00 ac | ✅ sozinho |
| 2 | Surveys A-669 + A-319 Blocos 5 e 6 | ✅ sozinho (os blocos citados à p.1 do TO) |
| 3 | 4 tratos, donos e acres somando 220,00 | ✅ sozinho (Exhibit "C") |
| 4 | Exhibit "A" = 67 leases com recording | ✅ sozinho (67/67 por visão; o OCR dava 13) |
| 5 | Série 0220936 fora do perímetro, zero acres | ✅ sozinho, **com a prova documental do deed Yentes** |
| 6 | Divergências DPU × XREF / Lease & Mineral Schedule | ✅ sozinho (6 ausentes do XREF, 4 do Schedule) |
| 7 | 3 title opinions cobrindo os 4 unit tracts | ✅ sozinho |
| 8 | Pastas que existem mas não têm o instrumento | ⚠️ parcial — 17 contra as 9 do gabarito, 4 em comum; a diferença é a limitação 1 abaixo |
| 9 | 5 leases memo-only → MISSING LEASE | ❌ o mecanismo funciona ponta a ponta (provado em `0220027-012`), mas **os 5 memorandos não estão em `FILES/`** — vieram do cartório, à mão |
| 10 | Probates de Ector com número de causa | ❌ S5 GAP-HUNT, fora do escopo desta rodada |
| 11 | RRC W-1 / P-12 / plat | ❌ S5 GAP-HUNT, fora do escopo desta rodada |
| 12 | Tract 1: 1/2 não arrendado, EOG WI 0,50 / NRI 0,40 | ❌ matemática de interesse, próximo PR |
| 13 | Runsheet com 23 instrumentos pós-certificação | ❌ S6 RUN, fora do escopo desta rodada |

Sobre o item 8: as 13 leases que só o sistema aponta são quase todas da série
`0220750`, e as pastas delas realmente **não têm** o instrumento — têm carta de
extensão, LAR, affidavit, recibo de aluguel e o title opinion. As leases foram
buscadas à mão durante a rodada de agosto e entraram direto no pacote (as 67
estão em `1. Landman Submitted\Leases\`), sem passar por `FILES/`. Ou seja: o
brief está mandando fazer exatamente o trabalho que foi feito à mão — o que ele
reconstruiu sozinho foi a lista de busca, não uma falha nova.

### PR-4b — as cinco correções depois da leitura do primeiro brief (11/08)

O primeiro brief passou no gate e mesmo assim estava errado em cinco pontos. Nenhum
deles era um bug de execução; todos eram uma regra faltando.

1. **A regra da capa de encaminhamento não tinha generalizado.** Ela foi corrigida
   nos title opinions e em mais nada — isso é um conserto, não uma regra. Reabri os
   13 arquivos `<LESSOR> LSE <número>.PDF` e li **todas** as páginas: **0 são lease,
   13 são carta** (mala certificada da EOG ao lessor, em papel timbrado, 1–2 páginas,
   sem instrumento atrás). A classificação estava certa; a regra é que estava
   estreita. Agora: a arbitragem vale para **todo tipo**, roda no caminho de texto
   além do de visão, e **continua lendo** (até `TRANSMITTAL_SCAN_PAGES = 6`) enquanto
   as páginas lidas forem só capa — janela de 2 páginas não bastava. Fixture
   `transmittal_cover_is_not_the_document` com um caso por tipo, mais o
   contra-exemplo que impede a regra de **inventar** um instrumento onde só há carta.
2. **Ausência nunca se infere de `unplaced`.** `unplaced` é "não sei o que é", e
   ignorância não é ausência: o arquivo não identificado pode **ser** o documento.
   Disposição nova `unidentified_documents_in_folder` → item de **veredito**
   (`action: verdict`, "diga o que é este arquivo"), nunca item de busca. E é
   **gate**: `validate_item` reprova qualquer `fetch`/`request` cuja evidência de
   ausência mencione `unplaced`. Mandar alguém ao cartório atrás de um documento que
   já está no disco é o erro mais caro que este brief sabe cometer.
3. **`blocking` agora deriva do que a célula alimenta** (`BLOCKING_DESTINATIONS`),
   não de "destrava uma célula" — leitura pela qual 25 de 34 itens eram blocking e a
   flag não dizia nada. Lease Review **não** bloqueia certificação (a PLM roda o
   runsheet antes, e branco declarado embarca); perímetro e WI/NRI verificado
   bloqueiam. Resultado: **2 itens blocking**, ambos de escopo.
4. **Um item por decisão.** As 7 leases da série 0220936 = **um** confirm com a prova
   escrita **uma vez**. Os lookups de cartório = **um** item com a tabela vol/página
   dentro. A seção de prioridade virou índice de ids, não segunda cópia dos itens.
   O detalhe por arquivo do `already_searched` ficou no `fetch_brief.yaml` (que é o
   que o `carry_forward` lê). **De 34 itens / 466 linhas para 5 itens / 128 linhas.**
5. **`0221055-002` (Marlee Stewart) — verificada, não presumida.** O gabarito a
   marca como "duas cópias ilegíveis (OCR falhou)". Li as duas por visão:
   `LEASE.TIF` e `LEASE - REC.TIF`, ambas `lease_ogl` a 0.98, mesma citação verbatim
   (*"PAID-UP OIL, GAS AND MINERAL LEASE … 25th day of July, 2008, between Marlee
   McConnell Stew…"*), of-record, e **royalty = 1/5** — exatamente o campo que o OCR
   não deu na rodada à mão. Ela **não é ilegível para este sistema**, então não gera
   item; o mecanismo existe assim mesmo (`instrument_illegible` → `action: rescan`,
   "abra o arquivo, não vá ao cartório"), porque ilegível é disposição própria e não
   silêncio.

Efeito colateral honesto de (2): re-lidos com a varredura profunda, 5 dos 6
`unplaced` viraram `correspondence`; sobrou **um** (`PLAT.PDF` em `0220953-005`,
confiança 0.4 — a lacuna de categoria `plat` do backlog #8). Por causa dele aquela
lease saiu da lista de busca e entrou na fila de veredito, que é o comportamento
correto.

### Limitações honestas desta rodada
1. **Disposição é por documento, não por campo** (backlog #9). O gabarito distingue "a lease está aqui mas falta o royalty" (`0220953-008/-010/-011`) e "as duas cópias estão ilegíveis" (`0221055-002`); o sistema diz `instrument_of_record` e para aí.
2. **Tiering declarado:** pastas com um arquivo que o classificador confirma como a lease receberam **uma** leitura; pastas sem candidato óbvio receberam **todas**. Isso custou o inventário completo de title opinions dentro das pastas já resolvidas.
3. **Curativa (probates de Ector) e RRC não foram tentados** nesta rodada — são S5 GAP-HUNT, não S2 SCOPE.

---

## PR-5 — fonte que prova o termo, e o gap-hunter (S5) · **2026-08-11**

### Regra 1 — `dual_disposition` generalizada

A regra do memorando nunca foi uma regra sobre memorandos. O que faz um documento
ser fonte é **estar de registro e declarar o termo**. Agora isso é dado em L1
(`proves_terms`), declarado em três categorias:

| categoria | prova os termos de | casa por | também é defeito |
|---|---|---|---|
| `lease_ogl` | si mesma | recording, nº EOG | não |
| `lease_memorandum` | a lease que memorializa | recording, nº EOG | **sim** (MISSING LEASE) |
| `title_opinion` | as leases que o LEASE SUMMARY recita | **recording apenas** | não |

Duas disciplinas seguram a regra: casa-se por **identidade, nunca por nome** (o
mesmo lessor tem lease em várias unidades, e um match por nome importa os termos
da unidade errada com toda a convicção do mundo); e **silêncio não é valor** — o
termo que a fonte não declara fica branco com motivo do vocabulário.

Um teste que falhou e valeu o PR: `lease_ogl` **não estava declarada** como fonte,
então o recital do examinador vencia o próprio instrumento. Óbvio demais para ter
sido escrito — e por isso não era aplicado.

**Efeito medido na Josh B:**

| | antes | depois |
|---|---|---|
| tabela de `fetch` (viagem ao cartório) | **24** | **10** |
| entrega do Seller (`request`, não-blocking) | 0 | **14** |
| células de Lease Review preenchidas **com citação de página** que antes eram branco | 0 | **62** |

As 14 não são as 13 "que têm o TO na pasta": são as que o **schedule do TO
recita pelo recording**, e duas delas (`0220604-005`, `0220604-013`) nem têm pasta
em `FILES/`. É a diferença entre casar por identidade e casar por proximidade.

O TO declara a Lease 36 (Nan Kirkendahl) como **Unrecorded**, então ela não casa
por recording e continua em `fetch` — conservador e correto: o Exhibit "A" lhe dá
Vol. 610 Pg. 245 porque foi gravada depois.

### Regra 2 — o gap-hunter

`src/knowledge/gap_hunter.py`, com as cinco perguntas de examinador: citado mas
ausente · lease posterior a toda cert date · requirement vivo × satisfeito ·
conflito entre fontes · disciplina de INFERENCE (a conclusão marcada nomeia o que
a refutaria, e **é retirada** se não sobreviver — nunca suavizada).

**Aceitação contra o gabarito — os três alvos, todos emitidos sozinhos:**

1. **Os 5 grupos de requirement do TO A-319:** Req 4 (Kramer/Wichita) · Req 6
   (herdeiros de Leonard Lewis Walker, III) · Req 10 (quitclaims James W. Farrell
   Trust) · Req 15 (Name Assumptions — identidade de lessor) · Req 17 (affidavit
   of nonproduction).
2. **A curativa do Tract 1** (TO A-669 50AC): Req 1 probate Julia Marlee Stewart ·
   Req 2 identidade Marlee McConnell Stewart · Req 3 nonproduction.
3. **O teste difícil — os três probates de ECTOR.** O item sai como
   `[A-669 Tract 1] Req 4 — probate: Unrecorded Probates`, **county = Ector**,
   causas **1449, 3734-A, 16915-02**, com o texto: *"This is NOT Montague County:
   the land is in Montague; these records are of Ector because that is where the
   parties were, and asking Montague for them comes back empty."* O condado vem do
   texto do próprio requirement, não do condado da terra — que é exatamente a
   diferença entre ler como examinador e casar strings.

`blocking` da curativa deriva do que a exigência **decide**: probate, quitclaim,
identidade, nonproduction e ratificação mexem em quem é dono e alimentam
`ownership_report` (bloqueiam); runsheet, imposto, posse e consentimento são
procedimentais (não bloqueiam).

### Brief resultante

**11 itens · 4 blocking** (perímetro 0220936 · split deed Vol. 311 Pg. 189 ·
curativa de propriedade local · probates de Ector) · 94 células em branco, nenhuma
órfã · gate com 0 problemas.

O gate reprovou meus próprios itens de curativa três vezes antes de fechar: sem
canal, sem custo, e propondo busca em portal para um `request`. O custo não está
em nenhum documento que temos, e inventar "$5" a partir do gabarito seria importar
fato numa réplica fria — então o contrato ganhou uma terceira forma aceita,
*"cost unknown — ask before ordering"*. Silêncio continua reprovando.

### Placar de reprodução — atualizado

**Das 13 conclusões verificáveis do gabarito, o sistema agora emite 8 sozinho
(era 7), 2 parcialmente (era 1), e 3 ainda dependem de você (era 5).**

| # | Conclusão | PR-4 | PR-5 |
|---|---|---|---|
| 1–7 | DPU, surveys, tratos, Exhibit "A", série 0220936 com prova, divergências, title opinions | ✅ | ✅ |
| 8 | Pastas sem o instrumento | ⚠️ | ⚠️ — agora 10 fetch + 14 entrega do Seller; 3 das 9 do gabarito em comum. As 6 restantes são gaps **de campo**, não de documento (backlog #9) |
| 9 | 5 leases memo-only → MISSING LEASE | ❌ | ⚠️ — o mecanismo generalizou e produz MISSING LEASE para 15 leases com os termos citados; os 5 memorandos específicos continuam fora do corpus |
| 10 | Probates de Ector com número de causa | ❌ | **✅ sozinho, com os 3 números e o condado certo** |
| 11 | RRC W-1 / P-12 / plat | ❌ | ❌ — não tentado |
| 12 | Tract 1: 1/2 não arrendado, EOG WI 0,50 / NRI 0,40 | ❌ | ⚠️ — a **curativa** que determina esses números é emitida; a aritmética não foi tentada |
| 13 | Runsheet com 23 instrumentos pós-certificação | ❌ | ❌ — não tentado |

---

## PR-6 — o kit, a frio · **2026-08-11**

### 1. A verificação grátis: célula a célula contra o DDR feito à mão

As duas leituras vêm do **mesmo** title opinion. É a evidência de corretude mais
forte que o projeto produziu até aqui.

| | |
|---|---|
| **iguais** | **117** |
| divergentes | **3** |
| só-no-sistema | **0** |
| só-à-mão | 62 |

**Zero cells em que o sistema inventou um valor que a mão não tem.** As 3
divergências restantes são de estilo, ambas as leituras fiéis à sua fonte: o
lessor pelo instrumento (*"The Marvin Brashear Trust and The Bess Brashear
Trust, by Bobbie Brashear, Jr., as Trustee"*) contra a abreviação do Exhibit "A"
(*"Marvin Brashear & B Brashear Tst"*); o termo literal contra o termo mais a
conclusão sobre a opção de extensão; e um nome de lessor enriquecido à mão com o
nome alternativo.

A primeira passada tinha **6 divergências e 44 iguais**. O que as fechou:

- **Frame local.** `LAND: Tract 2.` é a numeração de tratos **da opinião**, não a
  do unit. Transcrever aquilo para a coluna LEGAL DESCRIPTION é verbatim-correto
  e errado onde cai. Virou `frame_local` em L1: o valor é guardado como
  **ponteiro** e nunca vira célula.
- **Ponteiro não é valor.** *"SEE EXHIBIT 'A' ATTACHED HERETO FOR DESCRIPTION OF
  LANDS COVERED"* é uma remissão. Estava sendo escrita como se fosse a descrição.
- **Incorporação por referência.** A opinião diz, em palavras: *"Leases 26 - 32
  use the same form as Lease 10, and only those provisions differing from Lease
  10 are included below"*, e a 10 herda da 9. Não é inferência convidada por um
  campo vazio — é o documento declarando que as provisões não repetidas **são**
  as da lease base. A herança segue a cadeia (26 → 10 → 9), só termos de FORMA
  (identidade nunca herda, senão duas leases se fundem), e a citação carrega as
  **duas** páginas mais a frase que autoriza.
- **Exhibit "A" como fonte.** A DPU é instrumento gravado que imprime lessor,
  lessee, data e recording de cada lease. Passou a ser fonte desses quatro.

### 2. Disposição em nível de campo (backlog #9 — fechado)

`route()` separa o que o **documento** é do que as **células** sabem: uma lease
pode ter os termos de registro e não ter instrumento nenhum. E `_blanks()` passou
a reportar por campo em toda disposição, inclusive nas leases cujo instrumento
**está** presente — o que expôs 315 células órfãs que antes não existiam porque
ninguém perguntava.

Elas ganharam dono próprio: `EXTRACT-FIELDS`, ação nova `extract`. É a única
ação do brief cujo trabalho é **do sistema, não seu** — "o documento está aqui,
eu não li estes campos dele". Antes disso, uma royalty faltando numa lease
presente e uma lease inteira faltando contavam igual.

### 3. S6 → S7 → S8 a frio

| | |
|---|---|
| células com valor **e citação** | **279** |
| células em branco **com motivo do vocabulário** | **261** |
| células órfãs | **0** |
| **convergiu** | **sim** |

A rodada declara sozinha que acabou — não por estar cheia, mas porque toda
célula está evidenciada ou declarada. Gate estrutural e brief: 0 problemas.

Três defeitos meus que o próprio pipeline pegou no caminho: o kit colocando
**capturas de tela** como title opinions e well files (uma foto de um documento
não é o documento — regra nova, e nenhuma captura embarca); o mesmo TO copiado
23 vezes por estar arquivado em toda pasta de lease (dedupe por hash: 23 → 3); e
uma regra de shippability cega demais que zerou Seller Files, porque eu tinha
escrito "só embarca o que é de registro" quando um ownership report do seller
nunca é gravado e é justamente um arquivo do seller.

### 4. Kit gerado × kit à mão

| pasta | gerado a frio | gabarito 06/08 | pasta hoje |
|---|---|---|---|
| Leases | 35 | 53 | 67 |
| PLM Report | 1 | 1 | 1 |
| Seller Files | 1 | 6 | 6 |
| Title Documents | 1 | 19 | 32 |
| Title Opinions | 3 | 4 | 4 |
| Unit Designations | 1 | 1 | 1 |
| Well Files | 0 | 1 | 4 |
| Phase I - Checklist | 0 | 1 | 1 |
| **TOTAL** | **42** | **86** | **116** |

**42 de 86.** O que falta não está escondido: as 26 lacunas estão declaradas no
`SUBMISSION_MANIFEST.txt`, cada uma com o motivo e, onde há, os termos já
provados com citação. Os Title Documents são a maior distância — 1 contra 19 —
porque o Runsheet (S6 completo) não foi construído, e é dele que sai a lista dos
documentos de título. Well Files continua vazio porque o RRC nunca foi buscado.

### 5. Placar final

**Das 13 conclusões verificáveis do gabarito: 8 sozinho, 3 parciais, 2 abertas.**

| # | Conclusão | PR-5 | PR-6 |
|---|---|---|---|
| 1–7 | DPU, surveys, tratos, Exhibit "A", série 0220936, divergências, TOs | ✅ | ✅ |
| 8 | Pastas sem o instrumento | ⚠️ | ⚠️ — agora é por **campo**: 279 células com citação, 261 declaradas, 0 órfãs |
| 9 | 5 leases memo-only | ⚠️ | ⚠️ — mecanismo geral; os 5 memorandos seguem fora do corpus |
| 10 | Probates de Ector com causa | ✅ | ✅ |
| 11 | RRC W-1 / P-12 / plat | ❌ | ❌ — não tentado |
| 12 | Tract 1: EOG WI 0,50 / NRI 0,40 | ⚠️ | ⚠️ — curativa emitida; aritmética não tentada |
| 13 | Runsheet com 23 instrumentos | ❌ | ❌ — não tentado; é o que trava Title Documents |

---

## PR-7 — a última milha · **2026-08-11** · **objetivo NÃO atingido**

O kit ainda não é submissível. O que segue é o estado medido, não o pretendido.

### 1. Dívida de `extract` — meta 87,4%, entregue **65,7%**

| | |
|---|---|
| Lease Review preenchida com citação | **355 / 540 = 65,7%** (era 51,7%) |
| linhas COM instrumento no corpus (35) | 236/315 = **74,9%** |
| linhas SEM instrumento no corpus (25) | 119/225 = **52,9%** |
| células órfãs | **0** |

Duas passadas de visão sobre os 35 instrumentos que temos (páginas 1–2, depois
3–6 para as cláusulas) recuperaram lessor/lessee/data/descrição em 38, royalty em
36, shut-in em 34 — mas depth limitation em apenas 15.

Três correções de regra saíram daí, e a primeira é a que mais valia:

- **Ser de registro é propriedade do INSTRUMENTO, não da página escaneada.** Eu
  exigia `of_record: recorded` do documento; a página 1 de uma lease raramente
  mostra o carimbo, então 34 instrumentos liam `unknown` e não provavam nada. Um
  instrumento cujo registro o Exhibit "A" declara **é** de registro. `not_recorded`
  continua duro — é o filtro que manteve uma carta fora de um Runsheet entregue.
- **Identidade pela pasta.** Um documento que o ledger arquivou sob a lease não
  precisa casar recording com ela; exigir isso jogava fora as palavras do próprio
  instrumento em favor do recital do examinador.
- **Herança de forma e cláusulas** do schedule do TO (segunda leitura, pedindo o
  que a primeira não perguntou).

**Por que 87,4% não é alcançável deste corpus:** 25 das 60 linhas não têm
instrumento nenhum. Para elas o Exhibit "A" dá 4 campos e o TO dá mais alguns; o
resto está genuinamente ausente. O DDR à mão chegou a 100% porque o operador
tinha as 67 leases na mão — 32 a mais que eu. O teto estrutural aqui é ~77%, e
mesmo ele não foi atingido: as linhas com instrumento estão em 74,9%, e a
diferença é dívida de leitura ainda em aberto, não ausência de documento.

### 2. Runsheet — **4 entradas contra 24 do gabarito**, e a base é bloqueante

`src/knowledge/runsheet.py` + `knowledge/rules/runsheet_style.yaml` existem e
funcionam: três colunas de data separadas, entrada numa sentença, filtro de
escopo com motivo do vocabulário para cada exclusão (210 excluídos, contados).

Mas o piso de escopo **não foi resolvido**. `find_cert_date` devolve BLOQUEANTE
para as três opiniões — nenhuma imprime frase de certificação. Os candidatos
(9/4/2010 e 21/5/2010) **não batem** com as datas que o runsheet à mão declara
(A-669 de 3/3/2010, A-319 de 9/9/2010), e a base à mão é **por trato**, coisa que
o sistema ainda não modela. Construí com o candidato mais antigo e **declarei a
base na própria célula A3**, como o runsheet à mão declara a dele.

Um defeito de correção apareceu na inspeção e foi corrigido: o runsheet não
aplicava o filtro de perímetro, e duas entradas eram da série 0220936, que
contribui zero acres.

O que sobrou eu listo no arquivo da aba: grantee poluído com o recital das
partes, vol/pg capturado da descrição da terra em vez do registro, e nenhuma data
de registro (as cópias não mostram o carimbo). **Nenhuma dessas entradas deve ir
à PLM sem verdito.**

### 3. Phase I - Checklist — **9 Yes / 5 No**, contra 14/1 do gabarito

Preenchida e no kit, com Notes declarando cada pendência. Os 5 "No" são honestos:
Well Files (sem RRC), Ownership - Worksheet, Ownership - Wells, Agreements e PLM
Title Review — abas que esta rodada não populou.

### 4. Kit: **43 de 86**

Leases 35/53 · Title Documents 1/19 · Seller Files 1/6 · Title Opinions 3/4 ·
Unit Designations 1/1 · Well Files 0/1 · Checklist 1/1. As 26 lacunas estão
declaradas no manifesto, cada uma numa das duas caixas exigidas.

### O que falta para submissível

1. Cert dates por trato, confirmadas — destrava o Runsheet, que destrava Title Documents.
2. Os instrumentos pós-certificação de 2010–2012 (as 15 OGLs da lista à mão) não estão no corpus.
3. Ownership - Worksheet e Ownership - Wells: a aritmética de interesse, nunca tentada.
4. RRC para Well Files.


---

## PR-8 — os gates que deviam existir antes de qualquer escrita · **2026-08-11**

Nenhuma capacidade nova. O DDR que entreguei no PR-7 era o template com a Lease
Review escrita por cima: **247 células com a unidade de amostra** (*** Energy,
Reeves, Forest Oil, 636.13, Section **), a aba `delete - A.E. Carroll 4H`,
`Ownership Report` onde a instrução da PLM diz `Ownership - Worksheet`, e
**nenhuma DD_Audit_Trail**. O pipeline antigo já tinha as defesas
(`PLACEHOLDER_MARKERS`, `_drop_delete_tab`, `_scrub_placeholders`,
`check_sheet_set`) — eu simplesmente não as chamei.

| gate | estado |
|---|---|
| **1. Saída limpa**, sobre bytes relidos do disco | **CLEAN** · 3.819 células · 0 achados |
| **2. Asserção da checklist** | **CLEAN** — pegou "62", "67", "94%" herdados do Notes da checklist à mão |
| **3. Quarentena do gabarito** | **0 tentativas** de ler `docs/JOSH_B_*` durante a rodada |
| **4. DD_Audit_Trail no artefato** | **581 entradas** (célula, valor, citação, motivo do branco) |

### Três defeitos reais encontrados no caminho

- **`ws.cell(..., value=None)` não limpa nada.** O openpyxl ignora um `value`
  None, então a forma que eu escrevi lia como "limpe esta célula" e limpava
  zero. Era por isso que o Notes da checklist à mão sobrevivia a duas tentativas
  de limpeza.
- **`Volume 199, Page 336` repetido em cinco linhas** da coluna RECORDING: a
  extração capturou a referência de deed da *descrição da terra* como registro
  da lease. Corrigido pela ontologia — o Exhibit "A" é a **autoridade** sobre o
  registro (`categories.yaml dpu.authority`), e uma extração que discorda dele
  não é adotada; a divergência vai para a trilha. Valor errado é pior que branco.
- **`.pyc` obsoleto mais novo que o fonte** mascarou a correção por duas
  rodadas. Cache limpo.

### O que este PR NÃO fez

O item 5 — escrever Summary com a curativa, Ownership - Worksheet e Wells com a
aritmética, PLM Title Review e Agreements — **não foi feito**. Você disse "só
depois", e os quatro gates consumiram o PR. As abas seguem vazias e a checklist
diz "No" nelas, com a pendência declarada em Notes.

---

## PR-9 — contenção de escrita + gate de WHITELIST de proveniência · **2026-08-12**

Ordem executada na íntegra (`docs/CODE_INSTRUCTIONS_PR9_WHITELIST.md`). Branch
`pr9-whitelist-provenance`; rede `pre-pr9-cleanup` (tag).

### Item 0 — contenção e limpeza

- **Invariante 26 (write-roots):** `write_roots.write_scope` — a rodada declara
  os roots antes de escrever; escrita fora = exceção; `write_manifest.json`
  emitido ao final, inclusive em falha. Gancho em `assert_not_frozen`, o
  chokepoint que todo caminho de escrita já consulta.
- **Rodada promovida para o repo:** o script de kit vivia em `/tmp` — escrita
  não declarada por definição. Agora `src/knowledge/kit_round.py`.
- **Limpeza:** scratch pontual → `data/_attic/2026-08-12/` (fora do git);
  estado de rodada regenerável → `_josh_b_replay/_work/` (descartável por
  inteiro); `state.v*.yaml` (26 Bowen + 14 Maxwell) → `<UNIT>/versions/` com
  numeração sobrevivendo à migração (teste).
- **`corpus/` apagado** (1.105 arquivos duplicados de cliente). O replay lê os
  zips originais **in-place** via `corpus_reader.CorpusIndex` (read-only
  enforçado; `materialise` recusa destino fora de `_work/`). Índice validado
  contra 100% dos registros de classificação antes da deleção.
- **Aceitação 0.3:** replay novo ponta a ponta com 46 escritas, todas dentro do
  root declarado; quarentena 0; `git status` sem strays; suíte verde.

### O defeito, medido — e a fixture congelada (item 1)

A fixture `tests/fixtures/ddr_josh_b_pr8_provenance_defect.xlsx` (bytes fora do
git, claim com sha256) é o artefato PR-8 intocado. O gate novo reporta:
**FAIL — 525 órfãs de 1.094 células não vazias**, citando "Bone Spring" e
"Ma Chona Adaya". As ~759 do Cowork = 525 órfãs + ~234 células de estrutura que
a baseline agora legitima com valor esperado. Entre as órfãs estão o
`Date Submitted` do PR-8 (escrito sem trilha) e os quatro `--` do Summary —
asserções de ausência que a rodada contradizia.

### Itens 2–4 — baseline, esqueleto, whitelist

- **Baseline** (`knowledge/templates/ddr_template_structure.yaml`): 144 células
  de estrutura, 942 de amostra, contagens por aba anexadas. O validador do
  item 2 pegou meu primeiro erro de regra: `Agreements!A22` ("*** 3-11 A
  601H…") ia ser abençoado como estrutura — a regra por coordenada virou regra
  por princípio (rótulo termina em dois-pontos; título de bloco é dado).
- **Esqueleto** (`build_skeleton`): o artefato NASCE template-menos-amostra.
  Strip na origem; o scrub por marcador continua como defesa, nunca critério.
- **Whitelist** (`assert_provenance`, dentro de `write_ddr`, sobre bytes
  relidos): célula não vazia = estrutura declarada com valor esperado, ou valor
  com entrada na `DD_Audit_Trail`. Duas escritas sem trilha apareceram na hora
  (id da lease, Date Submitted) e ganharam trilha. Reconstruído: **CLEAN,
  0 órfãs de 598**.

### Itens 5–7

- **Checklist derivada dos bytes** (`tabs_populated` +
  `check_checklist_vs_artifact`): "populated" = ≥1 célula não-estrutura com
  trilha na aba; Summary exige os 8 campos nomeados. Resultado honesto:
  **7 Yes / 7 No** — o Summary caiu para "No" porque só Date Submitted está
  preenchido, exatamente a contradição que o Cowork apontou.
- **Ausência derivada** (`AbsenceNotDerived`): escrever "--"/"None" exige
  citação `derived: computed empty set`. Estado desconhecido nunca vira
  conclusão negativa.
- **Runsheet 8–9 e órfãs da Lease Review:** eram linhas/colunas de amostra do
  template sem origem documental na Josh B — **removidas** pelo strip na
  origem. Verificado no reconstruído: Runsheet linhas 4–7 apenas; B/M/N/O/P da
  Lease Review vazias.

### Invariantes e regressão

CLAUDE.md ganha os invariantes **25 (whitelist de proveniência + ausência
derivada)** e **26 (write-roots)**; o contrato do brief permanece no 24.
Suíte: **806 verdes** (24 novos). Bowen/Maxwell em leitura, inalteradas.

---

## PR-10 — as abas que nunca foram escritas, com dados reais · **2026-08-12**

Branch `pr10-real-tabs`. Gate whitelist ativo o tempo todo; quarentena do
gabarito ativa (0 tentativas de leitura durante a rodada). Regra do PR: só se
escreve o que a rodada prova com citação.

### Métrica do artefato

| | PR-9 | PR-10 |
|---|---|---|
| células com valor + trilha | 393 | **1.186** |
| brancos declarados | 188 | 393 |
| órfãs | 0 | **0** |
| checklist derivada dos bytes | 7 Yes / 7 No | **10 Yes / 4 No** |

### Item 1 — Summary

`knowledge/project/engagement.yaml`: cada campo com o **documento** que o
declara. Operator/Seller vêm do CSV do RRC no corpus e da própria DPU; State e
Counties da DPU. `dsu_str` fica **nulo** — nenhum documento do corpus o declara,
então a célula sai branca com motivo. O linter pegou minha primeira versão
citando `Vol. 611, Pg. 526` dentro de `knowledge/` (fato de unidade, invariante
13): a citação virou genérica e o Vol/Pg específico entra pela rodada.

Potential Defects e Outstanding Curative são **derivados**: os grupos de
requirement vivos que o gap-hunter emite, incluindo os probates de Ector com as
causas 1449 / 3734-A / 16915-02 e o aviso de que **não** é Montague.

### Item 2 — Ownership - Worksheet

Três defeitos meus, todos achados por medição e nenhum por opinião:

1. **Grão errado.** Eu escrevia uma linha por DONO, saída das schedules de
   ownership. O DDR à mão tem 47 linhas, todas tipadas WI, uma por **lease** —
   e a instrução da PLM pede colunas A→Q, a identidade da lease. Transcrição
   fiel no grão errado. Reescrito para lease×trato.
2. **Executive rights não é interesse mineral.** A opinião A-669 155ac lista os
   mesmos donos duas vezes na mesma página, sob "Executive Rights:" e "Minerals
   less Executive Rights:", cada bloco fechando em 1. Lidos como uma seção só,
   viram MI duplicado; escritos como MI, afirmam que o direito de arrendar é o
   mineral. Agora a seção decide o tipo, declarado na coluna C do template.
3. **Registro da descrição da terra.** A coluna K/L pegava `Volume 199, Page
   336` — a referência de deed da descrição, não o registro da lease. O
   Exhibit "A" é a autoridade (mesma regra já aplicada na Lease Review).

A aritmética está ligada: `interest_formula` avalia cada expressão impressa em
`Fraction` e compara com o decimal do examinador — **109 VERIFIED, 17 MISMATCH,
0 UNPARSED**, e os 6 recaps por trato fecham exatamente em 1.00000000. Os
MISMATCH vão para a trilha com "requires human verdict", nunca adotados nem
recalculados em silêncio.

O MI por lease só é escrito quando a cadeia **royalty → dono → minerals**
resolve para um único dono. Onde vários donos resolvem para uma lease, a
atribuição é pergunta humana: célula branca com `nao_computavel` e o item de
veredito que a possui.

### Item 3 — Ownership - Wells

API, well name, operator, profundidade e formação saem dos CSVs do RRC que
**estão** no corpus; unit size 220,00 e "Barnett Shale only" da DPU. Spud,
completion, status e drill type ficam brancos com motivo — só o W-1/P-12 os
prova, e esses não estão no corpus (item `RRC-FETCH` no brief).

### Item 4 — Agreements

**Aba em branco.** Nenhum dos 214 documentos classificados é um operating
agreement desta unidade. Item `AGREEMENTS-REQUEST` ao Seller. Nenhum card nasce
de recital.

### Item 5 — PLM Title Review

Cert dates com a mesma disciplina da A3 do Runsheet: base provisória declarada
na própria célula, `requires_human_verdict`. Landman fica branco com motivo e
item — `config.yaml` não declara `landman_name`. **A pergunta do PR-9 segue
aberta:** de onde vêm 3/3/2010 (A-669) e 9/9/2010 (A-319)? Os candidatos que o
sistema acha (9/4/2010 e 21/5/2010) não batem.

### Item 7 — comparação externa (harness, pós-rodada)

Junção declarada: **por LEASE (coluna B)**, que é como os dois documentos
modelam a aba. Duas medições minhas estavam erradas antes disso e foram
corrigidas no harness, não no sistema: junção por nome truncado (reportava 0/31
enquanto "Adrian Acker Walker" e "Adrian Walker" tinham o mesmo valor) e soma
de toda a coluna S sem ler o tipo declarado na C.

| | resultado |
|---|---|
| leases em ambos | **60 de 60** (0 só num lado) |
| lessor | 52/60 concordam |
| **MI** | **27 idênticos** · 1 divergente · 18 em branco declarado |
| Ownership - Wells | API, well name, operator, unit size **IGUAIS** |

A divergência única: `0220604-010`, gerado 0,02500000 contra 0,01250000 à mão —
exatamente o dobro. É achado para verdito humano, não para conserto silencioso.

---

## PR-11 — proveniência não é corretude · **2026-08-12**

Branch `pr11-crosstab-consistency`. O gate whitelist do PR-9 provava que **uma
fonte foi citada**; não provava que **o campo certo foi lido dela**, nem
enxergava célula que ninguém escreveu. Três defeitos passaram por ele com
trilha completa.

### 1. BLOQUEANTE — o registro errado, contradizendo a própria Lease Review

`Runsheet!C5` dizia `Volume 199, Page 356` e `C6` `Volume 199, Page 336 of the
Deed Records…` para as mesmas leases que a Lease Review do **mesmo arquivo**
registrava como 567.170 e 571.343. É a referência de deed da descrição da terra
— o defeito corrigido no PR-8 **no ponto de escrita da Lease Review**, que
nunca virou regra. Quinta instância de "conserto no ponto de erro, não regra no
ponto de acerto".

`src/knowledge/recording_authority.py` é agora o **único ponto** que decide um
registro, e `RECORDING_WRITERS` + um teste garantem que todo escritor o
consulte. Corrigido no artefato: as duas células batem com a Lease Review e com
o documento à mão.

Um detalhe que valeu o PR: o check de consistência **não pegava** o defeito no
começo, porque a citação do Runsheet era só `LEASE.TIF p.1` — sem a lease, não
há junção. A citação passou a nomear a lease, e o artefato ficou verificável a
partir dos próprios bytes, sem dado auxiliar.

### 2. BLOQUEANTE — valor cuja única fonte é uma captura de tela

A linha Choctaw citava `Captura de tela … .png p.1` nos **dez** campos, com o
grantee saindo `ENEGRY LIMITED PARTNERSHIP, hereinafter refer…`. Captura é
evidência de que um documento existe, nunca o documento: não tem carimbo, não
tem página, não se re-lê.

**Invariante 27**, imposto em `CellWrite.__post_init__` — onde toda célula
nasce, para nenhum escritor poder optar por fora. `captura_de_tela` entrou no
vocabulário fechado; o selector do Runsheet exclui com esse motivo. O gate
disparou de verdade na primeira rodada após ser escrito, no defeito real.

### 3. Brancos órfãos — o check tinha a forma do erro, não a do acerto

`Ownership - Worksheet` A5:E5 — o recap da unidade sob os cabeçalhos declarados,
os números-título do DDR inteiro — estava vazio **e** fora da trilha. O gate
andava pelas células escritas, então não via.

`cross_tab.check_coverage` passa a exigir as duas pontas sobre regiões de dados
declaradas. A5 sai da DPU (220,00 ac, citado). B5:E5 seriam médias ponderadas
por trato, e o mapeamento de trato ainda é **inferência** do item TRACT-MAP —
então ficam brancas com `nao_computavel` e dono. Um número plausível na célula
mais lida do documento seria o pior lugar para adivinhar.

### 4–5. Gate de consistência e denominadores

Consistência entre abas: **244 claims, 0 violações**. Denominadores agora em
três colunas nomeadas — **1.178 escritas-com-trilha · 366 brancas-com-motivo ·
144 estrutura**; escritas + estrutura = **1.322** = células não vazias no
arquivo. (A contagem correta de brancos no PR-10 era 363, não 393 como o texto
daquele PR disse.)

### 6. `0220604-010` — a causa do dobro, achada

O MI de Stephen Ray Walker é `1/10 x 1/8 + (1/8 x 1/5 x 1/2)` = 0,0125 **+**
0,0125 = 0,025: **dois interesses componentes** de origens distintas. O
documento à mão atribui **um** deles à lease; a cadeia royalty→dono→minerals
soma os dois. É o mesmo padrão dos direitos executivos desta rodada — um dono
aparecendo duas vezes por motivos diferentes. Fica em verdito humano, como
mandado: qual componente pertence à lease é pergunta que o documento não
responde sozinho.

### Gates e regressão

Whitelist **CLEAN** (1.322 células, 0 órfãs) · consistência **CLEAN** ·
cobertura **CLEAN** · zero citações de captura. Suíte **830 verdes** (24 novos).
Bowen/Maxwell em leitura, inalteradas.
