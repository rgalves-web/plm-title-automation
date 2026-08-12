# ORDEM DE TRABALHO — PR-9 · Contenção de escrita + gate de WHITELIST de proveniência
_Emitida 2026-08-12 pela sessão Cowork, após verificação externa dos bytes em disco. Supersede a ordem verbal de 11/08 sobre o mesmo tema. Item 0 (contenção e limpeza) executa PRIMEIRO._

**Branch:** `pr9-whitelist-provenance` a partir de `pr4-content-first`. **Nenhuma aba nova antes deste gate verde.**

## Item 0 — CONTENÇÃO E LIMPEZA (executa antes de tudo)

O sistema espalhou arquivos de trabalho pelo repo. Mapa medido hoje no disco:

- `data/units/` (raiz): `_bowen_colddrop/`, `_vision/`, `_josh_b_dpu_ocr.json`, `_josh_b_dpu_vision.json`, `_josh_b_exhibitA_ocr.json`, `_josh_b_exhibitA.json`, `_reconciliation_final.json` — scratch fora de qualquer namespace de unidade.
- `data/units/_josh_b_replay/` (raiz): `_chk_test.xlsx` e ~12 json/yaml de scratch soltos (`_to_a319_*.json`, `_to_a669_*.json`, `lse_reopen.json`, `cell_comparison.json`, `classifications*.json`, `lease_extractions.json`, `dispositions.json`, `inventory.json`) misturados com os entregáveis da rodada (brief, KIT).
- `data/units/_josh_b_replay/corpus/` — **cópia integral de 1.105 arquivos do cliente.** Duplicação de dado confidencial (fere o espírito do invariante 7) e da qual o replay não precisa: o corpus original é read-only por definição, então lê-se in-place.
- `data/units/BOWEN A UNIT/`: 26 `state.v*.yaml` + 2 planos json + 2 truth_run soltos na raiz da unidade. `MAXWELL A UNIT/`: 14 `state.v*.yaml`.

Ordens:

0.1 **Write-roots declarados + manifesto de escrita.** Todo round declara seus write-roots no início e emite `write_manifest.json` ao final listando **todo** caminho escrito. Escrever fora dos roots declarados = exceção, não warning. Scratch só dentro de `<root>/_work/`, apagável por inteiro sem perda. Registrar como **invariante 26** no CLAUDE.md.

0.2 **Limpeza com rede.** Tag no git antes. Depois: scratch de `data/units/` raiz e da raiz do replay movido para `data/_attic/2026-08-12/` (um único lugar, declarado — nada se apaga sem a tag); `state.v*.yaml` antigos para `<UNIT>/versions/`, mantendo `state.yaml` corrente; `corpus/` duplicado **apagado** depois que a fixture do item 1 estiver congelada, e o replay passa a ler o corpus original in-place (read-only, enforçado).

0.3 **Aceitação:** árvore do repo pós-limpeza anexada ao PR; um replay novo roda ponta a ponta e o `write_manifest.json` mostra 100% das escritas dentro do namespace declarado; `git status` sem strays; suíte verde.

## O defeito do artefato, medido nos bytes de hoje

Artefato: `data/units/_josh_b_replay/KIT/DDR - Josh B Unit.xlsx` (mtime 12/08 08:12, o do commit PR-8). Verificação externa com openpyxl, célula a célula contra a `DD_Audit_Trail`:

- Trilha: **581 entradas**. Células não vazias fora da trilha: **759**.
- Sete abas com cobertura de trilha **zero**: Summary (19) · Ownership - Worksheet (347) · Ownership - Wells (105) · Agreements (62) · Unit and Pooling Agreements (11) · PLM Title Review (17) · Disclaimer (2).
- Dados da unidade de amostra do template presentes no artefato: Dorothy Holder Roberts · Willard Kath · ~30× "Top of Bone Spring"/"below top of Wolfcamp" · poços "Two Georges (Bone Spring)" e "Phantom (Wolfcamp)" · WI/NRI 0,9896248 · Unit Size 636.16 · JOA Effective 2011-01-28 com non-consent 300%/300% · PLM Title Review com cert dates "9/12/2018 - 11/17/2024", landman "Ma Chona Adaya" e data 22/11/2024 · Unit and Pooling Effective **2011-01-28** (a real da Josh B é 2012-01-08). Josh B é Barnett, Montague County; Bone Spring e Wolfcamp são Permiano.
- Summary com "--" em Potential Defect(s) e Outstanding Curative Requirements: afirmação de ausência que a própria rodada contradiz (o gap-hunter emitiu 4 itens blocking). "--" não é branco; é "nenhum".
- Checklist contradiz o artefato: Unit and Pooling "Yes" sobre dados da amostra · Ownership Worksheet/Wells, Agreements e PLM Title Review "No — not populated" enquanto as abas exibem valores da amostra · Summary "Yes" com Client vazio.
- Lease Review: 174 órfãs, e nem todas são cabeçalho — B ("Fee"), M/N/P ("No"), O ("Yes (Pooling…)") são dados sem entrada na trilha.
- Runsheet: linhas 8 e 9 (Correction Special Warranty Deed 2019 · Merger Certificate 2021/2024) sem entrada na trilha.

