---
concept: layout-workbooks-bkv122tx-well-list-project-log-e-xref
type: layout
sources:
- well list - updated 6.9.26 (1).xlsx p.0, 1:1, 1:3, 2:1
- bkv122tx - project log (2).xlsx p.0, 3:2, 5:1
- lease & mineral schedule 6.9.26 (2).xlsx p.0
- lease to well and contract xref 06-16-2026 (1).xlsx p.0
links:
- custo-xlsx-ilegivel-pelas-ferramentas
- project-log-aba-missing-files-formato
- categories-reference-workbook
- manual-10-missing-files
- manual-12-producao-e-well-data
- escopo-cruzado-quando-xref-e-schedule-nao-estao-no-corpus
unit: ''
confidence: alta
---

## Workbooks do projeto BKV122TX — SÃO LEGÍVEIS por `read_page` com `pagina = "N"` ou `"N:J"`

**Corrige/limita a ficha `custo-xlsx-ilegivel-pelas-ferramentas`**: os .xlsx do projeto abrem normalmente. `pagina 0` lista as abas com nº de linhas e de janelas; `pagina N` lê a aba N; `"N:J"` lê a janela J (200 linhas). O que era ilegível eram os **CSVs** de wellbore/produção do RRC (retornam 0 caracteres).

### `well list - updated 6.9.26 (1).xlsx` — 2 abas
- `Sheet1`, 1.174 linhas, 6 janelas, **ordenada alfabeticamente por WELL NAME**. 30 colunas:
  `OPERATOR | COUNTY | WELL NAME | PAYOUT | WELL # (API) | CURRENT WI | CURRENT NRI | 100%/200%/300%/400%/500% APO WI e NRI (10 col.) | ORRI OIL | ORRI GAS | RI OIL | RI GAS | UMI OIL | UMI GAS | UNIT NAME | WELL STATUS | SPUD DATE | FIRST SALES DATE | COMPLETION DATE | WELL # (interno) | PRIMOLINK`
- `Wells Removed`, 2 linhas (nome + razão). **Checar sempre**: poço removido do escopo não entra em `Ownership - Wells`.
- **Uso**: é a fonte que *declara os poços da unidade* quando o corpus não traz Exhibit de poços — filtrar por `UNIT NAME`. Como está ordenada por WELL NAME, todas as linhas de um unit ficam **contíguas**: 1 janela resolve o denominador de poços. `COMPLETION DATE` costuma vir vazia (→ branco com dono RRC W-2/G-1). Colunas APO vazias quando `PAYOUT = NPO`.
- **Custo**: ~50–54k caracteres por janela. Estimar a janela pela letra inicial do unit antes de ler (janela 1 ≈ A–C, janela 3 ≈ G–K).

### `bkv122tx - project log (2).xlsx` — 8 abas
`Summary` (28) | `Project Log` (995) | **`Missing Files` (388)** | `AOV Schedule - 7.19.26` (1.178) | `Title Defects` (11) | `OneLine w PV10 (BKV)` (940) | `Removed Wells` (154) | `Sheet10` (1.187).
- `Missing Files` colunas: `Unit | Tract/obs | Lease no. | T0 no. | O que falta | Quem reportou | Data`. **É a pull list da própria casa, por unidade** — ler a janela que contém o nome da unidade dá PEDIDOS.md de graça e confirma "memorandum only".
- `Title Defects` colunas: `Defect No. | Unit | Lease(s) Affected | Well(s) Affected | County | Description and Basis of Title Defect | Category of Defect | Represented NRI | Verified NRI | NRI Delta | Comments` — **estava VAZIA** (linhas 1–10 sem conteúdo) em 24/08/2026: não há defeitos pré-declarados para importar; ausência ali **não** substitui a análise da unidade.

### `lease & mineral schedule 6.9.26 (2).xlsx` — 3 abas
`EOG Leases` (63.867 linhas, 320 janelas) | `EOG Owned Minerals and Royalty` (2.450) | `EOG Outleases` (488). É o Schedule do `lease-mineral-schedule-recording-multi-condado`. **Não** está ordenado por nº de lease — localizar a janela com `search_corpus` pelo número do lease antes de ler.

### `lease to well and contract xref 06-16-2026 (1).xlsx` — 2 abas
`Sheet1` (65.471 linhas, 328 janelas) | `Sheet2` (54.842 linhas, 275 janelas). É o XREF lease↔poço↔contrato.

### Custo — aviso
`search_corpus` devolve a lista inteira de arquivos **não pesquisáveis** do corpus (centenas de linhas, ~15k tokens por chamada em corpus grande). Usar apenas quando o alvo é texto e não se sabe a janela; para .xlsx cujo layout já está nesta ficha, ir direto de `read_page 0` para a janela estimada.
