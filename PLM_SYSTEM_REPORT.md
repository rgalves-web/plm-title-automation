# PLM Title Automation — Relatório Técnico de Sistema
**Data de referência:** Junho 2026  
**Propósito deste arquivo:** Contexto completo para sessão Claude. Leia antes de qualquer tarefa técnica.

---

## 1. O Que o Sistema Faz

Automatiza a produção de runsheets de cadeia dominial (chain of title) para minerais de petróleo e gás no Colorado. O cliente é a **Purple Land Management (PLM)**.

Dado:
- Uma planilha de registro de documentos do condado (colunas: tipo, grantor, grantee, datas, número de instrumento, livro/página)
- Um pacote ZIP com os PDFs dos documentos

Produz:
- Um arquivo Excel preenchido usando o **template oficial PLM MOR** (Mineral Ownership Report), com abas de runsheet, aba "Ownership - Worksheet" com donos minerais atuais, e relatório de integridade do template
- Artefatos de QA e rastreabilidade completa de cada campo

---

## 2. Stack Técnica

| Componente | Tecnologia |
|---|---|
| UI | Streamlit ≥1.34 |
| Runtime | Python 3.12, Windows 11 |
| PDF text | PyMuPDF (fitz) → pdfplumber fallback |
| OCR | pytesseract + Tesseract 5.4.0 (C:\Program Files\Tesseract-OCR\) |
| Schemas | Pydantic v2 |
| Excel | openpyxl |
| Fuzzy match | rapidfuzz |
| LLM | Anthropic Claude Haiku (claude-haiku-4-5-20251001), via ANTHROPIC_API_KEY em .env |
| Fraction math | fractions.Fraction (aritmética exata, nunca float) |
| Tests | pytest 8.x, 45 testes, 100% passando |

---

## 3. Arquitetura do Pipeline

```
app.py (Streamlit UI)
  └── src/pipeline.py → run_full_pipeline_from_dataframe()
        ├── 1. intake.py            → lê planilha CSV/Excel, cria SourceDocument[]
        ├── 2. dedupe.py            → marca DUPLICATE por instrumento/livro+página
        ├── 3. classifier.py        → rules.yaml → INCLUDE_FULL / INCLUDE_LIMITED / REDLINE / REVIEW
        ├── 4. source_verification  → match ZIPs, OCR via pdf_reader.py
        ├── 5. llm_extraction       → Claude Haiku extrai conveyance + comments
        ├── 6. ownership_analysis   → chain-of-title ledger com Fraction (ownership.py)
        ├── 7. qa.py                → valida; ERROR = hard stop
        └── 8. excel_writer.py      → gera runsheet preenchido + ownership worksheet
```

### Módulos principais (src/)

| Módulo | Responsabilidade |
|---|---|
| `schemas.py` | SourceDocument, QAException, ProjectMetadata, ClassificationStatus, LeaseStatus |
| `pipeline.py` | Orquestra os 8 passos; retorna PipelineResult |
| `classifier.py` | Regras determinísticas (rules.yaml) sem ML |
| `dedupe.py` | Deduplicação por instrumento, livro/página, fuzzy name |
| `source_matcher.py` | Scan do ZIP, matching por instrumento/fuzzy nome |
| `pdf_reader.py` | PyMuPDF → pdfplumber → OCR; configura caminho Tesseract no Windows |
| `llm_extractor.py` | Claude API: extrai conveyance e comments via tool_use; cache em disco |
| `ownership.py` | Chain-of-title ledger; Fraction puro; detecta title gaps |
| `excel_writer.py` | Preenche template MOR; calcula NMA; highlight needs_review |
| `qa.py` | 15 regras de QA; ERRORs bloqueiam exportação |
| `lease_engine.py` | is_oil_and_gas_lease(), infer_lease_status() |

---

## 4. Esquema de Dados Central — SourceDocument

