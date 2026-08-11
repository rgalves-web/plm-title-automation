# SYSTEM ASSESSMENT — `plm-title-automation`
### Pipeline de Due Diligence / DDR / Submission Packager
**Data:** 2026-07-22 · **Branch:** `maxwell-lessons-hardening` (30 commits à frente de `main`, **não mergeada**) · **Testes:** 494 passando · **Working tree:** limpo

> Documento de handoff para instruir o Claude em sessões futuras. Escrito a partir do estado real do repositório, não de memória. Leia antes de tocar em qualquer coisa do pipeline DD.

---

## 0. TL;DR (leia isto primeiro)

- O **núcleo determinístico é confiável**; a **fronteira com dados não estruturados é frágil** (OCR, nomes de arquivo, LLM, allowlist).
- **Invariantes inegociáveis:** `0 MISMATCH` no source-truth; `0 FAIL` no gate estrutural; nunca inventar arquivo; nunca afrouxar matcher; FILES é somente-leitura; **não rodar Bowen**.
- **Armadilha nº1:** validar um DDR standalone com manifest desatualizado gera **falsos `foreign_unit_leakage`**. Não é defeito — é allowlist incompleta.
- **Armadilha nº2:** OCR de screenshots é ruim → **confirme visualmente** antes de qualquer decisão de identidade.
- **Armadilha nº3:** source-truth é lento (OCR) → rode com janela longa, nunca em timeout curto.
- Última entrega: **Maxwell A Unit v13 = READY, 0 FAIL, 0 MISMATCH.** Pacote de submissão montado em `.../MAXWELL A UNIT/SUBMISSION/`.

---

## 1. Arquitetura e fluxo

Pipeline unit-scoped (começa de um nome de unidade, não de lista de documentos):

```
manifest_builder → title_opinion_parser → unit_aggregation → ddr_writer
    → [GATE OBRIGATÓRIO] ddr_validator (estrutural) + source_truth_check (fonte)
    → submission_packager (monta a pasta de submissão PLM)
```

### Módulos por tamanho (linhas) e papel
| Módulo | Linhas | Papel |
|---|---|---|
| `dd_pipeline.py` | 1450 | Orquestrador `run_dd_pipeline_for_unit`; monta allowlist, source roots, chama o gate e o packager |
| `ddr_validator.py` | 1100 | Gate estrutural. `run_final_validation` (linha ~1057), `validate_ddr` (~956). 100% das células. Sidecar, nunca aba |
| `ddr_writer.py` | 1084 | Preenche o template DDR |
| `source_truth_check.py` | 985 | Re-lê (OCR determinístico) cada documento citado e confirma a célula. `run_source_truth` (~938) |
| `submission_packager.py` | 945 | Monta a árvore de submissão PLM. Plan builder puro + stager de IO |
| `title_opinion_parser.py` | 689 | Parse das title opinions |
| `manifest_builder.py` | 571 | Constrói o `UnitManifest` a partir dos 3 workbooks de referência |
| `unit_aggregation.py` | 547 | Agregação WI/NRI, reconciliação |
| `provenance.py` | 359 | Localiza documento+página por célula, independentemente da extração |

Outros relevantes: `intake_router`, `name_match`, `dpu_parser/source`, `lease_parser/detail`, `agreements_xref`, `agreement_parser`, `tabular_source`, `dd_qa_gates`, `dd_pending`, `protected_values`, `title_case`.

---

## 2. O que está SÓLIDO (pode confiar)

1. **Matemática de interesses em `fractions.Fraction`** — determinística. O LLM **só fornece valores de campo**, nunca faz aritmética.
2. **Gate estrutural obrigatório** — roda em todo write, checa 100% das células (2271/2271 na Maxwell). O relatório é **sidecar** ao lado do DDR e **nunca vira aba** — o gate não pode contaminar o que julga.
3. **`0 MISMATCH` como invariante** no source-truth. Filosofia central: **"correct-and-fewer beats plausible-and-wrong."** Toda célula não confirmável é nomeada, não forçada.
4. **Cinco/seis vias de verificação:** `CONFIRMED`, `CONFIRMED_TRACT_LEVEL`, `ANCHORED_VERIFIED`, `SEMANTICALLY_CHECKED`, `VERIFIED_BY_RULE`, `VERIFIED_BY_MANIFEST`, `UNVERIFIABLE`, `MISMATCH`.
5. **Provenance independente** — documento+página são localizados buscando o texto-fonte, não confiando na extração. Ancoragem exige nome do titular + valor co-localizados na mesma página.
6. **Submission packager sistemático** (ver §5): expande archives por pasta, dedupe multi-nível, filtragem member-level, `SUBMISSION_MANIFEST.txt` com toda exclusão logada e seção **MISSING sempre visível**. **FILES nunca é modificado** (só cópia). Nada é inventado.

