# OKF — Plano de migração do sistema

**Data:** 2026-08-11 · **Audiência:** a IA de programação do `plm-title-automation` · **Base:** `OKF_SPEC.md` (a arquitetura-alvo, camadas L0–L3) · **Companions:** `DDR_JOB_FLOW_SPEC.md` v2.1 (o fluxo S1→S8 que consome o OKF), `WORKBENCH_BLUEPRINT.md`, `WORKBENCH_STATUS.md`, `FULL_SYSTEM_ASSESSMENT.md`.

**Rev v1.1 (mesmo dia, aprovada pelo Renato):** re-priorizado após revisão crítica. O que mudou: **fatia fina** (entregar Josh B antes de construir a catedral), **veredito por camada de risco** (D5), **peek de 1ª página na triagem** — nunca SKIP cego (D4), **Drive connector adiantado** para paralelo à Fase 4 (o gargalo real é aquisição de documentos, não classificação), **rigor em camadas** (D6 — auditoria adversarial completa só no tier pré-ship), **L3 sem maquinário de promoção** até existir um 2º cliente, **pisos de confiança calibrados** contra histórico de vereditos, **WIP paralelo** de unidades elevado de prioridade.

> Objetivo: alterar o sistema existente — **sem refazer nada que já é prova mecânica** (spine da Fase 1, UI da Fase 2, gates, packager, round-trip, Bowen A fechada com 0 FAIL / 0 MISMATCH) — para que a categorização passe a ser governada por uma base de conhecimento versionada (`knowledge/`), separada dos fatos de caso (`data/units/`). O OKF **é a implementação concreta do P0 do roadmap** do flow spec: não é um projeto paralelo, é o mesmo projeto com esqueleto explícito.

---

## 0. Como o OKF se encaixa no que existe

Uma frase por peça, para ninguém reconstruir o que já está de pé:

- **O flow spec v2.1 define O QUE acontece** (estágios S1→S8, loop, convergência). **O OKF define COM QUE CONHECIMENTO** cada decisão de categorização/relevância/identidade é tomada. A regra de design única não muda: *AI decide o que a coisa é e o que ela diz; código garante que nada se perde, nada se inventa e a conta fecha.* No OKF, o L0–L2 não substitui a IA — **dá a ela o cardápio de candidatos, os testes binários e o vocabulário fechado de respostas**. A IA continua lendo conteúdo e propondo com citação; o que acaba é a decisão por regex e o motivo em prosa livre.
- **`evidence_ledger` (construído) continua sendo a fonte única da verdade** sobre arquivos do caso. `catalog.yaml` e `graph.yaml` do OKF **não são bancos novos**: são projeções serializadas do ledger (decisão D2, §1). Quem já consome o ledger (`derive_allowlist()`, checklist, packager) não muda de fonte.
- **`unit_state` (construído) ganha três anexos** por unidade: `perimeter.yaml`, `catalog.yaml`, `graph.yaml` — versionados pelo mesmo mecanismo do `state.yaml`.
- **`verdicts.py` (construído) é o passo 6 do workflow OKF** (§6 do spec). O que falta é o passo 8: cada correção virar lição com fixture.
- **`checklist_builder` (construído) passa a ser instanciado pelo perímetro** em vez de só pelo manifest, e seus motivos passam a vir do vocabulário fechado.

### 0.1 Restrições de missão (o que "eficiente" significa aqui)

O entregável cobrado é o kit Phase I por unidade (árvore carbon-copy, DDR data-entry, checklist, naming), **SLA ≤2 dias Phase I / ≤5 dias relatório completo**, universo ~300 unidades, **um operador**. Consequências arquiteturais:

1. O tempo do Renato é o recurso mais escasso do sistema — toda decisão de design que o coloca no caminho crítico de tarefas de baixo risco é um bug de eficiência.
2. O gargalo histórico por unidade é: (a) aquisição de documentos ≫ (b) rodadas de auditoria > (c) leitura/classificação. A ordem de implementação respeita essa ordem de dor.
3. Phase I é *data entry* na definição da PLM — o rigor máximo (auditoria adversarial completa) é cobrado no fechamento, não em toda rodada intermediária. Rigor tem custo; paga-se onde é cobrado.
4. Custo de IA por unidade é uma métrica de primeira classe (medida no checkpoint Josh B, §3), não uma externalidade.

### 0.2 Estágios × camadas