```python
class SourceDocument(BaseModel):
    # Identificação
    source_document_id: str          # DOC-000001...
    document_type: str | None        # "Mineral Deed", "Patent", "Oil and Gas Lease"...
    instrument_number: str | None
    book: str | None
    page: str | None

    # Datas (prioridade: effective_date > instrument_date > recording_date)
    effective_date: date | None
    instrument_date: date | None
    recording_date: date | None

    # Partes
    grantor: str | None
    grantee: str | None

    # Campos preenchidos pelo pipeline
    conveyance: str | None           # Prefixo canônico + descrição legal
    comments: str | None             # Observações de título relevantes
    legal_description: str | None
    lease_status: LeaseStatus | None # ACTIVE | EXPIRED | RELEASED | REVIEW

    # Classificação
    status: ClassificationStatus     # INCLUDE_FULL | INCLUDE_LIMITED | REDLINE | REVIEW | DUPLICATE
    classification_confidence: float | None
    redline_reason: str | None
    review_question: str | None

    # Source verification / OCR
    matched_source_file: str | None
    pdf_extraction_status: str | None  # TEXT_EXTRACTED | OCR_REQUIRED | LOW_CONFIDENCE_TEXT | EXTRACTION_ERROR
    extracted_text_path: str | None
    pdf_text_preview: str | None

    # LLM
    llm_extraction_model: str | None
    llm_conveyance_confidence: float | None
    llm_comments_confidence: float | None

    # Rastreabilidade
    source_trace: dict[str, Any]     # proveniência de cada campo
```

---

## 5. Classificação — rules.yaml

### INCLUDE_FULL (entra no runsheet, alimenta o ledger de ownership)
Patent, Mineral Deed, Warranty Deed, Quit Claim Deed, Oil and Gas Lease, Release of OGL, Probate, Affidavit of Heirship, Distribution Deed, Personal Representative Deed, Decree Affecting Ownership, Death Certificate, Foreclosure/Sheriff's Deed, Assignment of OGL

### INCLUDE_LIMITED (suporte à cadeia)
Tax Deed, Stipulation Affecting Title

### REDLINE (excluído do runsheet)
Easement, Right-of-Way, Surface Use Agreement, Deed of Trust, Mortgage, Lien, UCC, Tax Lien, Survey Monument, Coal/Gravel Lease

### REVIEW (requer revisão humana)
Correction Deed, Scrivener's Affidavit, Partial Release, "Assignment" genérico (sem qualificador OGL), "Bill of Sale" genérico, Reservations genéricas

**Precedência:** DUPLICATE > REDLINE > REVIEW > INCLUDE_FULL > INCLUDE_LIMITED

**Limitação conhecida:** "Assignment" e "Bill of Sale" sem qualificador caem em REVIEW (não INCLUDE) porque sem contexto não é possível determinar se afetam o título mineral. Isso gera ~25% de REVIEW em datasets típicos do Condado de Arapahoe.

---

## 6. Extração LLM — Performance Medida

Smoke test em `4S-64W-15-20260602T114641Z-3-001.zip` (15 documentos elegíveis):

| Métrica | Resultado |
|---|---|
| Registros processados | 15/15 (0 erros de API) |
| **conveyance_llm_pct** | **73.3%** |
| **comments_llm_pct** | **60.0%** |
| Baixa confiança (< 0.85) | 9/15 |
| Tokens usados | ~41k prompt + ~4k completion |

**Por que 73% e não 100%?**
- Documentos com OCR de baixa qualidade (imagens escaneadas em ângulo, resolução baixa) produzem texto ilegível → LLM retorna confidence < 0.60 → campo não preenchido
- Patents governamentais antigos (1880-1920) têm caligrafia manuscrita ilegível
- Assignments genéricos com termos cruzados para outras seções/condados

**Confiança por faixa:**
- 0.85–1.0 (HIGH): texto limpo, lido diretamente. ~45% dos casos.
- 0.60–0.84 (MEDIUM): inferido do contexto, provável. ~28% dos casos.
- < 0.60 (descartado): campo não escrito no registro.