---

## 3. FRAGILIDADES e RISCOS (com evidência real)

### 3.1 — Allowlist depende de manifest completo e atual · **RISCO ALTO**
A validação standalone constrói a allowlist a partir do `UnitManifest`. Nesta sessão, o `manifest.yaml` persistido em `data/output/dd/MAXWELL A UNIT/manifest.yaml` estava **desatualizado (run de 7/14)** e **não continha os números XREF das title opinions do v13** (T0140253, T0140319, T0140249, T0140422, T0140555, etc.).
- **Sintoma:** 8 `foreign_unit_leakage` FALSOS na aba `PLM Title Review` ("expected title opinion T0140253 does not cover MAXWELL A UNIT").
- **Causa:** allowlist incompleta, não defeito do DDR.
- **Correção aplicada:** completar `allowlist.title_opinions` com a cadeia de TOs que o próprio DDR declara → **0 FAIL**.
- **Regra:** um `foreign_unit_leakage` isolado é **quase sempre allowlist incompleta**. Confirme antes de reportar FAIL. Não existe manifest v13 canônico persistido — dívida.

### 3.2 — Classificação por nome de arquivo é heurística · **RISCO MÉDIO**
`classify_unit_files` e os regex `_SELLER_*`, `_DPU_NAME_RE`, `_TO_NAME_RE`, `_LEASE_NAME_RE` calibrados para convenções Maxwell/EOG. Outra nomenclatura pode misclassificar **em silêncio**.
- **Mitigação existente:** o que não casa nenhum bucket fica de fora (conservador); MISSING/decisions torna visível. **Mas depende do analista ler o manifesto.**
- **Precedente:** `_TO_NAME_RE` casava a palavra inglesa "to" ("ENCANA TO EOG") e classificava seller como TO — já corrigido exigindo separador (`T-O`/`T O`).

### 3.3 — OCR não-determinístico e mal configurado · **RISCO MÉDIO**
- `tesseract_cmd` **hardcoded em dois lugares** (`source_truth_check.py` e `pdf_reader.py`) para `C:\Program Files\Tesseract-OCR\tesseract.exe`, e **não está no PATH**.
- Screenshots de UI dão OCR ruim: o doc# **96546 (Kramer) não foi lido pelo OCR**; só confirmado por **visualização humana da imagem**.
- **Regra:** para decisões de identidade em imagens, **veja a imagem**, não confie só no texto extraído.

### 3.4 — Source-truth é lento · **RISCO OPERACIONAL**
Re-OCR de todos os documentos citados **estourou timeout de 2 min**. Rode com janela longa (até 10 min) ou em background. Não é bug.

### 3.5 — Cobertura de verificação limitada por DADOS, não por método
Maxwell: **101 verificados, 199 unverifiable** — porque só ~6 leases têm documento completo em disco. É honesto (lacuna de dados), mas a maioria das células de Lease Review não é confirmável. Não trate isso como falha do sistema.

---

## 4. DÍVIDAS TÉCNICAS concretas

- [ ] `tesseract_cmd` duplicado e hardcoded → centralizar num único ponto de config; degradar graciosamente se ausente.
- [ ] Sem manifest v13 canônico persistido → toda re-validação exige reconstrução manual da allowlist.
- [ ] Seller's Files: filtragem member-level infere "partes" do nome do zip; título pobre pode super-excluir (mitigado por logar cada exclusão).
- [ ] Branch `maxwell-lessons-hardening` com 30 commits **não mergeada** → risco de divergência com `main`.
- [ ] ~5 marcadores `best-effort`/`TODO` no código; 21 módulos dependem de regex/filename.

---

## 5. SUBMISSION PACKAGER — estado detalhado

**Entrada:** `package_unit_submission(unit_folder, ddr_path?, unit_name?, unit_dpu_contract?, title_document_files?)`.
**Saída (dentro da pasta do projeto da unidade, nunca em scratch):**
```
<unit_folder>/SUBMISSION/
  SUBMISSION_MANIFEST.txt          ← toda colocação, exclusão/dedupe (com razão) e MISSING
  <Unit Name em Title Case>/1. Landman Submitted/
    1. PLM Report/        o DDR .xlsx
    2. Title Opinions/    1 cópia única de cada TO usada (dedupe por chain-key; archives expandidos em PDF)
    3. Unit Designation/  só o DPU da PRÓPRIA unidade + emendas (foreign excluído); archive expandido, cruft dropado
    4. Leases/            documentos de lease individuais (zips expandidos)
    5. Title Documents/   cada instrumento do runsheet renomeado "volume.page" (ex.: 492.510.png)
    6. Seller's Files/    só o instrumento gravado ("- REC") do assunto de cada contrato; cruft/foreign excluídos
    7. Well Files/        relatório de produção RRC, ou vazio + nota MISSING
```

