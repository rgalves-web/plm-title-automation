# AVALIAÇÃO — o sistema contra o Manual Técnico (v1.0, 16/08/2026)

_Avaliação de 16/08/2026, sobre o branch `sistema-operavel`. O manual consolida
o Slack até 14/08 e se declara normativo (caps. 1–12) e desenho de
implementação (caps. 13–17). Avalio as duas coisas separadamente, porque o
sistema satisfaz muito da primeira e contradiz frontalmente a segunda._

## 1. O conflito que precede tudo: a arquitetura

O cap. 4 do manual prescreve **13 componentes determinísticos** — Lease
Reconciler, Title Chain Engine, Interest Engine, Validator — que são,
componente por componente, **a arquitetura que a ordem de 12/08
(`ARQUITETURA_LLM_FIRST.md`) mandou aposentar**: "nenhuma decisão em Python",
vinte módulos fora do caminho. O repositório hoje tem as duas gerações — a
esteira determinística (`src/knowledge`, `src/dd`, 894 testes, congelada) e a
LLM-first (`src/examinador`, `src/minorh`, provada na sintética).

Pela regra de precedência do próprio manual (§2.2, "prevalece a instrução
mais recente e específica"), o manual (16/08) é posterior ao pivô (12/08).
**Mas essa não é uma decisão minha**: o pivô foi ordem direta do operador, e o
manual foi escrito para outro agente ("Codex") a partir do Slack. As opções:

- (a) o manual REVOGA o pivô → reativar a esteira determinística e completá-la
  contra os caps. 13–17;
- (b) o manual define O QUÊ, o pivô define COMO → os requisitos normativos
  (censo, gates, proveniência, não-fabricação) valem, implementados no
  LLM-first; os "engines" do cap. 4 são desenho, não requisito;
- (c) as duas trilhas coexistem (Codex constrói pelo manual; minorh segue).

A leitura (b) é a única em que o trabalho existente conta quase todo. E o
manual quase a autoriza: o §18.2 exige "regras de negócio em configuração
versionada, não apenas em prompts" — as fichas OKF em `knowledge_okf/` **são**
configuração versionada em git, escritas e consultadas pelo modelo.

## 2. Onde o sistema já cumpre o manual (às vezes antes dele)

O núcleo normativo do manual codifica as mesmas lições que as 12 rodadas de PR
aprenderam a golpes — em vários pontos, palavra por palavra:

| manual | onde o sistema já faz |
|---|---|
| §5.2/§9 "Regra de não fabricação" — campo sem evidência fica nulo, nunca completado por plausibilidade | O princípio fundador: branco declarado com motivo e dono; `record_blank`/`declarar_branco`; invariantes 11/21/25 |
| §9.3 memorandum não comprova royalty; preencher só o que ele prova | `dual_disposition`/`proves_terms` (PR-4/5); disposição `memo_only` |
| §10.2 (S06) documento achado no cartório ≠ "não localizado"; a nota diz só a deficiência remanescente | "Ausência NUNCA se infere de unplaced" (PR-4b); hunt log no `doc_nao_localizado` |
| §10.4 nunca apagar histórico; encerrar como RESOLVED | Trilha DD_Audit_Trail no artefato; exclusões com motivo E dono embarcadas (PR-12, no stash) |
| §16 escalonamento: pergunta, evidência, opções, impacto | `perguntar` → PERGUNTAS.md com candidatos + "o que desempataria"; P1/P2 da prova sintética são exatamente esse formato |
| §2.3 registro de regra com supersessão | Fichas OKF com `links`, fontes e "não pergunte de novo — aplique" (precedente da P1); falta o schema formal DDR-RULE |
| §19.1 "reviewer navega do Summary até a fonte em dois passos" | Citação literal (doc, página, trecho) em toda célula; auditoria de 100% reabre a página citada |
| VAL-007 memo-only sem termo inferido | Coberto e testado na esteira antiga |
| §6.1 project log Coluna E/G, um DDR por unidade | Esteira dd (Bowen/Maxwell/Collin) já opera assim |

O ponto forte é real: **a disciplina de evidência exigida pelo manual é o que o
sistema tem de mais maduro** — e a auditoria de 100% do `minorh ship` vai ALÉM
do manual (o Validator do cap. 15 valida estrutura; o auditor confere se a
página sustenta o valor).

## 3. Lacunas concretas, por gravidade

### Bloqueantes pelo próprio manual (VAL/Block, S02)

1. **Proteção das células azuis (§9.1, §13, VAL-003, AT-10).** O template real
   tem **413 células com fórmula**. `write_workbook` (examinador e minorh)
   escreve valor em qualquer célula, sem mapa de células editáveis, sem hash
   antes/depois, sem bloqueio. É a regra mais reiterada do Slack (S02, 13/08)
   e o sistema não tem NADA dela. A esteira antiga tem o parente
   (`template_structure.py`: STRUCTURE_RULES, proveniência por whitelist), mas
   não hash de fórmula nem bloqueio de escrita.
2. **VAL-001 — todo lease do XREF em Ownership E Lease Review.** É exatamente
   o gate de completude por linha do PR-12 — que está **num stash, fora de
   qualquer branch** desde o pivô. O manual o torna obrigatório de novo.
3. **Empacotamento (§14, VAL-013, AT-16/17/18).** A esteira antiga monta
   `1. Landman Submitted/` (kit_builder); o minorh **não tem packager** — o
   ship para em `_minorh/ship/`. E há um conflito interno novo: a quarentena
   do R1 bloqueia abrir qualquer caminho `*1. Landman Submitted*` — correto
   para o gabarito da Josh B, mas **impede o próprio empacotador de conferir o
   pacote que acabou de montar** em qualquer unidade nova. O padrão precisa
   distinguir "o kit entregue à mão que é gabarito" de "o kit que estou
   montando".
4. **Produção (§12, VAL-009/010, AT-11/12).** Desde a completion, W-1 mais
   recente, e a distinção ZERO_PRODUCTION ≠ MISSING_DATA ≠ PRE_COMPLETION. A
   esteira dd lê os CSVs do RRC (kit_round), mas o detector com essa taxonomia
   não existe em nenhuma das gerações.

### Importantes, não bloqueantes

5. **Lease Universe com as 8 classes (§7.2).** As disposições existentes
   (`memo_only`, `outside_perimeter`, `terms_sourced_instrument_missing`…)
   cobrem parte, mas não mapeiam 1:1 (faltam POST_TO_LEASE, DPU_ADDITION,
   REMOVED_BY_AMENDMENT como classes; a união XREF-duas-abas ∪ DPU ∪
   amendments ∪ TO como população de partida).
6. **Máquina de estados + reviewer (§3.1, §14.4, S11, AT-15).** Nada nas duas
   gerações sabe se há reviewer atribuído nem bloqueia overwrite pós-review.
7. **Ciclo de vida do Missing Files (§10.4).** PEDIDOS.md tem
   aberto/atendido; faltam SEARCHING/REQUESTED/RECEIVED/VERIFIED e
   UNAVAILABLE_CONFIRMED.
8. **Cadeias obrigatórias (§8.2).** Forward/backward por papel (seller,
   unleased owner, post-TO lessor/lessee) — o gap-hunter fazia parte disso por
   juízo; o manual as torna checklist. Nenhuma cobertura sistemática.
9. **Formatação (§13.2, VAL-017).** TNR 10, sem hard returns, auto-height,
   spell-check — `runsheet_style.yaml` cobre um pedaço na esteira antiga;
   minorh nada.
10. **Evento de auditoria (§17.2).** Os ledgers têm citação e sequência, mas
    não before/after com hash, actor e rule_id.

### Fatos novos que o manual entrega de graça

- **Summary: Client = BKV Corp., Acquisition = Project Emirates (§11.2).** Na
  Rodada 1 da Josh B, o Examinador deixou Client/Acquisition em branco e
  PERGUNTOU — o manual é a resposta. Vira precedente OKF imediatamente.
- Disclaimer: ABC, LLC → BKV Corp. Agreements sem JOA: "N/A" + dashes.
- Advisory only fora de Material Outstanding (§8.4, VAL-012).

## 4. Testes de aceite do cap. 19, como o sistema está hoje

| AT | situação |
|---|---|
| AT-04 memo-only sem inferência | **passa** (esteira antiga, testado) |
| AT-05 achado no county ajusta a nota | **passa em espírito** (PR-4b), sem o fluxo de nota automática |
| AT-08 advisory fora de outstanding | não implementado |
| AT-10 bloqueio de célula azul | **falha** — nenhuma proteção |
| AT-11/12 produção zero vs ausente | **falha** — detector inexistente |
| AT-13 quatro TOs, um DDR | passa na esteira antiga (Josh B: 3 TOs, um DDR) |
| AT-15 reviewer atribuído bloqueia overwrite | **falha** — sem estado de reviewer |
| AT-17 ALL CAPS no nome da pasta | **falha** — sem packager no minorh |
| AT-18 runsheet 1:1 com Title Documents | parcial (`title_document_names` na esteira antiga) |

## 5. Recomendação

Tratar o manual como **fonte de requisitos e de precedentes**, não como ordem
de rearquitetura — salvo decisão explícita em contrário do operador:

1. Ingerir os caps. 6–12 e 15 como fichas OKF (regra por regra, com S## como
   fonte e supersessão declarada) — é o Rule Registry do §2.3, no formato que
   o modelo já consulta.
2. Fechar as 4 lacunas bloqueantes na ordem: proteção de fórmula com hash
   (413 células é um invariante barato de verificar), recuperar o gate de
   completude do stash do PR-12, packager + correção do padrão de quarentena,
   detector de produção.
3. Gravar os fatos do §11 (Client/Acquisition/Disclaimer) como precedente
   global — responde a pergunta que a Rodada 1 deixou aberta.
4. Decidir explicitamente a questão de precedência do item 1 — está registrada
   aqui para não ser decidida em silêncio, que é o que o §1.2 do próprio
   manual proíbe.