| Estágio | Consome | Produz para o OKF |
|---|---|---|
| S1 OPEN | L1 `category_to_ddr` (contrato do template) | — |
| S2 SCOPE | L0 identidade + L2 relevância (auto-instanciada da DPU) | `perimeter.yaml` + divergências |
| S3 GATHER | L1 (looks-like por categoria) + vocabulário de exclusão | itens de checklist |
| S4 DROP | L0 + L1 + L2 identidade + L3 lições | `catalog.yaml`, propostas p/ veredito |
| S5 GAP-HUNT | grafo de relações + L2 precedência | novas pendências nomeadas |
| S6 RUN | `category_to_ddr` (feeds) + grafo | células com proveniência |
| S7 REVIEW | L2 precedência + L3 | achados; vereditos → lições |
| S8 SHIP | grafo (nomes de pacote, allowlist) | — |

---

## 1. Decisões de arquitetura (fechadas)

**D1 — Fixtures × invariante "dados de cliente nunca vão ao git".**
Fixture em duas partes. (a) No git: `knowledge/fixtures/<lesson_id>/fixture.yaml` com hash sha256 do(s) arquivo(s), caminho esperado sob `data/fixtures/` (gitignored), página relevante, citação mínima que prova a lição e resultado esperado. (b) Fora do git: os bytes reais em `data/fixtures/`. A suíte roda a fixture quando os bytes existem e **marca SKIP explícito com contagem no relatório** quando não existem (nunca passa em silêncio, nunca falha por ausência). Fixtures sintéticas/redigidas que reproduzam o caso entram inteiras no git.

**D2 — `catalog.yaml`/`graph.yaml` × `evidence_ledger`: uma verdade só.**
O ledger é a verdade; catálogo e grafo são projeções. O registro do ledger ganha os campos OKF (`disposition`, `motivo` do vocabulário, `categoria proposta/confirmada`, `of_record`, `identity_key`); `catalog.yaml` e `graph.yaml` são gerados a cada mutação e gravados com o **round-trip check existente**. Nenhum módulo novo escreve estado próprio.

**D3 — "Conhecimento não contém nome de unidade" × lições unit-scoped.**
O invariante vale para `global.yaml` e `project/*.yaml`; lições de escopo `unit` são quarentena nomeada. Um **linter de conhecimento** roda na suíte: nomes de unidade/lease/poço em `global`/`project`/`ontology`/`taxonomy`/`rules` = FAIL. (O maquinário de *promoção* está adiado — ver Fase 5.)

**D4 — Triagem nunca pula às cegas (novo na v1.1).**
SKIP baseado só em inventário (nome/tamanho) seria decisão por filename — exatamente o que este projeto aboliu. Regra: **todo candidato a SKIP recebe um peek de 1ª página** (uma chamada vision barata) que confirma ou derruba o motivo proposto antes do SKIP valer. SKIP sem leitura nenhuma só por metadado forte (hash idêntico a arquivo já classificado; tipo não-documento). Peeks e SKIPs são contáveis, com motivo do vocabulário, revisáveis em lote na UI. O corte de custo da triagem vem de **não fazer OCR profundo** do que está fora do perímetro — não de não olhar.

**D5 — Veredito por camada de risco (novo na v1.1).**
Confirmação humana universal não escala para ~300 unidades com um operador. Duas camadas:
- **Risco alto — veredito humano obrigatório:** tudo que alimenta WI/NRI, Ownership, Lease Review ou Runsheet (`title_opinion`, `dpu`/`amendment`, `lease_*`, `assignment`/`deed`/`release`/`lien`, `probate_heirship`, `agreement`) e **toda** proposta abaixo do piso de confiança ou marcada `unplaced`/divergência.
- **Risco baixo — auto-confirm com QC por amostragem:** `well_file`, `reference_workbook` e duplicatas por hash, quando acima do piso; amostra aleatória configurável (começa conservadora, ex. 20%) vai à fila humana; erro achado na amostra rebaixa a categoria para veredito obrigatório até novo ciclo.
- **O piso de confiança é calibrado, nunca chutado:** a partir da Fase 4 existe histórico (proposta × veredito). O piso é derivado desse histórico por categoria e re-derivado periodicamente — a lição da `DD_RECONCILIATION_TOLERANCE` (constante inventada que ninguém validou) não se repete.

