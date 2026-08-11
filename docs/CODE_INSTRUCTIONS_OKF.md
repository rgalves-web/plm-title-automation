# INSTRUÇÕES DE EXECUÇÃO — Claude Code · Migração Flow v2.1 + OKF

**Data:** 2026-08-11 · **Repo alvo:** `C:\Users\Renato\PURPLE LAND MGMT\plm-title-automation` (GitHub `rgalves-web/plm-title-automation`, privado) · **Operador:** Renato
**Você (Code) executa. Estas instruções são a ordem de trabalho; os specs abaixo são a arquitetura. Em conflito: CLAUDE.md > estas instruções > specs > código — e todo drift é reportado, nunca silenciado.**

---

## 0. Leitura obrigatória, nesta ordem

| # | Documento | O que é |
|---|---|---|
| 1 | `CLAUDE.md` (raiz do repo) | Invariantes vigentes — continuam valendo integralmente; o PR-0 adiciona as extensões do §2 |
| 2 | `docs/DDR_JOB_FLOW_SPEC.md` (v2.1) | O fluxo alvo S1→S8 (OPEN→SHIP), loop e critério de convergência |
| 3 | `docs/OKF_SPEC.md` | A arquitetura de conhecimento L0–L3 (`knowledge/` × `data/units/`) |
| 4 | `docs/OKF_MIGRATION_PLAN.md` (v1.1) | O plano que estas instruções executam — decisões D1–D6, fases, aceitações |
| 5 | `docs/WORKBENCH_BLUEPRINT.md` + `claude/WORKBENCH_STATUS.md` | O que já está construído e provado — **não refazer nada disso** |

> **Renato:** antes da 1ª sessão do Code, copie os docs 2–5 do projeto Claude (Cowork) para `docs/` do repo. Sem eles o Code não tem a arquitetura.

### Mapa de staleness dos documentos de raiz (não se confunda)

O working tree carrega documentos históricos de eras diferentes do projeto. **Estado atual = `WORKBENCH_STATUS.md` + a suíte de testes (baseline: 548 passando).** O resto é história útil, não estado:

| Documento | Era | Status |
|---|---|---|
| `PLM_SESSION_HANDOFF.md` (06-23) | MOR / Arapahoe County | **Histórico.** As "next actions" dele NÃO são tarefas suas |
| `PLM_SYSTEM_REPORT.md` (jun/26) | MOR | Histórico; útil só como referência do pipeline MOR |
| `FULL_SYSTEM_ASSESSMENT.md` (07-01) | DD inicial (127 testes) | Histórico; os *gaps* citados seguem válidos como requisitos (o plano os fecha) |
| `SYSTEM_ASSESSMENT.md` (07-22) | DD + packager (494 testes) | Histórico recente; as **regras de ouro do §6 continuam obrigatórias** |
| `README.md` | MOR MVP | Desatualizado; PR-0 atualiza |

---

## 1. Missão em uma frase

Sem refazer o que já é prova mecânica (spine, UI, gates, packager, round-trip, Bowen A 0 FAIL / 0 MISMATCH), fazer a classificação/relevância/identidade passarem a ser **decididas por IA governada por `knowledge/` versionado** — e entregar **Josh B** ponta a ponta como checkpoint, com métricas.

## 2. Extensões ao CLAUDE.md (aplicar no PR-0)

Adicionar ao CLAUDE.md, seção "Invariants":

1. **AI decide o que um documento é e o que ele diz — sempre com citação (arquivo, página, quote, confiança). Código prova** (Fraction, gates, round-trip). Nenhum valor sem evidência entra em caso ou deliverable.
2. **Nome de arquivo é prior fraco, jamais regra.** Nenhum SKIP de triagem sem peek de 1ª página ou metadado forte (hash duplicado / tipo não-documento) — plano D4.
3. **Todo motivo gravado (blank, SKIP, unplaced, waiver) vem do vocabulário fechado** (`knowledge/rules/exclusion_reasons.yaml`). Prosa livre é erro de escrita.
4. **Nenhuma regra L2 classifica sem leitura de conteúdo.** L2 delimita e dá vocabulário; a IA lê e propõe; o humano arbitra por risco (plano D5).
5. **`knowledge/` nunca contém fato de unidade** em `global`/`project`/`ontology`/`taxonomy`/`rules` (linter na suíte — plano D3). Fato de unidade mora em `data/units/`.
6. **Toda lição tem fixture** (formato duas-partes do plano D1); fixture sem bytes no disco = SKIP contado, nunca pass silencioso.
7. **Fonte única de verdade de arquivos do caso é o `evidence_ledger`**; `catalog.yaml`/`graph.yaml` são projeções (plano D2).

