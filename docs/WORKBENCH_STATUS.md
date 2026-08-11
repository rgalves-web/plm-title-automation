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
