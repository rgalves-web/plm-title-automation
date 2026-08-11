# OKF — Ontologia + Knowledge Framework (spec)

**Data:** 2026-08-11 · **Status:** aceito como base de arquitetura · **Audiência:** a IA de programação do `plm-title-automation` · **Companions:** `OKF_MIGRATION_PLAN.md` (como chegar lá a partir do sistema atual), `DDR_JOB_FLOW_SPEC.md` v2.1 (o fluxo que consome esta base), `WORKBENCH_BLUEPRINT.md`, `WORKBENCH_STATUS.md`.

**OKF** = base de conhecimento estruturada que governa a categorização — ontologia + regras + lições, separada do código. O draft parte de uma distinção que hoje não existe no repo: **conhecimento** (reutilizável entre unidades) vs. **caso** (fatos de uma unidade). Hoje os dois estão misturados — parte em regex no código, parte em markdown, parte em memória de sessão. O OKF é a camada onde o conhecimento passa a morar em dado versionado.

---

## 1. As quatro camadas

| Camada | Responde | Formato | Muda quando |
|---|---|---|---|
| **L0 — Ontologia** | Que coisas existem e como se identificam | YAML fixo | Quase nunca |
| **L1 — Taxonomia** | Que categorias de documento existem e o que cada uma alimenta no DDR | YAML por cliente/template | Cliente novo ou template novo |
| **L2 — Regras de decisão** | Como decidir relevância, identidade, precedência e exclusão | YAML por projeto | Descoberta de método |
| **L3 — Lições** | O que aprendemos errando | YAML escopado (unit → project → global) | Toda rodada |

A regra de ouro: **L0–L2 são declarações; L3 são correções**. Uma lição que se repete em três unidades vira candidata a virar regra L2. Uma regra L2 que vale para qualquer cliente sobe para L1/L0.

---

## 2. L0 — Ontologia mínima

O ponto crítico aqui não são as entidades, é a **chave de identidade** de cada uma. Praticamente todo erro caro do projeto veio de identidade ambígua (Bowen A × Bowen; Pendergast × Prendergast; A-319 Bloco 5 × Bloco 12).

| Entidade | Chave de identidade (obrigatória) | Nunca identificar por |
|---|---|---|
| Unit | DPU book.page + data efetiva | Nome ("Bowen A" ≠ "Bowen") |
| Unit Tract | Unit + nº de trato da DPU | Ordem de aparição no TO |
| Survey/Abstract | Abstract + bloco (A-319 Bl. 5) | Só o abstract |
| Lease | nº de lease EOG **+** recording (Vol/Pg) | Nome do lessor |
| Title Opinion | Abstract coberto + gross acres + cert date | Nome do arquivo |
| Instrument | Vol/Pg (ou instrument nº) | Título do documento |
| Well | API | Nome do poço |
| Party | Nome como grafado no instrumento | Sobrenome aproximado |

Relações que o sistema precisa poder afirmar: `Lease —agrupada_em→ Unit` (prova: Exhibit A da DPU), `TO —cobre→ Tract` (prova: abstract + acres), `Instrument —afeta→ Lease|Tract` (prova: descrição legal), `Lease —contribui_acres→ Unit`.

Cada relação carrega **prova obrigatória** (arquivo + página). Relação sem prova não entra no grafo — vira pendência nomeada.

---

## 3. L1 — Taxonomia de categorias

Cada categoria é definida por quatro campos, e não por um nome bonito:

| Campo | Para quê |
|---|---|
| `feeds` | Qual aba/coluna do DDR a categoria alimenta — se não alimenta nada, a categoria não deveria existir |
| `identity_fields` | O que precisa ser extraído para o doc ser identificável |
| `relevance_test` | Pergunta binária que decide dentro/fora da unidade |
| `disposition_default` | READ ou SKIP quando a evidência é fraca |

Rascunho das categorias (derivadas do que já apareceu em Maxwell, Bowen A e Josh B):

