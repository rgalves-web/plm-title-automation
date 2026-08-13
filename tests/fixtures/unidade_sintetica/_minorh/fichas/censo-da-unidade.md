---
concept: censo da unidade
type: unidade
sources:
- derivado pelo Examinador nesta sessão
links: []
unit: ''
confidence: exige 60 campos
---

## Censo — unidade_sintetica (JOSH SINTETICO UNIT, Palo Duro County, TX) — **v2** (substitui a v1 de 89)

Dois fatos novos mudaram a conta: (1) veredito do operador em **P1** sobre a Runsheet; (2) chegada da copia do **lease 0999001-004**.

### O que o registro declara (inalterado)
- **5 leases** — Exhibit "A" da DPU: "Five (5) leases in total are pooled into the JOSH SINTETICO UNIT." (dpu - josh sintetico unit - rec.pdf, p.2)
- **2 tratos / 100.00 acres** — Exhibit "C": "Total: 100.00 acres, two (2) tracts." (dpu, p.3)
- **1 poco** — pocos - rrc sintetico.csv, p.1 (1 linha de dados: 42-999-00001)
- **6 instrumentos de registro** — 5 leases (Vol. 100, Pgs. 1-5) + a DPU (Vol. 200, Pg. 50); **nenhum** posterior a June 1, 2011
- **1 requirement** no parecer + **1 conflito de registro** achado na conferencia

### Conta por aba (v2)
| Aba | Linhas | Campos/linha (cabecalho) | Total |
|---|---|---|---|
| Summary | 1 | 4 (B2 Unidade, B3 Condado, B4 Acres, B5 Operador) | 4 |
| Lease Review | 5 leases | 7 (LEASE NO., LESSOR, LESSEE, DATA, REGISTRO, ROYALTY, TERMO) | 35 |
| Ownership - Worksheet | 2 tratos | 4 (TRACT, ACRES, LEASES, SURVEY) | 8 |
| Runsheet | **0** instrumentos + 1 celula de NOTA | 5 por linha; nota e celula de aba | **1** |
| Wells | 1 poco | 6 (API, NOME, OPERADOR, STATUS, PROFUNDIDADE, COMPLETACAO) | 6 |
| Curative | 2 itens | 3 (NO., REQUIREMENT, FONTE) | 6 |
| **TOTAL** | | | **60** |

### Por que a Runsheet caiu de 30 para 1
Veredito do operador (**P1**, gravado como ficha global `runsheet-e-cadeia-suplementar-vazia-quando-nada-e-posterior-a-cert-date`): a Runsheet e cadeia **suplementar** — so instrumentos de registro **posterior** a data de certificacao do parecer controlador. O parecer certifica em **June 1, 2011** ("examined title to the captioned lands as of June 1, 2011 (the certification date)", titulo - original title opinion.pdf p.1) e os 6 instrumentos do corpus sao todos anteriores → exclusao `pre_cert_date`. Aba **vazia com a nota**; conto **1 campo** (a celula de NOTA DA ABA, gravada com citacao). Quem preferir nao contar a nota como campo lera **59** — a diferenca esta declarada aqui, nao escondida.
Os 6 instrumentos seguem na memoria com citacao literal e continuam sustentando Lease Review / Ownership; a exclusao e **so** da Runsheet.

### Cobertura (nao muda o denominador, muda o quanto esta coberto)
- **lease 0999001-004 (Daniel Prado): COMPLETO** — copia lida (0999001-004 (daniel prado) lease.pdf, p.1); os 7 campos gravados do proprio instrumento, confianca alta. Confere integralmente com o Exhibit "A" (Feb 20, 2011; Vol. 100, Pg. 4) — **nenhum novo item de curative**.
- **lease 0999001-005 (Elisa Ramos): 5 de 7** — LEASE NO., LESSOR, LESSEE, DATA, REGISTRO vem do Exhibit "A"; **ROYALTY e TERMO seguem PENDENTES** ate a copia chegar (pedido **PED-004**, que estreita o pedido anterior agora que o -004 chegou).
- **Curative com 2 linhas**: Requirement No. 1 do parecer + o conflito de registro do lease 0999001-003 (Exhibit "A": Vol. 100, Pg. 3; o lease: Vol. 100, Pg. 33). Se o operador nao quiser defeitos descobertos na aba, cai para 57 (ou 56 sem a nota).