**Modelo em uso:** `claude-haiku-4-5-20251001` (configurável via `PLM_LLM_MODEL` em `.env`)

---

## 7. Chain-of-Title — Módulo ownership.py

### Lógica do ledger

```
fee_ledger: dict[str, Fraction]       # interesse mineral de taxa
royalty_ledger: dict[str, Fraction]   # royalties
wi_ledger: dict[str, Fraction]        # working interests (OGLs ativos)
```

**Regras de processamento (ordem cronológica):**

| Conveyance prefix | Ação |
|---|---|
| `Grant of:` (Patent) | `fee_ledger[grantee] = 1/1` — sem verificação de saldo |
| `ARTI to:` sem "undivided" | Transfere TODO o saldo do grantor; gap se grantor não está no ledger |
| `an undivided X/Y interest to:` | Transfere X/Y; gap se grantor < X/Y |
| `Lease covering:` + ACTIVE | `wi_ledger[grantee] += frac`; não toca fee_ledger |
| OGL EXPIRED/RELEASED | Ignorado |
| Royalty deed | `royalty_ledger[grantee] += frac` |

**Verificação de soma:** `sum(fee_ledger.values())` deve ser `Fraction(1, 1)`. Se não fechar, gera TitleException com instrumento "SUMMARY". Números NÃO são ajustados — título com gap permanece como está.

**Limitações conhecidas:**
- Não rastreia por sub-trato (NE/4 vs W2 etc.) — ledger único por seção. Para títulos com conveyances parciais de tratos diferentes, o ledger pode não fechar = TITLE_EXCEPTION esperada, não bug.
- Quantum incerto (regex não encontra fração) → `needs_review=True`, linha amarela na aba, fração registrada como "?"
- Nomes dos grantors/grantees devem corresponder exatamente entre conveyances (capitalização e pontuação incluídas). Variações de nome (`John Smith` vs `John H. Smith`) podem criar entradas duplicadas no ledger em vez de transferir corretamente.

---

## 8. Template MOR — Aba "Ownership - Worksheet"

**Estrutura do template (linha 3 = cabeçalho):**

| Col | Campo | Descrição |
|---|---|---|
| A | MINERAL OWNER/SELLER | Nome da party com saldo > 0 |
| B | SOURCE DEED | Número do instrumento de origem |
| C | INTEREST TYPE | "Fee - OGM" / "Working Interest" / "Royalty" |
| D | STATUS | "Open" / "Expired" / "Released" |
| E | SECTION | Número da seção (ex: 15) |
| F | TOWNSHIP | Ex: "4S" |
| G | RANGE | Ex: "64W" |
| H | LEGAL DESCRIPTION | Descrição das terras |
| I | TRACT GROSS ACRES | Acres brutos |
| J | MINERAL INTEREST | Decimal 0–1 (ex: 0.5) |
| K | EXECUTIVE RIGHTS | Decimal 0–1 |
| L | RIGHT TO BONUS | Decimal 0–1 |
| M | BURDENS | Decimal (0 se nenhum) |
| N | NMA | Net Mineral Acres = Gross × Interest |
| O | OPEN OF RECORD | Igual ao NMA |
| P | COMMENTS | Notas de revisão |

**Highlight amarelo:** linhas com `needs_review=True` (quantum incerto)

---

## 9. QA — Regras de Validação

### Hard stops (ERROR — bloqueiam exportação)
- DOCUMENT_COUNT_MISMATCH
- MISSING_SOURCE_DOCUMENT_ID
- MISSING_STATUS
- MISSING_REDLINE_REASON
- MISSING_REVIEW_QUESTION
- MISSING_LEASE_STATUS (OGLs sem lease_status)
- DUPLICATE_WITHOUT_CANONICAL
- DUPLICATE_INCLUDED
- TEMPLATE_CHECK_FAILED
- SOURCE_FILE_NOT_MATCHED (quando pacote ZIP está carregado)
- PDF_EXTRACTION_ERROR