E atualizar no CLAUDE.md: "The authoritative description of current state" passa a ser `WORKBENCH_STATUS.md` + os specs de `docs/`; `FULL_SYSTEM_ASSESSMENT.md` vira referência histórica.

## 3. Estado que estas instruções assumem (verifique antes de começar)

- **Construído e testado:** `src/flow/` (config, evidence_ledger com `derive_allowlist()`, unit_state versionado, checklist_builder, runner), Workbench FastAPI (`minorh serve`, `src/webapp`), verdicts + mecanismo de sanção, round-trip check (`deliverable_io.py`), submission_packager, gates estrutural + source-truth. **Suíte: 548 testes.**
- **Unidades:** Bowen A fechada (prova mecânica); Maxwell A v13 = regressão; Josh B em kickoff.
- Se qualquer item acima não bater com o repo, **pare e reporte o drift** antes de prosseguir.

---

## 4. Ordem de execução — um PR por fase, branch-only

Disciplina de todo PR: branch a partir de `main`; suíte inteira verde antes e depois; comportamento novo = teste novo (`tests/test_knowledge_*.py`); aceitação da fase (copiada do plano §3) demonstrada no corpo do PR; `git diff --cached --name-only | grep -iE '\.(pdf|xlsx|tif|zip|png)$|^data/'` **CLEAN**; regressão obrigatória: **Bowen A e Maxwell A revalidam 0 FAIL / 0 MISMATCH a partir dos seus `state.yaml`**.

### PR-0 — Housekeeping (pré-requisito de tudo)
1. **Base única:** resolver `maxwell-lessons-hardening` (30 commits à frente na época do assessment): rebase/merge em `main`. Regra: `main` vira a única base antes da F1. Verificar as demais branches (`collin-corrections-lease-detail`, `maxwell-operational-minorh`, `phase1-conversational-shell`) — merge ou arquivamento documentado.
2. **Remote:** `git remote set-url origin https://github.com/rgalves-web/plm-title-automation.git` (o `.git/config` local pode ainda apontar para o repo vazio `PLM.git` — ver `claude/GITHUB_REPO.md`).
3. **docs/ no git:** versionar `docs/` (specs + `minorh-workbench-prototype.html`). São a arquitetura, não dados de cliente.
4. **requirements.txt:** o snapshot da raiz é da era Streamlit — conferir e pinar as dependências reais do workbench (fastapi, uvicorn, etc.).
5. **CLAUDE.md:** aplicar o §2 acima. **README.md:** reescrever curto apontando para o workbench (`./minorh serve`) e para `docs/`.
6. **Config:** confirmar que `src/flow/config.py` é o único ponto de config do tesseract; se restarem os 2 hardcodes antigos (`source_truth_check.py`, `pdf_reader.py`), remover agora (dívida do SYSTEM_ASSESSMENT §4).
7. **Streamlit `app.py`: congelado.** Não tocar, não deletar (fallback até decisão explícita — blueprint §5).
8. **Segurança:** confirmar que `.env` segue fora do git e do histórico (já verificado em `GITHUB_REPO.md`); **a chave da API foi exposta em anexos de conversa — Renato deve rotacioná-la no console da Anthropic e atualizar o `.env` local.** Nunca imprimir a chave em log, teste ou commit.