## Itens

1. **Congelar a fixture do defeito ANTES de qualquer nova rodada.** Copiar o artefato de hoje para `tests/fixtures/` intocado. Ele é a prova de que o gate por marcador não basta (invariante 14: toda lição tem fixture).

2. **Baseline de estrutura do template.** Introspecção única do template pristino → `knowledge/templates/ddr_template_structure.yaml` com todo par (aba, célula) que é ESTRUTURA: cabeçalhos, rótulos, texto do Disclaimer. Todo o resto do template é DADO DA AMOSTRA e entra na lista de strip. Anexar contagem por aba para revisão humana. Aceitação: nenhuma coordenada com valor da amostra (exemplos acima) classificada como estrutura.

3. **Strip na origem, não scrub no fim.** O artefato nasce do esqueleto: template menos células de amostra. Atenção openpyxl: `ws.cell(..., value=None)` não limpa nada; atribuir `None` direto na célula. Aceitação: esqueleto salvo, relido do disco, 0 células fora do conjunto de estrutura.

4. **Gate whitelist por proveniência**, em todo caminho de escrita, sobre bytes relidos do disco: toda célula não vazia é (a) estrutura declarada no yaml, com o valor esperado, ou (b) valor com entrada na `DD_Audit_Trail`. Qualquer terceira coisa = FAIL. O scrub por marcador pode continuar como defesa; deixa de ser critério. Aceitação em duas pontas: (i) sobre a fixture do item 1, o gate reporta FAIL com ~759 células e cita Bone Spring e "Ma Chona Adaya" entre elas; (ii) sobre o artefato reconstruído, 0 órfãs.

5. **Checklist derivada dos bytes.** Yes/No calculado do artefato relido + manifesto, nunca escrito literal: "populated" exige pelo menos 1 célula não-estrutura com trilha na aba; instrução com campos nomeados (Summary: Client até Date Submitted) exige os campos nomeados preenchidos. Contradição aba×checklist = FAIL.

6. **Asserção de ausência é derivada.** "--"/"None" em Potential Defects, Outstanding Curative e afins só quando a rodada computou o conjunto vazio. Com o gap-hunter emitindo blocking, a célula ou carrega o resumo com citação ou fica branca com motivo do vocabulário. Estado desconhecido nunca vira conclusão negativa.

7. **Explicar as linhas 8–9 do Runsheet e as órfãs de dados da Lease Review** (Fee, Pugh Y/N, Pooling): ou ganham entrada na trilha com citação de documento real da Josh B, ou saem do artefato. Nenhum "provavelmente" — origem documental ou remoção.

8. **Registrar o invariante 25 no CLAUDE.md** (o 24 do repo já está ocupado pelo contrato do brief): *gate de saída é whitelist por proveniência, nunca blacklist por marcador; célula sem proveniência não se escreve.*

9. **Regressão em leitura:** Bowen A e Maxwell A intocadas (0 FAIL / 0 MISMATCH, `frozen_paths` ativo). Suíte inteira verde (≥ 781). **Anexar ao PR o artefato reconstruído e o relatório do gate — relatório sem artefato não fecha o PR.**

## Fora de escopo deste PR

Escrever Summary/Ownership - Worksheet/Ownership - Wells/Agreements/PLM Title Review com dados reais da Josh B. Isso é o PR-10, que só começa com este gate verde: Summary com a curativa do gap-hunter, Ownership com a aritmética `unit_aggregation`/`Fraction`, e as demais abas — cada valor com trilha, por construção.
