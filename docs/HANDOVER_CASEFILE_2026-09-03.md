# HANDOVER — Case File por Unit (plm-title-automation) · 2026-09-03

_Documento de passagem de bastão do agente anterior (Claude Code) para o próximo agente/desenvolvedor. Tudo o que está aqui é verificável no repositório, no banco local e na pasta da unit. Onde houver dúvida entre este documento e o código/banco, o código/banco vencem — e a divergência deve ser reportada ao operador._

---

## 0. Em uma página

- **O que é**: sistema local-first de due diligence de título mineral (Texas, EOG/BKV, Project Emirates, ~300 units, entregável DDR em Excel) para a Purple Land Management (PLM). Operador único: **Renato** (fala português; é quem aprova tudo).
- **O que mudou em 30/08–02/09**: o produto foi reorganizado em torno de um **Case File por Unit** em PostgreSQL local (`src/casefile/`), conforme recomendação de CTO aceita pelo operador. O monolito anterior (`src/minorh` + `src/examinador`) está **congelado** — continua no repo para replays e como fonte de plumbing por import, mas **não recebe funcionalidade nova**.
- **Onde estamos**: Vertical Slices **VS1** (Unit → Investigation Plan) e **VS2** (coleta sob condições) executados na unit-golden **JOSH B UNIT**; **VS3** (exame canônico) **parcial**; **VS-D0** (dashboard read-only) entregue e validado. A Josh B está em estado **EXAMINANDO**, sob **`simulation_mode=true`** (nenhuma operação paga é possível por construção).
- **Bloqueio único para continuar**: a conta **Anthropic está sem créditos** (`credit balance too low`). A verificação cega (OpenAI, família B) não depende disso.
- **Regra de ouro**: LLM-first — **nenhuma decisão de título em Python**. Código abre arquivo, renderiza página, indexa, valida forma/identidade, protege bytes e contabiliza custo. Quem afirma é o modelo; quem confere é outra família de modelo; quem decide é o operador.

---

## 1. Ambiente e como rodar

**Repositório**: `C:\Users\Renato\PURPLE LAND MGMT\plm-title-automation` · branch **`casefile-vs1`** (criada a partir de `conserto-definitivo`; nunca commitar em `main`). Último commit: `b5980a9`. Working tree limpo. **Abra a sessão neste diretório** (a sessão anterior foi aberta por engano em `C:\Users\Renato\ingestion-engine`, um projeto não relacionado — "Black Box").

**Dados do cliente** (leitura no lugar, nunca copiar, nunca commitar): `C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates\` — raiz do projeto com XREF, Schedule, Well List, template do DDR; uma pasta por unit (`JOSH B UNIT`, `WEBB B UNIT`, `CAIN RANCH A UNIT #1H WELL`, `BOWEN A UNIT`, `MAXWELL A UNIT`).

**Banco**: PostgreSQL 16 nativo (serviço `postgresql-x64-16`, `C:\Program Files\PostgreSQL\16\bin\psql.exe`, fora do PATH). Bancos `plm_casefile` (produção local) e `plm_casefile_test` (testes, schema temporário por teste). Role `plm` com senha aleatória que vive **só** no `.env`. A senha do superusuário `postgres` é a **default do instalador winget (`postgres`)** — recomendado trocar; só aceita conexões locais.

