---
concept: precedente-lessor-igual-numero-de-lease-diferente-nao-funde
type: veredito
sources:
- PERGUNTAS.md P3 desta unidade + RESPOSTA do operador, 24/08/2026 (aplicar manual-7-3-chaves-de-reconciliacao)
- 0221795-048 (methodist childrens home -oil & gas)/lease memo - rec.tif p.1 (VOL
  732 PAGE 105; 'dated as of the 12th day of November, 2013')
- '0221123-035 (choctaw energy lp-oil & gas)/lease memo-rec.tif p.1 (VOL 608 PAGE
  794; ''Date: January 21, 2012''; Prior Lease 19/09/2008 memo Vol 467 Pg 707)'
- bkv122tx - project log (2).xlsx aba Missing Files janela 3:2
links:
- manual-7-3-chaves-de-reconciliacao
- identity-keys-lease
- precedente-memo-only-missing-lease-em-potential-defects
- manual-10-3-categorias-de-missing-files
unit: ''
confidence: alta
---

## VEREDITO (operador, 24/08/2026) — mesmo lessor + número de lease que não casa = leases DISTINTOS até prova em contrário

**Caso (P3, `_josh_b_replay`)**: o Exhibit "A" do Josh B trazia dois leases sem pasta correspondente, com lessor batendo:
- "0221851/004 METHODIST CHILDRENS HOME, 06/24/2010, **Vol 530 Pg 612**" — corpus tem `0221795-048 (methodist childrens home)`;
- "0222981/056 CHOCTAW ENERGY LIMITED PARTNERSHIP, 07/11/2011, **Vol 581 Pg 14**" — corpus tem quatro pastas Choctaw (0220568-014, 0221122-006, 0221123-035, 0221124-008).

**Resposta**: aplicar `manual-7-3-chaves-de-reconciliacao` — **nunca fundir registros só por nome semelhante**; exigir **pelo menos DUAS evidências convergentes** (número do lease, book/page, data, partes, legal description). Cotejar o recital RECORDED e a data dos instrumentos das pastas candidatas contra a linha do Exhibit. Sem convergência: leases **distintos sem arquivo no corpus** → entram na **pull list do cartório com o book/page do Exhibit**. Não casar em silêncio.

### Cotejo executado nesta unidade (resultado: NÃO FUNDIR)
| Exhibit "A" | Pasta candidata | Instrumento da pasta | Converge? |
|---|---|---|---|
| 0221851/004 — 06/24/2010 — Vol 530 Pg 612 | 0221795-048 | Memorandum recorded **VOL 732 PAGE 105**, lease "dated as of the **12th day of November, 2013**" | **0 de 2** |
| 0222981/056 — 07/11/2011 — Vol 581 Pg 14 | 0221123-035 | Memorandum recorded **VOL 608 PAGE 794**, "**Date: January 21, 2012**", Prior Lease 19/09/2008 memo Vol 467 Pg 707, instrumento estampado "0221123--035" | **0 de 2** |

Evidência independente que fecha: o project log da casa (`bkv122tx - project log (2).xlsx`, aba `Missing Files`) lista, sob **Josh B Unit**, exatamente "0221851-004 | Missing Lease (memorandum only)" e "0222981-056 | Missing Lease (memorandum only)" — a casa reconhece que o lease **não está** no dump.

### Regra operacional
1. Nº de lease é chave; **lessor é atributo**, não chave (o mesmo lessor assina vários leases com a mesma lessee).
2. O teste barato é o memorandum gravado da pasta candidata: **book/page + data** em uma página de OCR resolvem a dúvida por ~1 leitura.
3. Divergência de numeração *com* duas evidências convergentes → mesmo lease, **registrar a divergência** (não silenciar).
4. Sem convergência → linha do Exhibit permanece **PENDENTE** via pedido de cópia certificada; a pasta do corpus é **fora do perímetro** (`exclusion-reasons-fora-do-perimetro`), não fonte.
5. Risco evitado: casar por nome importa ~40 campos de outro trato para dentro do unit.