### PR-1 — F0 + F1-mínima: `knowledge/` + vocabulário
- Criar `knowledge/ontology/{entities.yaml,identity_keys.yaml}` (as 8 entidades e chaves do OKF §2 — sem cerimônia além disso) e `knowledge/rules/exclusion_reasons.yaml` (vocabulário do OKF §4; os 3 blank-reasons do blueprint viram subconjunto).
- `src/knowledge/loader.py`: carga + validação Pydantic de todo `knowledge/`; erro de schema quebra o boot. Cache por hash de arquivo.
- `evidence_ledger`/`unit_state`: toda referência a entidade exige chave completa ou estado `candidato` com o que falta nomeado. Todo motivo gravado vem do vocabulário.
- Linter de conhecimento (D3) como teste da suíte.
- **Aceitação:** plano §3 F1 (Bowen≠Bowen A por construção; zero motivo em prosa livre; Bowen A revalida).

### PR-2 — F2: taxonomia enxuta
- `knowledge/taxonomy/categories.yaml` — as ~10 categorias do OKF §3, cada uma com `feeds`, `identity_fields`, `relevance_test`, `disposition_default` e **`risk_tier`** (novo campo; alimenta D5). Loader rejeita categoria sem `feeds`.
- `knowledge/taxonomy/category_to_ddr.yaml` — destino de escrita por categoria, cruzado no S1 com o template real por **introspecção de abas** (nunca hardcode; a divergência "Ownership Report" × "Ownership - Worksheet" entre versões de template é real).
- Refactors: `checklist_builder` instancia itens das categorias; `ddr_writer` resolve destinos via `category_to_ddr`; `intake_router` deixa de rotear por convenção própria.
- **Migração de conhecimento preso em código (vira dado, não se perde):**
  - `title_extractor.py` → o dict `CONVEYANCE_PREFIX` e as convenções de entrada viram `knowledge/taxonomy/runsheet_style.yaml` (estilo house-style de entrada por categoria — Template MOR/PLM). O módulo permanece como **verificador determinístico de formato** do que a IA redigir — nunca mais como decisor de conteúdo.
  - `config/rules.yaml` (MOR) e os regexes `_SELLER_*`/`_DPU_NAME_RE`/`_TO_NAME_RE`/`_LEASE_NAME_RE` → `knowledge/lessons/seed.yaml` como *priors fracos* (deleção do código só no PR-6, quando as lições existirem).
  - `_TO_FILE_NUM_RE` (app.py, prefixo de zip) → prior fraco registrado no ledger, não decisão de identidade.
  - `SELLER_PARTY_MATCH_THRESHOLD=80` e fuzzy 93/80 (`name_match`/`ownership`) → parâmetros em `knowledge/rules/` (identidade por chave dupla passa a mandar; fuzzy vira sinal de candidato).
  - `DD_RECONCILIATION_TOLERANCE=0.0005` → dado em `knowledge/rules/precedence.yaml` com flag `calibration: pending (Trevor/PLM)`.
- **Aceitação:** plano §3 F2 (cobertura 100% do corpus Bowen+Maxwell+Josh B; célula rastreável a categoria).

