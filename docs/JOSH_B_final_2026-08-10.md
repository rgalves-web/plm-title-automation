# JOSH B UNIT — Encerramento Phase I (2026-08-10) — GABARITO, parte 4 de 4
_Snapshot do projeto Claude. **Estado final da unidade. O supervisor mandou iniciar unidade nova — por isso Josh B é fixture, não alvo vivo.**_

Pacote Phase I submetido. Feedback do supervisor recebido e aplicado no DDR: "note all this in your ddr, add the leases that are memos as missing leases and get a new unit".

## DDR — versão final (Date Submitted 2026-08-10)
Salvo em `JOSH B UNIT\DDR - JOSH B UNIT.xlsx` e `JOSH B UNIT\1. Landman Submitted\PLM Report\DDR - Josh B Unit.xlsx`.

Alterações de 8/10 conforme feedback:
- Potential Defects item 4 renomeado para **MISSING LEASES**: 0220604-021 (Joiner), 0220604-023 (Pendergast), 0220604-026 (C.C. Walker), 0221851-004 (Methodist Home for Children in Waco), 0222981-056 (Choctaw Energy LP) — só memorando registrado; instrumento completo a ser fornecido pelo Seller.
- Outstanding Curative: probates de Ector County com números de causa — **1449 (Yentes), 3734-A (J.C. McConnell), 16915-02 (Nellie McConnell)**. Portal online de Ector pesquisado em 8/10/2026 — sem resultados (índice pré-digital); pedir cópias certificadas ao Ector County Clerk, Odessa ($5 busca/processo, e-mail EctorCountyClerk.Probate@ectorcountytx.gov).
- Section Notes: bloco **MISSING DOCUMENTS (8/10/2026)** com os 4 itens abertos, incluindo RRC W-1/P-12/plat (API 42-337-34773) — site do RRC com application error em todas as tentativas de 8/10; baixar quando voltar.

## Pendências (terceiros)
1. Seller: 5 leases memo (acima)
2. Seller: curativa Stewart/Tract 1 (identidade Marlee=Julia, quitclaims Montie+Lorna, affidavit de não-produção)
3. Ector County Clerk: 3 probates certificados
4. RRC: W-1, P-12, plat — retentar ewaMain.do → W-1 Query → API 33734773 → permit 730771

Missing Files do Project Log (linhas 245–248, amarelas) conferido e intacto no arquivo do time.

Próximo passo: iniciar nova unit.

---

## Nota de arquitetura (2026-08-11)

Este encerramento contém a **regra de negócio que o supervisor da PLM tornou explícita** e que o sistema tem de implementar como dado, não como caso especial:

**Lease cujo único registro é memorando entra no DDR como MISSING LEASE** (Potential Defects), com o instrumento completo pedido ao Seller — *e ao mesmo tempo* o memorando gravado **serve como fonte of-record dos termos** que ele efetivamente declara (ver requisito F2/F4 no `OKF_MIGRATION_PLAN.md`). As duas coisas convivem: o termo que o memorando prova é preenchido e citado; o que ele não prova é pendência nomeada; e a lease aparece na lista de missing leases. É exatamente a diferença entre "célula em branco sem explicação" e "branco declarado com motivo do vocabulário".