| Categoria | Alimenta | Teste de relevância |
|---|---|---|
| `title_opinion` (orig / supp / second supp / DOTO) | Ownership Report, Ownership-Wells O/Q, Lease Review | Abstract + bloco pertence à unidade? |
| `ownership_report` (AFD MOR) | Ownership Report, quando não há TO | Trato consta da DPU? |
| `dpu` + `dpu_amendment` | Unit and Pooling Agreements, Exhibit A | book.page bate com a unidade? |
| `lease_ogl` / `lease_memorandum` | Lease Review (todas as colunas) | Par lease nº + Vol/Pg consta do Exhibit A? |
| `assignment` / `deed` / `release` / `lien` | Runsheet | Data > cert date **e** toca a EOG ou o trato? |
| `probate_heirship` | Runsheet (curativa) | Toca parte na cadeia da unidade? |
| `agreement` (JOA / Farmout) | Agreements | Nomeia a unidade ou o poço? |
| `well_file` (W-1, P-12, plat, production) | Ownership-Wells | API bate? |
| `reference_workbook` (XREF, Well List, Project Log) | Cross-check e manifesto | Projeto correto? |
| `unplaced` | Nada — lista visível com motivo | — |

`unplaced` não é falha: é a categoria que garante que **nada some silenciosamente** (regra operacional nº 6 do blueprint).

---

## 4. L2 — Regras de decisão

Quatro famílias, cada uma com sintaxe própria:

**Relevância** — o filtro que decide se o documento entra no caso.
> Ex.: "Unidade Josh B ⊂ {A-669, A-319 Bl.5, A-319 Bl.6}. Documento com outro abstract no nome ou no corpo → SKIP, motivo `fora_do_perimetro`."

Esta regra é *derivada da DPU*, não escrita à mão: o sistema lê o Exhibit A, monta o conjunto de abstracts da unidade e a regra se instancia sozinha. É a diferença entre uma lista que envelhece e uma que se recalcula.

**Identidade** — como casar documento com entidade.
> "Lease casa só se nº EOG **e** Vol/Pg baterem. Um dos dois sozinho → `candidato`, nunca `confirmado`."

**Precedência** — quando duas fontes discordam.
> "Por trato, controla o TO de cert date mais recente." · "MI vem da seção LEASE ANALYSIS, não MINERALS." · "TO de unidade vizinha vale só se o texto nomear nossa lease como beneficiária."

**Exclusão** — vocabulário **fechado** de motivos. Ninguém escreve motivo em prosa livre; escolhe de uma lista (`fora_do_perimetro`, `trade_de_terceiro`, `pre_cert_date`, `nao_adverso_a_eog`, `doc_nao_localizado`, `pendente_de_terceiro`, `fato_inexistente_no_registro`). É isso que torna a checklist auditável e o SKIP contável.

---

## 5. L3 — Lições

Schema mínimo por lição:

```
id, enunciado, tipo (relevancia|identidade|precedencia|exclusao|leitura),
escopo (unit|project|global), evento_de_origem (o erro que a gerou),
fixture (caso real que a prova), criada_em, promovida_em
```

Duas exigências que fazem a diferença entre um repositório de lições e um arquivo morto:

1. **Toda lição nasce com fixture.** O caso real que a motivou vira teste de regressão. Sem fixture, a lição é opinião. O padrão já existe nos dois casos de TO de unidade estrangeira — é para generalizar.
2. **Promoção é ato explícito.** Lição de unidade só vira global depois de valer em ≥2 unidades e passar por revisão do Renato. Promoção automática por frequência é como se contamina uma base de conhecimento com o viés de um cliente só.

Sementes já disponíveis: regra do abstract; nomes de arquivo mentem; screenshot exige confirmação visual; busca de condado por nome+data; uplift de JOA não é defeito; célula em branco = fonte indisponível; leases alimentam várias unidades.

---

## 6. Workflow de uma rodada

