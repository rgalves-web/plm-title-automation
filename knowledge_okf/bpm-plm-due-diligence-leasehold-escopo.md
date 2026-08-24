---
concept: bpm-plm-due-diligence-leasehold-escopo
type: formulario
sources:
- bpm - due diligence (leasehold) (1).pdf, p.1 (secoes A-D)
- bpm - due diligence (leasehold) (1).pdf, p.2 (secoes E-F)
links:
- ddr-template-structure-plm-title-review
- ddr-template-structure-lease-review
- ddr-template-structure-ownership-worksheet
- category-to-ddr-outstanding-curative
unit: ''
confidence: alta — citacao literal das 2 paginas do memorando
---

## BPM: Due Diligence (Leasehold) — o memorando que define o escopo de cada aba do DDR

Documento de 2 paginas, PLM Corporate, 5049 Edwards Ranch Road, Fort Worth, Texas 76109. Camada de texto limpa — ler com `modo=texto`, 2 chamadas. Provavelmente se repete nas 300 unidades; **nao contem fato de unidade nenhum**, so metodologia. Nao serve de fonte para celula de dado; serve para justificar branco e para preencher escopo.

### A. Title Work — dois regimes mutuamente exclusivos (decisao que trava `PLM Title Review!B4`)
- *"For properties with title opinion coverage, PLM will perform supplemental title research from the title certification date to present day."*
- *"For fee properties without title opinion coverage, PLM will typically perform mineral and leasehold title research from patent to present day insofar and only insofar as it pertains to verifying the Seller's specific interest."*
- Leases Federal/State/Tribal: revisar o arquivo da agencia; transfers of operating rights entram no DDR.
- *"all material outstanding title requirements will be documented in the PLM Title Review Tab of the DDR"* — origem canonica de `PLM Title Review!B13`.
- *"All title work will include checks for unreleased liens and encumbrances, along with any outstanding abstracts of judgment or pending litigation"* — origem canonica de `Summary!B12`.

**Consequencia:** sem saber se existe title opinion, nao da para declarar o escopo nem a data inicial da Runsheet. A data de certificacao e o marco zero da runsheet suplementar — e o elo entre `PLM Title Review!B11` e a aba `Runsheet`.

### B. Oil and Gas Lease Review — lista exata do que a aba `Lease Review` deve capturar
*"Lessor, Lessee, Recording Information, Effective Date, Term of Lease, Extension, Royalty Rate, Existing Depth Limitations, and Pugh Clauses."* Mais: confirmar que a lease e valida e held by production; *"Any provisions not in compliance that call into question the validity of the lease should be flagged and noted in the DDR"* — alimenta `Summary!B10 Potential Defects`.

### C. HBP Analysis — origem da coluna `Gaps in Production`
Revisar historico de producao de todos os pocos para confirmar HBP; identificar provisoes disparadas (Pugh, cessation of production) e seu impacto na propriedade das leases; revisar comprovante de pagamento de shut-in e minimum royalty. **Isto liga a aba `Ownership - Wells` (coluna K) a validade das leases da aba `Lease Review`** — nao sao abas independentes.

### D. Summary of Property Ownership
*"The ownership breakdown will be done in the same format as the PSA Exhibit is organized."* — o layout da `Ownership Report` segue o Exhibit do PSA, entao **o PSA e documento necessario**, nao opcional, para ordenar tratos/leases.

### E-F. Mapping; Closing Documents Review and Filing
Mapas sob demanda. Revisao e protocolo de assignments county/state/federal. Fora do DDR propriamente dito.