### Warnings (não bloqueiam)
- PDF_OCR_REQUIRED
- PDF_LOW_CONFIDENCE
- POSSIBLE_LEASE_TERM_UNRESOLVED
- LEGAL_DESCRIPTION_SECTION_MISMATCH
- LLM_EXTRACTION_FAILED
- LLM_EXTRACTION_LOW_CONFIDENCE

---

## 10. Distribuição Típica — Dataset Arapahoe County (4S-64W-15, 464 docs)

| Status | Contagem | % | Causa raiz |
|---|---|---|---|
| INCLUDE_FULL | ~156 | 34% | Mineral deeds, patents, OGLs |
| REDLINE | ~130 | 28% | Easements, deeds of trust, liens |
| REVIEW | ~113 | 24% | Assignments genéricos, correction deeds |
| DUPLICATE | ~65 | 14% | Mesmo instrumento indexado múltiplas vezes |
| ERRORS | ~0 | 0% | — |

**O número alto de REVIEW (24%) é estrutural**, não um bug:
1. "Assignment" sem qualificador cai em REVIEW por design (regras são conservadoras)
2. Reduzir exigiria tuning do `rules.yaml` ou ativar reclassificação LLM pós-extração
3. Com LLM ativo, conveyance e comments são preenchidos mesmo em REVIEW rows — o analista pode inspecionar e reclassificar manualmente via Review Queue

---

## 11. Cobertura de Testes

| Módulo testado | Arquivo de teste | Casos |
|---|---|---|
| Classifier | test_classifier.py | ~8 casos |
| Deduplication | test_dedupe.py | ~6 casos |
| QA exceptions | test_qa.py | ~9 casos |
| Golden set | test_golden_set.py | ~3 casos |
| Package intake | test_package_intake.py | ~4 casos |
| PDF reader | test_pdf_reader.py | ~4 casos |
| Source verification | test_source_verification.py | ~4 casos |
| LLM extractor | test_llm_extractor.py | ~5 casos |
| Excel writer | test_excel_writer.py | ~3 casos |
| **Ownership ledger** | **test_ownership.py** | **6 casos** |
| **Total** | **10 arquivos** | **45 testes, 100% passando** |

---

## 12. Configuração e Arquivos de Controle

### .env (raiz, nunca commitado)
```
ANTHROPIC_API_KEY=sk-ant-...          # obrigatório para LLM
PLM_LLM_MODEL=claude-haiku-4-5-20251001  # opcional; padrão acima
```

### config/rules.yaml
Regras de classificação determinística. Editar aqui para mudar REVIEW → INCLUDE ou REDLINE → REVIEW sem tocar código.

### config/template_map.yaml
Mapeamento de colunas do template MOR. Aliases permitem múltiplos nomes de cabeçalho para o mesmo campo. Inclui `ownership_columns` para a aba Ownership - Worksheet.

### config/terminology.yaml
Termos de domínio para normalização e busca contextual.

---

## 13. Fluxo de Operação no Streamlit (app.py)

1. **Sidebar esquerda:** carregar planilha de documentos (CSV/XLSX), ZIP de documentos, e template MOR (XLSX)
2. **Botões de pipeline (6 etapas):** cada um muda de estado visual (✅/❌/○) após execução
3. **Review Queue:** lista todos os docs em REVIEW com a pergunta de revisão
4. **QA Exceptions:** log de todos os ERRORs e WARNINGs
5. **Runsheet Preview:** tabela dos campos preenchidos + botão de download antecipado
6. **Confirmação antes de Export All:** checkbox obrigatório após gerar runsheet
7. **Export All:** executa pipeline completo; bloqueia se QA tiver ERROR

---

## 14. Pontos Fracos e Trabalho Pendente