| # | Etapa | Entra | Sai | Quem decide |
|---|---|---|---|---|
| 1 | **Inventário** | Pasta FILES | Catálogo completo de nomes/tamanhos/hashes | Máquina |
| 2 | **Instanciação** | DPU + XREF + Well List | Perímetro da unidade (abstracts, tratos, leases esperadas, APIs) | Máquina |
| 3 | **Triagem** | Catálogo + perímetro + L2 | Lista READ (com motivo) e SKIP (com motivo) | Máquina propõe |
| 4 | **Leitura seletiva** | Só os READ | Texto/OCR | Máquina |
| 5 | **Proposta de categoria** | Texto + L0/L1 | `(categoria, confiança, citação, página)` por arquivo | LLM propõe |
| 6 | **Veredito** | Propostas ordenadas por confiança | `confirmado / corrigido / unplaced` | **Renato** |
| 7 | **Efeitos** | Vereditos | Allowlist derivada, checklist atualizada, nomes de pacote, grafo de relações | Máquina |
| 8 | **Aprendizado** | Cada correção do passo 6 | Lição + fixture | Máquina grava, Renato promove |

O passo 6 é onde o produto se paga: a interface deve deixar o operador percorrer 200 propostas em minutos, porque cada linha traz a citação que a justifica. Confirmar não deve custar leitura de documento — só leitura de evidência.

---

## 7. Estrutura em disco

```
knowledge/                          ← reutilizável, versionado, testado
├── ontology/entities.yaml, identity_keys.yaml
├── taxonomy/categories.yaml, category_to_ddr.yaml
├── rules/relevance.yaml, precedence.yaml, exclusion_reasons.yaml
├── lessons/global.yaml
│         project/BKV122TX.yaml
│         unit/JOSH_B.yaml
└── fixtures/<lesson_id>/           ← 1 caso real por lição
data/units/<UNIT>/                  ← caso, nunca conhecimento
├── perimeter.yaml                  ← abstracts, tratos, leases esperadas (derivado)
├── catalog.yaml                    ← todo arquivo: hash, categoria, disposição, motivo
├── graph.yaml                      ← relações provadas
└── state.yaml                      ← o que já se tem
```

A fronteira `knowledge/` × `data/units/` é a regra estrutural mais importante do draft. Se um fato de unidade vaza para `knowledge/`, a base envenena a próxima unidade. Se uma regra fica presa em `data/units/`, ela se perde.

---

## 8. Invariantes

1. Todo arquivo do inventário termina com disposição e motivo — cobertura 100%, sempre contável.
2. Categoria sem `feeds` não existe.
3. Confiança abaixo do piso → `unplaced`, nunca palpite.
4. Nome de arquivo é *prior fraco*, jamais regra.
5. Toda relação no grafo tem arquivo + página.
6. Toda lição tem fixture; fixture roda na suíte.
7. Conhecimento não contém nome de unidade.

---

## 9. Ordem de implementação

| Fase | Entrega | Por que primeiro |
|---|---|---|
| **1** | `ontology` + `identity_keys` + `exclusion_reasons` | Vocabulário fechado é pré-requisito de tudo; sozinho já mata ambiguidade Bowen/Bowen A |
| **2** | `categories.yaml` + `category_to_ddr.yaml` | Amarra categorização a entregável — elimina categoria decorativa |
| **3** | `perimeter.yaml` derivado da DPU + triagem por relevância | Maior ganho isolado: corta o volume de leitura antes de qualquer OCR |
| **4** | `catalog.yaml` com disposição obrigatória + tela de veredito | Torna a cobertura auditável e transfere a decisão para o operador |
| **5** | `lessons` + fixtures + promoção | Só faz sentido depois que existe um lugar canônico para a correção incidir |

---

## 10. Fora do escopo do OKF

Aritmética de interesses (fica em `Fraction`), valores de célula (ficam no caso), julgamento de adversidade de instrumento (fica com o operador, registrado como veredito), e qualquer coisa que o LLM "acha" sem citação.