**`.env`** (gitignored; modelo em `.env.example`): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MINORH_AUDITOR_OPENAI` (modelo da família B), `CASEFILE_DSN`, `CASEFILE_TEST_DSN`, `CASEFILE_PROJECT_ROOT`, **`CASEFILE_SIMULATION_MODE=true`**. Opcionais: `CASEFILE_TETO_UNIT_USD` (default 25 — **não alterar sem ordem**), `CASEFILE_MODELO`, `CASEFILE_MODELO_TRIAGEM` (usar `claude-sonnet-5` — o Haiku deu 529 persistente na chamada grande), `CASEFILE_TETO_VERIFICACAO_USD` (2.0), `CASEFILE_TETO_COLETA_USD` (25).

**Comandos** (`python -X utf8 -m src.casefile ...`, sempre da raiz do repo):

| comando | o que faz | modelo? |
|---|---|---|
| `db migrar` / `db estado` | migrações SQL versionadas com checksum (0001–0007 aplicadas) | não |
| `indicar "Josh B Unit"` | resolve a pasta pelo nome; unit INDICADA | não |
| `planejar` | VS1: censo → triagem → Examinador → plano proposto | sim |
| `plano` / `aprovar` / `rejeitar --motivo=` | gate do operador sobre o plano | não |
| `coletar` | VS2: índice local XREF/Schedule → populações → busca negativa → exame dirigido → cartório/RRC (bloqueados em simulação) → relatório | sim |
| `reconciliar` | matriz de recordings por lease + pull deduplicada | não |
| `gates` | status das 6 condições da aprovação | não |
| `examinar [--preflight]` | VS3: **preflight resume-aware obrigatório**, sessão de exame, verificação cega, entregáveis | sim |
| `dashboard [--porta=8788]` | Control Tower local read-only | não |
| `estado` / `unidades` | painel textual | não |
| `avancar` | `coleta_concluida` — recusa com gate pendente (produção) | não |

**Testes**: `python -m pytest -q` → **1018 verdes** (939 do legado + 79 do casefile). Testes `@postgres` exigem `CASEFILE_TEST_DSN` (skipam com motivo). Regra do repo: comportamento novo exige teste novo, **de plumbing, nunca de julgamento**.

**Dashboard**: `python -X utf8 -m src.casefile dashboard` → http://localhost:8788. Read-only; polling 4s; sem botões (ações são o VS-D1). Se abrir por `uvicorn` direto: `uvicorn --app-dir <repo> src.casefile.api:app --port 8788`. **Reiniciar após mudar `api.py`** (sem `--reload`).

**Relançador para sessões de modelo** (a API Anthropic deu 529 em série em 02/09): padrão usado — loop bash que sonda a API com uma chamada de 1 token (`scratchpad/probe_api.py`, exit 0 ok / 1 transitório / 2 definitivo), roda o comando, e repete o ciclo se cair. Toda sessão grava `progresso_<comando>.jsonl` por turno; se a sessão cair, o custo dos turnos pagos está lá (e **não** em `cost_entries` — reconciliar manualmente, ver §5).

---

## 2. Documentos de governança (leia nesta ordem)

1. `CLAUDE.md` — invariantes do repo (branch-only, suíte verde antes/depois, caneta protege bytes, FILES/ read-only, entrega congelada, gabarito quarentenado, ausência nunca inferida de ignorância, achado que não muda o entregável vai para `docs/BACKLOG.md`).
2. `docs/ARQUITETURA_GOVERNANTE.md` — a lei: LLM-first puro.
3. `docs/CASEFILE_VS1.md` — desenho do Case File (módulos, decisões).
4. `docs/WORKBENCH_STATUS.md` — baseline vigente, seção por seção (o topo é o mais recente).
5. `docs/BACKLOG.md` — achados abertos.
6. Na pasta da unit (`JOSH B UNIT\_casefile\`): `DECISAO_PLANO_v1.md` (6 condições da aprovação), `DETERMINACOES_VS2_R2.md` (7 determinações), `POLITICA_SIMULACAO.md` (9 itens), `AUDIT_FIX_REPORT_VS3.md` (veredito CTO aplicado). **Todos também estão em `operator_decisions` no banco**, por `kind`.

---

## 3. Arquitetura do Case File (`src/casefile/`)

Fluxo obrigatório: **Agentes → Case File (Postgres) → API → Dashboard**. Nada infere estado de logs ou de Markdown.

| módulo | papel |
|---|---|
| `db.py`, `migrations/0001..0007.sql` | conexão psycopg3 + runner de migrações (checksum; migração aplicada nunca muda) |
| `repo.py` | **DAO único** — todo acesso ao banco passa aqui; `tests/helpers_casefile.py::RepoFake` implementa a mesma interface em memória |
| `estados.py` | máquina de estados: INDICADA → PLANEJANDO → COLETANDO → (COLETA_SIMULADA_CONCLUIDA) → EXAMINANDO → VERIFICANDO → PREENCHENDO → AUDITANDO → AGUARDANDO_RENATO → LIBERADA (+ BLOQUEADA). Toda transição em `unit_state_transitions` com ator/nota |
| `referencia.py` | resolver por nome (extraído de `src/dd/project_reference.py`); referências mais novas por data no nome |
| `acervo.py`, `censo.py` | índice recursivo read-in-place (zips por dentro), sha256 completo, `file_sightings` com **origem** (`unit_files`, `unit_folder`, `project_reference`, `entrega`, `outro`); entrega fora do acervo por padrão; liberação pontual (`entrega_permitida`) ou ampla (`incluir_entrega`) **menos `PLM Report`** (DDR final/conclusões humanas — bloqueio por plumbing) |
| `ferramentas.py`, `ferramentas_vs2.py`, `validacao.py` | tools do modelo; `registrar_claims` valida **forma/identificador/evidência** (nunca conteúdo); claim cuja evidência existe **só** na entrega recebe `benchmark_contamination=true` automaticamente |
| `sessao.py` | `run_loop` do examinador por import; custo em `cost_entries` antes de qualquer print |
| `triagem.py`, `plano.py`, `custo.py`, `caneta.py` | VS1; teto duro por unit; write-root `_casefile/` (única exceção: `promover_staged` → `FILES/`, com round-trip de hash) |
| `xref_local.py`, `populacoes.py`, `buscas.py`, `staging.py`, `portal.py`, `reconciliacao.py`, `exame_dirigido.py`, `gates.py`, `relatorio.py` | VS2 |
| `simulacao.py` | **gate global**: com `simulation_mode` (env **ou** política no banco) qualquer operação externa paga falha ruidosamente antes de abrir documento |
| `verificador.py`, `exame_vs3.py`, `vs3_entregaveis.py` | VS3: verificação cega (família B extrai, código compara), grafo/posições/claims-DDR, reconciliação e entregáveis com **lifecycle** |
| `api.py`, `static/index.html` | VS-D0 |

**Modelo de dados essencial**: `claims` (afirmações com `source_sha256` FK obrigatória, página, trecho, confiança, materialidade, status ativo/substituido/retirado, `ddr_candidates`, `limitations`) · `verifications` (veredito + **rastreio completo**: `source_sha256`, `page`, `evidence_payload_sha256`, `prompt_sha256`, `raw_response`, `request_id`, `model_params`; status `valida`/`invalidada`) · `population_members` · `population_positions` · `xref_lookups`/`xref_rows` · `negative_searches` · `collection_items` · `deliverable_versions` (com `lifecycle` draft/partial/final) · `operator_decisions` · `cost_entries` · `model_sessions`.

---

## 4. Estado real da JOSH B UNIT (03/09/2026, verificado no banco)

- **Estado**: `EXAMINANDO` (cadeia: … COLETANDO → COLETA_SIMULADA_CONCLUIDA → EXAMINANDO). **Não avançar para VS4** sem aprovação do VS3 completo pelo operador.
- **Custo**: modelo $19,43 + verificação $0,31 + **portal $0,00** = **$19,74 de $25**. Restam **$5,26**.
- **Populações**: `dpu_exhibit_a` 67 (denominador **nunca** muda em silêncio) · `operacional` 67 · **`in_dpu_but_zero_unit_acres` 7** (série 0220936, toda A-811) · potencialmente contribuintes 60 · `xref_encontrada` 64 · `documentos_ausentes_incompletos` 10.
- **Claims ativos**: 124 (67 `lease_in_unit`, 11 `divergence`, 13+ `fact`, …). Claims **supersedidos** nesta rodada: 100, 102, 108, 124 (divergências resolvidas por leitura), **111 → 129** (a indexação local extraiu 637 linhas por chave).
- **Verificação cega** (só vereditos válidos): **67 leases tentadas → 49 concordantes / 18 evidencia_insuficiente / 0 divergentes**; dirigidas: 116 insuficiente (memo BRA-DE ilegível ao B), 2 nao_verificavel. **Verification 142 (claim 128) INVALIDADA como `verifier_error`** — a página 596/589 tem A-811 (inspeção visual do operador); o "A-1272" era alucinação. **Não é divergência de título.**
- **Gates**: 5 OK + `to-155ac-certificacao-e-amarracao` **OK-PARCIAL** (155 ac gross × 80,02 ac do Tract 2 sem explicação documental — coincidência de nomes não prova amarração).
- **Fila do operador**: **0** itens acionáveis. **Dependências de produção (4)**: pulls 441.275 (Prior Lease BRA-DE) e 514.412 (Deaton, conferir Vol 515) — `bloqueado_simulacao` / `required_in_production_but_unavailable_in_simulation`; DOTO/DOI ao PM/seller (busca **NAO_ENCONTRADO_EM_BUSCA_PARCIAL**: 61 pesquisáveis, 1.397 TIFs sem OCR); Quitclaim/Affidavit/Landman Statement Stewart (citados no e-mail de release of suspense, sem recording).
- **Entregáveis** em `JOSH B UNIT\_casefile\`: `RELATORIO_COLETA_VS2_v6.md` (final), `RECONCILIACAO_RECORDINGS_v3.md` (final), VS3 **partial**: `TITLE_EXAMINATION_VS3_v1.md`, `UNRESOLVED_ISSUES_VS3.md`, `EVIDENCE_COVERAGE_VS3.md`, `COST_REPORT_VS3.md`, `CLAIMS_READY_FOR_DDR_VS3.json` (vazio). **Ausentes**: `CHAIN_GRAPH_VS3.json`, data de corte, posições canônicas, claims-DDR — todos dependem da sessão de exame interrompida.
- **Sessão 10** (`exame.vs3`): morreu no turno 5 por `credit balance too low`; fechada com `stop_reason` INTERROMPIDA e custo reconciliado do jsonl (+$2,29).

---

## 5. Regras vinculantes do operador (não são sugestões)

1. **Simulação/golden replay** (`simulation_mode=true`): nenhuma compra, abertura paga, download em portal ou comunicação externa em nome da PLM. **Portal $0 obrigatório.** O gate técnico está em `simulacao.py` e em `portal.py` — não contorne.
2. **Nunca acessar o portal do RRC** — gera cobrança à empresa. Os well files já estão no PC (`1. Landman Submitted\Well Files\`). O operador interrompeu uma tentativa em 02/09.
3. **CourthouseDirect** só em produção, via CDP no Chrome corporativo logado do operador (`--remote-debugging-port=9222`), $0,50/abertura, dentro do teto de coleta. Nunca digitar credencial ou pagamento.
4. **Entrega (`1. Landman Submitted`)**: usável para exame/reconstrução/preenchimento **com** `origin=entrega` + `benchmark_contamination=true`; **nunca** conta como coleta autônoma; **nunca** consumir `PLM Report` (DDR preenchido, notas e conclusões humanas — bloqueado por plumbing).
5. **Denominador**: 67 leases do Exhibit A, sempre. A série 0220936 fica no Exhibit A e na trilha como `in_dpu_but_zero_unit_acres`; nunca apagar do Lease Review.
6. **WI/NRI e net acres**: **não verificados** até DOTO/DOI ou evidência suficiente. Nenhuma certificação nesta fase.
7. **Tentativa ≠ evidência**: gate só fecha com `leitura_completa: true`; **tentativa ≠ concordância** nas métricas (tentada / concordante / divergente / insuficiente / não-verificável são baldes separados).
8. **Verificação cega**: o verificador (família B, OpenAI) **nunca** recebe a resposta do examinador. Antes de cada chamada, `afirmar_identidade` confirma que SHA/página renderizados são os do claim. Divergência não se resolve em silêncio — fica aberta ou vai a adjudicação; erro do verificador é `invalidada` com motivo, preservada na trilha.
9. **Custo**: teto $25/unit **inalterado**; preflight resume-aware obrigatório antes de chamadas do VS3; se o máximo restante ultrapassar o restante, parar e apresentar alternativas. Desenvolvimento/testes/dashboard **não** entram no custo da unit.
10. **Inferência plausível nunca vira fato**: claims novos carregam `tipo_resultado` ∈ {fato_documental, inferencia, conclusao_titulo, divergencia, nao_verificavel, documento_ausente, impedido_pela_simulacao}. Conclusão dependente dos documentos indisponíveis na simulação é `impedido_pela_simulacao`.
11. **Trilha**: preservar histórico; itens resolvidos não aparecem como ativos (supersede/cancela com nota, nunca apaga). Fichas OKF (`knowledge_okf/`) escritas pelo modelo são revisadas e commitadas só se aprovadas — branch limpa ao final.
12. **Não avançar** de etapa sem aprovação explícita do operador (VS3 → VS4 exige VS3 completo e aprovado).

---

## 6. Próximo passo objetivo (ordem)

1. **Operador restaura crédito Anthropic** (único bloqueio).
2. `python -X utf8 -m src.casefile examinar "Josh B Unit" --preflight` → conferir que o máximo restante (~$4,50) cabe nos $5,26. Depois rodar sem `--preflight` (com o relançador). A retomada é idempotente: verificações válidas não se repetem; a sessão reabre porque faltam posições e grafo.
3. A sessão deve entregar: **data de corte com evidência** (nunca "até o presente"), **grafo** (`propor_grafo`, toda aresta com claim + documento), **posições canônicas** por item material (`classificar_populacao`), **claims-DDR** (`propor_claims_ddr`, sem escrever no workbook), e investigar **TO 155ac × Tract 2** por legal descriptions/metes and bounds (registrar `diferenca_gross_explicada` só se demonstrado).
4. Verificação cega dos claims novos (roda sozinha dentro do `examinar`; independe do crédito Anthropic).
5. Regenerar entregáveis (viram `lifecycle=final` quando posições + grafo + data de corte existirem) e submeter o VS3 à aprovação do operador.
6. Só então: **VS4** — projeção controlada no DDR (o minorh tem a caneta com proteção de fórmulas em `src/examinador/run.py::write_workbook` e o `template_map`; reaproveitar por import) — e **VS-D1** (dashboard com ações auditáveis).

---

## 7. Armadilhas descobertas nos dados reais (economizam rodadas)

- **Homônimos com bytes diferentes** (50 na Josh B): identidade é **sempre** sha256 completo; nome ambíguo em claim = erro nomeado, cite `sha256:<hash>`.
- **Josh B não tem XREF própria** — só a master na raiz do projeto; o de mesmo nome dentro de WEBB B UNIT tem bytes diferentes.
- **XREF**: duas abas com cabeçalhos idênticos e **duplicados** (desambiguados como `NOME__2`); **não tem coluna de recording**; possivelmente sem `UNIT LEVEL NAME` — pertencimento via contrato `K1402139` (DECL OF POOLED UNIT- JOSH B UN). Formato `0220604-016` (claims usam `0220604/016` — normalizar). Nunca mandar janelas ao LLM: indexar local (`xref_local.py`) e entregar só as linhas recuperadas.
- **Lease & Mineral Schedule**: 3 abas; a principal (`EOG Leases`) tem a coluna da lease com **cabeçalho vazio** (`''`); as outras usam `LEASENO`; todas têm `RECORDING`.
- **Pastas 0126714-* (Donald, A-730)** carregam documentos de **outras units**, inclusive `unit dec` alheios — filtrar pelos tokens da unit ao escolher a DPU.
- **Transcrição independente do Exhibit A** (família B) não devolve o bloco **0220604/001–018** em nenhuma passada (sub-série/ditto?) — 18 leases ficam `evidencia_insuficiente`. BACKLOG: recorte por região.
- **596/589 (lease 0220936/006, Frances Caswell)**: o memorandum é scan sem camada de texto; OCR local não extrai o abstract; o examinador (visão) leu A-811; o verificador B alucinou A-1272 → caso que motivou a rastreabilidade (migração 0007).
- **Release Stewart**: as 4 cópias `.html` são ilegíveis; o PDF `Stewart curative - EOG release of suspense 2013-03-14` é **release of SUSPENSE** (e-mails EOG aceitando o curative), não o instrumento registral; os instrumentos (Quitclaim/Affidavit/Landman Statement) não estão no acervo e não têm recording citado.
- **BRA-DE**: leases /008–/011 são **top leases** de 2011 (Vol 555), cadeia até a EOG completa no acervo (K1401501, Vol 563); a Prior Lease 441/275 (base da cadeia) não existe no PC.
- **TO A-669 155ac**: certification date está na p.2 ("as of March 3, 2010"), não na p.1; cobre o Tract 2 (Harrison) por nome de mineral owner — amarração parcial.
- **API Anthropic**: 529 em série no dia 02/09; Haiku falhava na chamada grande da triagem → triagem em Sonnet. Sessões que caem deixam `model_sessions` aberta e custo fora de `cost_entries` (reconciliar do jsonl; BACKLOG: fechar em `finally`).
- **Testes de API/UI**: `uvicorn` sem `--reload` não pega mudanças em `api.py`; o dashboard só re-renderiza quando o JSON muda (guarda de assinatura) — sem ela o polling invalidava cliques.

---

## 8. Arquivos de apoio fora do repo

- `.claude/launch.json` em `C:\Users\Renato\ingestion-engine\` (sessão anterior) — config `casefile-dashboard` (uvicorn). Recriar na nova sessão se for usar o preview do IDE.
- Scripts descartáveis usados na sessão anterior (scratchpad, podem ser recriados): `probe_api.py` (sonda), `aplicar_veredito_cto.py`, `registrar_determinacoes_r2.py`, `ler_release_run.py`, `ler_006_run.py`.
- Memória do agente anterior (não acessível ao próximo): o conteúdo relevante foi transcrito neste documento e em `docs/WORKBENCH_STATUS.md`.

---

## 9. Contagem final para conferência rápida

`git log --oneline -1` → `b5980a9` · `python -m pytest -q` → 1018 passed · `db estado` → migrações 1–7 · `estado "Josh B Unit"` → EXAMINANDO, 124 claims, $19,74 · `gates` → 5 OK + 1 OK-PARCIAL · dashboard → saúde ATENÇÃO (exame interrompido; 0 posições), fila 0, dependências de produção 4.