### Alta prioridade
| Item | Descrição |
|---|---|
| Ledger multi-trato | ownership.py usa ledger único por seção; títulos com sub-tratos diferentes podem gerar falsos TITLE_EXCEPTION |
| Variações de nome | "John Smith" vs "John H. Smith" cria entradas duplicadas no ledger |
| OGL sem fraction | OGLs sem fração explícita assumem WI=1 — pode estar errado para OGLs parciais |
| Reclassificação pós-LLM | Depois que LLM preenche conveyance, sistema não reclassifica REVIEW → INCLUDE automaticamente |

### Média prioridade
| Item | Descrição |
|---|---|
| OCR de documentos manuscritos antigos (1880-1920) | Confiança < 0.4, campo não preenchido. Preprocess de imagem (binarização, correção de ângulo) poderia melhorar |
| REVIEW count alto (24%) | Tuning de rules.yaml para tipos de Assignment conhecidos |
| Teste de integração end-to-end | Nenhum teste que rode o pipeline completo com arquivo real |
| Exportação do ownership para Excel | NMA calculado mas BURDENS sempre 0 — precisaria de dados de royalty/override |

### Baixa prioridade
| Item | Descrição |
|---|---|
| Multi-seção | Sistema assume projeto = 1 seção; metadata tem apenas 1 section/township/range |
| UI responsividade | Streamlit bloqueia thread principal durante OCR longo (~2-3 min para 400+ docs) |

---

## 15. Como Rodar

```powershell
# Raiz do projeto
cd "c:\Users\Renato\PURPLE LAND MGMT\plm-title-automation"

# Ativar (se venv configurado) — ou usar python direto
python -m streamlit run app.py
# → http://localhost:8502

# Smoke test LLM
python scripts/smoke_llm.py data/input/document_packages/<arquivo>.zip

# Testes
python -m pytest -q
```

**Porta padrão:** 8502 (configurada em .streamlit/config.toml)  
**Upload máximo:** 2 GB (maxUploadSize = 2048)  
**Tesseract:** `C:\Program Files\Tesseract-OCR\tesseract.exe` — hardcoded em `src/pdf_reader.py:28` como fallback do PATH

---

## 16. Estrutura de Saída

Cada execução cria `data/output/<project>_<county>_<timestamp>/`:

```
document_register.xlsx
classification_results.xlsx
redline_rows.xlsx
review_required.xlsx
extraction_coverage.json          # % de campos preenchidos por fonte
ownership_entries.json            # ledger final + title_exceptions
processing_summary.json           # totalizadores + métricas de cada etapa
QA_EXCEPTION_LOG.xlsx
08_source_match_report.xlsx
09_pdf_extraction_report.xlsx
10_review_checklist.xlsx
<project>_preliminary_runsheet_<ts>.xlsx   # entregável final
<project>_preliminary_runsheet_<ts>_template_integrity_report.json
QA_internal/
  source_files/                   # PDFs extraídos do ZIP
  extracted_text/                 # .txt de cada PDF
  llm_cache/                      # cache JSON das respostas LLM
```

---

## 17. Glossário de Termos de Domínio

| Termo | Significado |
|---|---|
| MOR | Mineral Ownership Report — formato de entrega padrão PLM |
| Runsheet | Planilha de cadeia dominial cronológica |
| INCLUDE_FULL | Documento que afeta título mineral; entra no runsheet e no ledger |
| REDLINE | Documento irrelevante para título mineral (excluído) |
| ARTI | "All right, title and interest" — transferência da totalidade |
| Chain of title | Sequência cronológica de conveyances que rastreia a propriedade mineral |
| Working Interest | Interesse operacional de uma OGL ativa (lessee) |
| Fee interest / OGM | Interesse de taxa em oil, gas and minerals (lessor/grantor) |
| NMA | Net Mineral Acres = Gross Acres × Mineral Interest decimal |
| Title exception | Gap, conflito ou ambiguidade detectada na cadeia dominial |
| Reception number | Número de registro do condado (equivalente a "instrumento") |
| Grantor/Grantee | Quem transfere / quem recebe o interesse |