### PR-3 — F3: perímetro + triagem com peek
- `src/knowledge/perimeter.py`: o S2 SCOPE mecânico — IA lê o Exhibit "A" da DPU com prova por página, cruza com XREF + Lease & Mineral Schedule + Well List → `data/units/<UNIT>/perimeter.yaml` + divergências como achados. `manifest_builder` vira insumo, deixa de ser autoridade (fecha o gap #1 do assessment). Relevância L2 se auto-instancia do perímetro.
- `src/knowledge/triage.py`: inventário completo (nome/tamanho/hash) → candidato READ/SKIP → **peek de 1ª página confirma todo SKIP** (D4) → OCR profundo só nos READ. Contadores logados, sem teto silencioso.
- **Aceitação:** plano §3 F3 (Josh B: 4 leases DPU∉XREF como divergência; conflito Schmidt 427.385×685; zero SKIP cego; 100% com disposição).

### PR-4 — F4-lite: classifier + veredito por risco
- Ledger estendido (campos D2: `disposition`, `motivo`, `categoria`, `of_record`, `identity_key`); projeções `catalog.yaml`/`graph.yaml` gravadas com round-trip.
- Classifier content-first sobre os READ, schema do flow spec §2 (inclui `of_record` e parsing de fórmulas em prosa — a supplement "62.5% x 7/8 less (…)" **nunca mais causa fallback silencioso de basis**: vira achado bloqueante).
- Workbench: fila de veredito de classificação ordenada por confiança, citação inline, 1 clique; **risco alto (por `risk_tier`) = veredito humano obrigatório; risco baixo = auto-confirm com amostragem de QC** (D5); piso calibrado por categoria a partir do histórico de vereditos.
- Efeitos: veredito → relação no grafo com prova; `derive_allowlist()` e nomes de pacote citam o grafo.
- **Aceitação:** plano §3 F4 (re-drop frio de Bowen sem filename; memo interno → nunca no Runsheet; allowlist regressão bit a bit; erro plantado pego pela amostragem).

### PR-5 — Fase C: Drive connector (paralelo ao PR-4 se houver duas frentes)
- Busca/fetch no Drive da PLM por nº de TO, nº de lease, book.page, nome; drop automático no S4; upload do kit com confirmação de 1 clique. O que não achar volta como item de checklist com termos de busca.
- **Aceitação:** plano §3 Fase C, medida no perímetro de Josh B.

### ★ CHECKPOINT — duas metades (corrigido 2026-08-11)
**Josh B foi entregue à mão** (pacote 06/08, encerrada 10/08). É o **terceiro fixture**, não o alvo vivo.
- **A — replay de Josh B (corretude):** o sistema reprocessa a frio, em leitura, e bate item a item contra `docs/JOSH_B_*`. Achar menos que o gabarito = fase não fechou; achar mais = achado a verificar antes de celebrar.
- **B — a próxima unidade designada pela PLM (eficiência):** S1→S8 com F1–F4+C. Coletar e reportar: horas do operador/unidade · custo de IA/unidade · rodadas até convergência · % auto-confirm correto na amostragem · SLA real vs ≤2 dias Phase I. **Nenhum PR além deste ponto sem os números.**

### PR-6+ — condicionais ao checkpoint
F5 lições enxutas (schema OKF §5, escopos unit/project, fixtures D1, migração das 7 sementes, deleção dos regexes) · Fase A `audit.py` (5 lentes, tier pré-ship, D6) · `gap_hunter.py` (sobre o grafo; gabarito = `JOSH_B_kickoff_download_list.md`) · browser agents RRC/TexasFile (por nome+data, nunca por abstract) · board com fila/clock/WIP paralelo.

---

## 5. O que NÃO fazer

- Não rodar Bowen nem modificar deliverable entregue sem reportar findings antes (regra de ouro vigente).
- FILES é somente-leitura; sidecar nunca vira aba; nada é inventado; matcher nunca é afrouxado para passar teste; `MISMATCH > 0` nunca é aceito.
- Não unificar os pipelines MOR e DD (gap #12): fora de escopo. Regra mínima: o classifier novo mora em `src/knowledge/` e **não nasce uma 3ª cópia de conceitos** — MOR o consome no futuro, quando for a hora.
- Não deletar `app.py` (Streamlit congelado como fallback).
- Não iniciar fases pós-checkpoint sem as métricas de Josh B.
- Não commitar dado de cliente, chave, nem caminho pessoal fora de `config.yaml` (gitignored).

## 6. Definition of done da missão

1. **Josh B replay** reproduz o gabarito escrito a frio (perímetro, divergências, Lease Review 87,4% com os mesmos motivos, 19 pendências) — e **a próxima unidade** sai shipada pelo sistema: kit Phase I no formato do `PLM_PHASE1_SUBMISSION_SPEC.md`, pendências declaradas, md5 round-trip.
2. As 5 métricas do Checkpoint B reportadas.
3. Bowen A e Maxwell A revalidando 0 FAIL / 0 MISMATCH em `main`.
4. `knowledge/` versionado, linter verde, zero conhecimento preso em regex de código no caminho DD.