**Regras já implementadas e testadas:**
- **Title Case** do nome da unidade ("A UNIT" → "A Unit", "A" continua "A").
- **Dedupe de TOs** em 3 níveis: chave exata, arquivo resolvido, e **chain-key** (ORIG/SUPP + sobrenome) — colapsa o mesmo parecer sob nomes diferentes; ORIG e SUPP são mantidos separados.
- **Expansão de archives** em TODAS as pastas de documento, com predicado de cruft compartilhado (`_FILING_CRUFT_RE`: CAF, legal approval, notes, transmittals).
- **DPU próprio** casado por número de contrato OU tokens do nome da unidade; foreign designation **excluída com decisão logada**.
- **Seller's Files member-level:** só "- REC" recorded instrument do assunto do pacote; exclui rascunhos não gravados, contrato/parte estrangeiros, CAF/LAR/notes/DO/bonus/summaries/correspondence. Cada membro excluído é logado. Dedupe de cópias "(2)".
- **Title Documents:** insumos curados do analista vão em `<unit>/SUBMISSION SOURCES/` nomeados `vol.page` (ex.: `492.510.png`); auto-descobertos em re-runs. **FILES nunca tocado.**
- **Idempotente:** re-run limpa o pacote anterior; `.extract` transiente é removido no fim.

**Estado da entrega Maxwell (SUBMISSION):** PLM Report 1 · Title Opinions 9 · Unit Designation 4 · Leases 6 · **Title Documents 3** · Seller's Files 6 · Well Files 0. **MISSING:** só o relatório de produção RRC do MAXWELL A UNIT #1H (não existe em FILES — ~1389 membros de archive varridos).

---

## 6. REGRAS DE OURO para o Claude (obrigatórias)

1. **Nunca afrouxe um matcher para passar teste.** Nunca aceite `MISMATCH > 0`. Célula não confirmada → nomear como unverifiable, não forçar.
2. **Antes de validar DDR standalone**, garanta allowlist completa (cadeia de TOs, contratos, leases). `foreign_unit_leakage` isolado ≈ allowlist incompleta, **confirme antes de reportar FAIL**.
3. **Nunca invente nem coloque arquivo que não identificou.** Liste toda decisão; o ausente vai para MISSING.
4. **FILES é somente-leitura.** Só cópia. Insumos curados → `SUBMISSION SOURCES/`, nunca em FILES.
5. **NÃO rode Bowen.** Não modifique o deliverable sem reportar findings primeiro.
6. **OCR de imagem exige verificação visual** — não confie só no texto extraído para identidade.
7. **Source-truth com janela longa**; reporte o split por método honestamente.
8. **Disciplinas do deliverable:** conjunto de abas == template; relatório do gate é sidecar, nunca aba; datas de submissão são preenchidas no envio, não hardcoded no passado.
9. **Ao commitar:** branch-only; `git diff --cached --name-only | grep -iE '\.(pdf|xlsx|tif|zip|png)$|^data/'` deve estar **CLEAN** (nada de dados de cliente). Mensagem termina com `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## 7. Comandos úteis

```bash
# Suíte completa (esperado: 494 passing)
python -m pytest -q

# Só o packager
python -m pytest tests/test_dd_submission_packager.py -q

# Validação estrutural (rápida) — precisa de allowlist COMPLETA (ver §3.1)
#   run_final_validation(ddr, template_path=..., allowlist=..., source_roots=(), run_source_truth_check=False)

# Source-truth (lento, OCR) — rode com timeout longo
#   run_source_truth(wb, [unit_folder, unit_folder/'FILES'])

# Montar submissão de uma unidade (in-place, na pasta do projeto)
#   from src.dd.submission_packager import package_unit_submission
#   package_unit_submission(unit_folder, unit_dpu_contract="K1400813")

# Tesseract não está no PATH — usar:
#   pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## 8. Caminhos-chave
- Código: `C:\Users\Renato\PURPLE LAND MGMT\plm-title-automation`
- Deliverable Maxwell: `C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates\MAXWELL A UNIT\DDR - MAXWELL A UNIT (PLM) (v13).xlsx`
- FILES da unidade: `...\MAXWELL A UNIT\FILES`
- Template DDR: `C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates\DDR - Template (PLM).xlsx`
- Manifest persistido (⚠ pode estar desatualizado): `data/output/dd/MAXWELL A UNIT/manifest.yaml`

---
*Gerado por auto-assessment. Próxima prioridade sugerida: (a) persistir um manifest v13 canônico para tornar a re-validação reprodutível; (b) centralizar config do tesseract; (c) decidir merge da branch em `main`.*