**D6 — Rigor em camadas (novo na v1.1).**
- **Toda rodada:** gates estruturais (0 FAIL) + source-truth (0 MISMATCH) + round-trip em bytes do disco — inegociáveis, já construídos, baratos.
- **Tier pré-ship / relatório completo:** auditoria adversarial completa (5 lentes independentes, achado atacado antes de adoção) roda **uma vez por marco de entrega**, não a cada rodada intermediária. Phase I é data entry na definição da PLM; o custo das 5 lentes se paga no fechamento.

---

## 2. Mapa OKF → código existente

| Peça OKF | Onde isso vive hoje | Ação |
|---|---|---|
| L0 `ontology/entities.yaml`, `identity_keys.yaml` | Implícito nos modelos Pydantic (`src/dd/manifest.py`) e em disciplina de sessão | **NOVO** YAML mínimo + loader; modelos validam identidade contra as chaves (lease = nº EOG **+** Vol/Pg; unit = DPU book.page + data efetiva; TO = abstract+acres+cert date) |
| L1 `categories.yaml` | Espalhado: roteamento do `intake_router`, `kinds` do `checklist_builder`, mapeamentos hardcoded do `ddr_writer` | **NOVO** YAML; os três módulos passam a ler dele |
| L1 `category_to_ddr.yaml` | Hardcoded no `ddr_writer` | **NOVO** YAML, cruzado no S1 com o template-contrato (nomes de aba por introspecção, nunca hardcode) |
| L2 `relevance.yaml` | `apply_supplemental_scope_filter`, `confirm_coverage`, matching coluna AA | **REFACTOR**: regra declarativa auto-instanciada do perímetro (Exhibit "A" da DPU como autoridade — o S2 do flow spec) |
| L2 identidade | Fuzzy match `SELLER_PARTY_MATCH_THRESHOLD=80`, regexes `_TO_NAME_RE`/`_SELLER_*` | **DEMOTE**: regex → seed lesson; identidade por chave dupla; um campo só = `candidato`, nunca `confirmado` |
| L2 `precedence.yaml` | `resolve_controlling_certification_date`, `select_ownership_basis` (código) | **PARAMETRIZAR**: política vira dado; código executa. **Elimina o fallback silencioso de basis** (gaps #5/#6): opinion mais nova imparseável = achado bloqueante (flow spec §2 r6) |
| L2 `exclusion_reasons.yaml` | Motivos em prosa (3 blank-reasons; REDLINE; "unplaced(reason)") | **NOVO** vocabulário fechado; os 3 blank-reasons viram subconjunto |
| L3 `lessons/` | `lessons.py` planejado (blueprint Fase 3), 7 sementes citadas nos docs | **BUILD enxuto**: project-scoped com fixture; sem promoção/global por ora (D3 + Fase 5) |
| Workflow §6 passos 1–4 (inventário/triagem/leitura) | Não existe triagem; hoje lê-se tudo | **NOVO** `perimeter.py` + `triage.py` com peek (D4) |
| Workflow §6 passo 5 (proposta por LLM) | `title_opinion_parser` (só TOs) + classifier previsto no flow spec §2 | **EXPANDIR**: candidatos = itens do perímetro + categorias L1; saída = schema do flow spec §2 (`of_record`, citação, página) |
| Workflow §6 passo 6 (veredito) | `verdicts.py` + review queue (construídos) | **ESTENDER** à classificação, **por risco** (D5) |
| Workflow §6 passo 7 (efeitos) | `derive_allowlist()`, checklist, packager | **LIGAR** ao grafo: allowlist e nomes de pacote citam relações provadas |
| Workflow §6 passo 8 (aprendizado) | Não existe | **NOVO**: correção de veredito → lição draft + fixture pointer, na mesma transação |

---

## 3. Fases — a fatia fina

Princípio da v1.1: **construir o mínimo que muda o próximo ship, entregar Josh B, medir, e só então decidir o resto com números.** Uma fase = um PR = suíte verde (548+) + testes novos `tests/test_knowledge_*.py`. `knowledge/` entra no git; `data/` continua fora.

### Fase 0 — Fundações (mesmo PR da Fase 1)
- `src/knowledge/loader.py`: carrega e valida todo YAML de `knowledge/` com Pydantic; erro de schema quebra o boot, não a rodada. Cache por hash.
- Linter de conhecimento (D3) como teste da suíte.

### Fase 1-mínima — Vocabulário (dias, não semanas)
**Entrega:** `identity_keys.yaml` + `exclusion_reasons.yaml` + um `entities.yaml` mínimo (as 8 entidades e suas chaves — sem cerimônia ontológica além disso).
**Mudanças:** `evidence_ledger`/`unit_state` exigem chave de identidade completa (ou estado `candidato` com o que falta nomeado); todo motivo gravado vem do vocabulário — prosa livre é erro de escrita.
**Aceitação:** "Bowen A" × "Bowen" e "A-319 Bl.5" × "Bl.12" distintos por construção; zero motivos fora do vocabulário; Bowen A revalida 0 FAIL / 0 MISMATCH do `state.yaml`.

### Fase 2 — Taxonomia enxuta
**Entrega:** `categories.yaml` (`feeds`, `identity_fields`, `relevance_test`, `disposition_default`, **risk_tier** — novo campo, alimenta D5) + `category_to_ddr.yaml`.
**Mudanças:** `checklist_builder` instancia dos categories; `ddr_writer` resolve destino via `category_to_ddr` × template-contrato; `intake_router` para de rotear por convenção própria.
**Aceitação:** loader rejeita categoria sem `feeds`; as ~10 categorias cobrem 100% do corpus Bowen + Maxwell + Josh B; toda célula escrita rastreável a uma categoria.

### Fase 3 — Perímetro + triagem com peek (o maior ganho de custo)
**Entrega:** `src/knowledge/perimeter.py` (o S2 mecânico) + `src/knowledge/triage.py` com D4.
**Mudanças:** IA lê o Exhibit "A" da DPU com prova por página, cruza XREF + Schedule + Well List → `perimeter.yaml` + divergências como achados (o `manifest_builder` vira insumo, deixa de ser autoridade — fecha o gap #1). Relevância se auto-instancia do perímetro. Triagem: inventário completo (hash) → candidato READ/SKIP → **peek de 1ª página confirma todo SKIP** → OCR profundo só nos READ.
**Aceitação:** Josh B: perímetro emite as 4 leases do Exhibit "A" ausentes do XREF como divergência e o conflito Schmidt 427.385×685 como `confirmar_no_cartorio`; nenhum SKIP sem peek ou metadado forte (teste conta); corte de leitura logado (N inventariados / N peeks / N OCR profundo / N SKIP por motivo — sem teto silencioso); 100% dos arquivos com disposição.

### Fase 4-lite — Catálogo + classifier + veredito por risco
**Entrega:** ledger estendido (D2) + projeções + classifier content-first + fila de veredito **por risco** (D5) no Workbench.
**Mudanças:** classifier roda sobre os READ com o schema do flow spec §2; abaixo do piso → `unplaced` proposto, nunca palpite. UI: fila ordenada por confiança com citação inline, 1 clique; risco baixo auto-confirma com amostragem de QC; piso calibrado por categoria a partir do histórico assim que ele existir. Efeitos: veredito → relação no grafo com prova; allowlist e nomes de pacote citam o grafo.
**Aceitação:** re-drop frio do corpus Bowen A reproduz classificações, cert dates e o flag A-226 sem dependência de filename; memo interno pós-cert-date → `of_record: internal`, jamais no Runsheet; allowlist idêntica à atual para Bowen/Maxwell (regressão); erro plantado numa categoria auto-confirm é pego pela amostragem e rebaixa a categoria.

### Fase C — Drive connector (ADIANTADO; em paralelo à Fase 4)
Ataca o gargalo (a) — é a maior alavanca de SLA que existe no plano, por isso não espera o OKF terminar.
**Entrega:** busca/fetch no Drive da PLM por nº de TO, nº de lease, book.page, nome; drop automático no S4; upload do kit com confirmação de 1 clique (fecha o passo 19 do fluxo).
**Aceitação:** dado o `perimeter.yaml` de Josh B, o connector localiza e baixa sem intervenção a maioria mensurável dos itens da checklist que existem no Drive; o que não achar volta como item com termos de busca (regra de ouro do GATHER); log do que foi buscado/achado/não-achado.

### ★ CHECKPOINT — Ship Josh B e medir
Josh B percorre S1→S8 com F1–F4+C ativos. Métricas coletadas (viram baseline do produto):
- horas do operador por unidade (alvo de tendência: caminho para os ≤12 cliques do blueprint);
- custo de IA por unidade (peeks, OCR, classificação, gates);
- rodadas até convergência;
- % de auto-confirm correto na amostragem de QC;
- SLA real vs. ≤2 dias Phase I.
**As fases seguintes só se justificam pelo que esses números mostrarem.**

### Fase 5 — Lições enxutas (condicionada ao checkpoint)
**Entrega:** `lessons.py` com o schema do OKF §5, escopo `unit` e `project` apenas; fixtures no formato D1; migração das 7 sementes (regra do abstract; nomes de arquivo mentem; screenshot exige confirmação visual; condado por nome+data; uplift de JOA não é defeito; branco = fonte indisponível; leases alimentam várias unidades) — cada uma com fixture. Só então os regexes `_TO_NAME_RE`/`_SELLER_*` são deletados do código.
**Explicitamente adiado até existir um 2º cliente:** escopo `global`, UI de promoção, cerimônia unit→project→global. Promoção hoje = editar o YAML de projeto com revisão do Renato; o linter D3 continua garantindo que project/global não contêm fatos de unidade.
**Aceitação:** corrigir uma classificação uma vez muda o próximo drop; toda lição tem fixture; suíte reporta fixtures rodadas/skipped.

### Fase A — `audit.py` como módulo do tier pré-ship (condicionada ao checkpoint)
As 5 lentes + ataque de achados, wired a verdicts/sanções e DD_Audit_Trail — rodando **no marco de entrega** (D6), não a cada rodada.
**Aceitação:** sobre os bytes pré-auditoria de Bowen, encontra o erro de NRI do Tract 2 e o erro de basis do Ownership-Wells, e as próprias correções sobrevivem a re-ataque.

---

## 4. Sequência líquida × roadmap P0–P5 do flow spec

```
F0+F1min → F2 → F3 → (F4-lite ∥ Fase C: Drive connector) → ★ SHIP JOSH B + métricas
        → então, guiado pelos números: F5 (lições) · Fase A (audit) · gap_hunter (P1) · browser agents (P4)
```

- **P0** = F1min + F2 + F4-lite (+ F5 depois). Não começa pelo classifier: sem vocabulário e taxonomia, o classifier não tem cardápio nem respostas válidas.
- **P1 (`gap_hunter.py`)** roda sobre o grafo + precedência — depois da F4. O kickoff de Josh B é o gabarito.
- **P2 (`audit.py`)** = Fase A, no tier pré-ship (D6).
- **P3 (Drive connector)** = **Fase C, adiantada** — a mudança de prioridade mais importante da v1.1.
- **P4 (browser agents RRC/TexasFile)** — segunda alavanca de aquisição; depois do checkpoint, com o mesmo contrato da Fase C (por nome+data, nunca por abstract).
- **P5 (SLA/board)** — **elevado**: o Units board ganha fila + clock + **WIP paralelo** (N unidades em voo; o estado por unidade já permite, falta a orquestração e a visão de fila). Entra junto com o checkpoint, porque as métricas nascem dele.

---

## 5. O que este plano explicitamente NÃO muda

Aritmética de interesses (`fractions.Fraction`; IA propõe, código prova), valores de célula (caso, nunca conhecimento), julgamento de adversidade (veredito humano), gates estruturais/source-truth, round-trip em bytes do disco, packager e formato Phase I, e todos os não-negociáveis do blueprint §7 / flow spec §6. Nenhum matcher é afrouxado para uma fase ficar verde.

**Guarda-corpo anti-regressão a algoritmo:** nenhuma regra L2 decide categoria sem leitura de conteúdo. L2 **delimita e dá vocabulário** (que abstracts, que respostas válidas); a IA lê e propõe com citação; o humano arbitra conforme o risco (D5). Qualquer YAML de regra que comece a "classificar sozinho" é o regex voltando de crachá novo — rejeitar em review.

## 6. Prova de fogo

- **Regressão:** Bowen A e Maxwell A revalidam dos seus `state.yaml` com 0 FAIL / 0 MISMATCH após CADA fase.
- **Ao vivo:** Josh B é o checkpoint — S1→S8 com OKF fatia-fina + connector, com as 5 métricas coletadas (§3). O kickoff de 2026-08-05 é o gabarito do que perímetro + gap-hunter devem produzir mecanicamente.
- **Aprendizado (pós-F5):** uma correção feita em Josh B aparece como lição unit-scoped com fixture; generaliza para project por edição revisada; o YAML de projeto não contém "Josh B" (linter verde).
