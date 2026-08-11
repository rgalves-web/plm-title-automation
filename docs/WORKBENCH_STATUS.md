# Workbench — status de implementação
_Acompanha `WORKBENCH_BLUEPRINT.md`. Atualizar a cada fase concluída. Snapshot copiado do projeto Claude (Cowork) em 2026-08-11; a cópia canônica vive no projeto._

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

### Limitações honestas desta rodada
1. **Disposição é por documento, não por campo** (backlog #9). O gabarito distingue "a lease está aqui mas falta o royalty" (`0220953-008/-010/-011`) e "as duas cópias estão ilegíveis" (`0221055-002`); o sistema diz `instrument_of_record` e para aí.
2. **Tiering declarado:** pastas com um arquivo que o classificador confirma como a lease receberam **uma** leitura; pastas sem candidato óbvio receberam **todas**. Isso custou o inventário completo de title opinions dentro das pastas já resolvidas.
3. **Curativa (probates de Ector) e RRC não foram tentados** nesta rodada — são S5 GAP-HUNT, não S2 SCOPE.
