# PLM "Phase I" — Spec de submissão (recebida 31/07/2026)
_Snapshot copiado do projeto Claude (Cowork) em 2026-08-11._

Fonte: mensagem @channel da PLM + zip "1. Landman Submitted" (Submission Example, unidade-modelo: Knox Unit). Vale para TODA submissão de unidade daqui em diante. Prazos: Phase I em 1–2 dias (máx 2), ping no canal p/ revisão; total Phase I + relatório completo: **máx 5 dias por unidade**.

## Estrutura de pastas obrigatória (carbon copy)
```
1. Landman Submitted/
├── Phase I - Checklist.xlsx        ← preenchida com "Yes" em TODAS as linhas
├── Leases/                         ← PDFs SOLTOS (não subpastas por lease)
│   └── "L1 - 368.522 - Sheree Lynn Wylie Roberts OGL.pdf"
│       (L# = nº do lease no Title Opinion; book.page; nome do lessor + "OGL")
├── PLM Report/
│   └── DDR - <Unit Name>.xlsx      (template PLM padrão)
├── Seller Files/                   ← só o que não cabe nas outras (JOA, Farmout, contratos)
├── Title Documents/                ← todo doc lançado no Runsheet, nomeado "book.page" (ex. 399.562.pdf)
├── Title Opinions/
│   ├── Unit Tract 1/               ← subpastas = nºs de tract da Unit Designation
│   ├── Unit Tract 2/  …
├── Unit Designations/              ← DPU original + amendments, nomeados "book.page"
└── Well Files/                     ← do RRC (gis.rrc.texas.gov): W-1, P-12, Well Plat, Production Report
```

## Checklist Phase I — o que preencher no DDR (Phase I = data entry)
- **Summary**: linhas Client → Date Submitted.
- **Ownership - Worksheet**: colunas A (Unit Tract No.) → Q (Tract Depth: To); R–X podem ficar em branco no Phase I.
- **Ownership - Wells**: colunas A (API #) → N (Seller NRI (PSA)). Cols M/N vêm das cols F/G da aba **"AOV Schedule - 7.19.26"** do Project Log (filtrar col C pelo poço).
- **Lease Review**: todas as colunas, p/ leases da EOG.
- **Agreements**: o que conseguir dos JOAs achados nos lease files (title reviewer completa).
- **Unit and Pooling Agreements**: dados da Unit Designation.
- **Runsheet**: pós-certification date do TO — assignments in/out da EOG, OGLs novos da EOG, Deeds of Trust, Liens, Mortgages/Releases, DPUs/amendments.
- **PLM Title Review**: "to the best of your ability".

## EXECUTADO 31/07/2026 — BOWEN A e MAXWELL A reformatados ✓
Pacotes reconstruídos no formato carbon-copy e gravados no disco do Renato em
`<UNIT>\SUBMISSION PLM\` (zips com mesma raiz; extrair juntos = 1 pasta). Verificação: extração
round-trip 94/94 e 28/28 arquivos, md5 100% igual ao build. Árvores antigas (`Bowen A Unit\1. Landman
Submitted` e `SUBMISSION\Maxwell A Unit\...`) podem ser arquivadas/apagadas à mão.

O que mudou em cada pacote:
- **Leases renomeados** "L# - book.page - Lessor OGL" (L# = ordem do Lease Review). Bowen: 31/31 (L4 Brim
  381.762 = via executada; memo gravado referenciado no K1400430). Maxwell: só 5/30 têm cópia (screenshots
  CourthouseDirect → PDF: L23 507.775, L24 507.751, L26 541.32, L27 564.390, L28 566.664); resto nunca
  esteve no Drive do seller — declarado na checklist.
- **Phase I - Checklist.xlsx preenchida** em cada pacote, com coluna Notes (pendências declaradas, não escondidas).
- **Title Opinions em subpastas Unit Tract N**. Bowen: Tract 2 = T-O ORIG A-64 124ac (obtido 30/07) + First
  Supp A-682; Tract 3 = First Supp A-682; Tract 5 = ORIG+SUPP A-227 141.5; Tract 6 = T-O ORIG W. Edwards
  A-227 125ac (obtido 30/07 — cobre Clark/Franklin/Donnell/Orrell, era a pendência "TO do tract Orrell").
  ⚠ Os dois TOs de 30/07 são pós-DDR: integração na análise pendente. Maxwell: Unit Tract 1 (DPU de trato único).
- **Unit Designations** book.page puro: Bowen 479.590 + 493.217; Maxwell 491.160 + 574.830 (só versões gravadas).
- **Title Documents** renomeados book.page puro; Maxwell PNGs → PDF.
- **DDR renomeado** "DDR - <Unit Name>.xlsx" (conteúdo intocado). Obs: aba se chama "Ownership Report" na
  nossa versão do template (exemplo Knox usa "Ownership - Worksheet") — anotado na checklist, não alterado.

## Pendências restantes (declaradas nas checklists)
1. **Well Files RRC** — W-1, P-12, Well Plat: Bowen 1H (42-337-34187) e 2H (42-337-34189); Maxwell #1H
   (42-337-34216) precisa também do Production Report. RRC bloqueado p/ fetch no sandbox — puxar via
   browser (gis.rrc.texas.gov / webapps.rrc.texas.gov: Drilling Permit W-1 query + Completions query).
   Os zips de well files do seller (14738/14761) são Division Order files, não têm W-1/P-12/plat.
2. **Bowen**: ORIGINAL T-O 4/15/2008 (tract A-682 146.5 ac) — segue com seller/PM.
3. **Ownership - Wells cols M/N**: conferir contra aba "AOV Schedule - 7.19.26" do Project Log ATUAL antes de enviar.
4. **Date Submitted**: repreencher com a data real do envio em cada DDR.
