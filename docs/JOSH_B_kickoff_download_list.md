# JOSH B UNIT — Documentos a buscar (2ª rodada) — GABARITO do perímetro/gap-hunter
_Snapshot copiado do projeto Claude (Cowork) em 2026-08-11. Este é o documento que `perimeter.py` + `gap_hunter.py` devem reproduzir mecanicamente (aceitação F3 / PR-6). A 3ª rodada (05/08, noite) está em `JOSH_B_status_2026-08-05.md`._

**Poço:** Josh B Unit #1H · API 42-337-34773 · Montague Co., TX · EOG Resources
**Unidade:** 220,00 ac · DPU Vol. 611, Pg. 526 (inst. 1201931), efetiva 08/01/2012 · **profundidade: só Barnett Shale**
**Status do DDR:** 67 leases mapeadas (Exhibit "A" da DPU), 62 linhas de ownership, runsheet com 23 instrumentos.
**Célula em branco no DDR = documento não localizado. Nada foi estimado.**

---

## 1. BLOQUEADOR — sem isto o DDR não fecha

### 1.1 Title Opinion do Unit Tract 1 (Stewart, 13,05 ac)
Nenhuma das 53 pastas tem TO cobrindo o trato de 50 acres (Tract 1 do Vol. 217, Pg. 491, Deed Records)
na **W. Scarbrough Survey, A-669**. São 5,93% da unidade. Sem ele **não dá para certificar WI/NRI verificados**
do poço (colunas O e Q da aba Ownership - Wells ficam em branco).
- Buscar no Drive: pastas de lease **0221055-001 (Alice Fitzsimmons)** e **0221055-002 (Marlee McConnell Stewart)** — versões completas.
- Se não existir, procurar TO em pastas de outras unidades que tocam o mesmo trato (Josh A Unit, Deaton, South Hills)
  e pedir ao PM/seller. Nome provável do arquivo: `T-O ORIG ... A-669 50AC`.

### 1.2 Well Files do RRC (não estão no Drive — puxar no navegador)
`gis.rrc.texas.gov` / `webapps.rrc.texas.gov`, API **42-337-34773**:
- **Form W-1** (drilling permit) → Total Depth Drilled
- **Form W-2 / G-1** (completion report) → Completion Date, Target Zone
- **Well Plat**
- **Production Report** → Gaps in Production
Essas 4 células da aba Ownership - Wells estão em branco só por isso.

---

## 2. LEASES SEM PASTA NENHUMA NO DRIVE — 17 de 67

### 2.1 As 4 que estão na DPU e **não estão no XREF** (achado do cross-check — prioridade)
Elas existem no Exhibit "A" da DPU, ou seja, foram efetivamente agrupadas na unidade, mas o
Lease-to-Well XREF não as mostra. Ninguém teria baixado sem o cross-check.

| Lease | Lessor | Data | Recording |
|---|---|---|---|
| 0220604-018 | Robert C. Donald, Jr. | 21/01/2010 | Vol. 506, Pg. 386 |
| 0220604-021 | Mallory W. Joiner | 24/01/2011 | Vol. 557, Pg. 240 |
| 0220604-023 | Jane L. Pendergast | 24/01/2011 | Vol. 562, Pg. 895 |
| 0220750-017 | Robert C. Donald, Jr. | 16/02/2010 | Vol. 509, Pg. 137 |

### 2.2 Leases curativas pós-certificação (fecham requirements do TO A-319)
| Lease | Lessor | Data | Recording | Cura |
|---|---|---|---|---|
| 0220604-022 | Kramer Mineral Trust II | 09/03/2011 | Vol. 561, Pg. 757 | **Req. 1** — maior interesse não arrendado (0,08430990) |
| 0220604-024 | Steven Dewitt Walker | 18/04/2011 | Vol. 567, Pg. 170 | Req. 6 (parte) |
| 0222981-056 | Choctaw Energy LP | 11/07/2011 | Vol. 581, Pg. 14 | **Req. 2** (0,00553386) |
| 0221851-004 | Methodist Home for Children in Waco | 24/06/2010 | Vol. 530, Pg. 612 | **maior cura do Tract 2** — 0,30645161 do mineral |

### 2.3 Leases cobertas pelo TO A-319 (termos já preenchidos pelo TO, mas falta o instrumento)
| Lease | Lessor | Recording | TO |
|---|---|---|---|
| 0220604-001 | James J. Hunt | Vol. 429, Pg. 56 | Lease 33 |
| 0220604-005 | John R. Hunt | Vol. 427, Pg. 394 | Lease 2 |
| 0220604-013 | Robin Trause | Vol. 429, Pg. 866 | Lease 22 |
| 0220750-002 | James J. Hunt | Vol. 434, Pg. 695 | Lease 16 |

### 2.4 Série 0220936 (Caswell / Whitecotton — A-811)
| Lease | Lessor | Recording |
|---|---|---|
| 0220936-002 | Elmer Caswell Estate (co-executores) | Vol. 596, Pg. 587 |
| 0220936-003 | Norman Caswell | Vol. 596, Pg. 566 |
| 0220936-004 | Nancy Caswell Laughton | Vol. 596, Pg. 568 |
| 0220936-005 | Gary Caswell | Vol. 596, Pg. 567 |
| 0220936-007 | Teresa Caswell Kelly | Vol. 597, Pg. 787 |

⚠ **Questão a resolver antes de gastar tempo com estas 7:** o Exhibit "C" da DPU mostra a
**Texas Emigration & Land Co. Survey, A-811 FORA do perímetro da unidade**, e a tabela de tratos do
Exhibit "C" só lista 4 tratos (A-669 e A-319). Mesmo assim as 7 leases da série 0220936 estão no
Exhibit "A". Provável que a contribuição em acres seja zero. **Confirmar com o Collin/Trevor** —
se for zero, elas entram na Lease Review declaradas, e não precisam de instrumento.
_(Resolvida na 3ª rodada com prova documental: o source deed Vol. 217, Pg. 491 conveia dois tratos; a série 0220936 é o SECOND TRACT em A-811, fora da unidade, zero acres — ver `JOSH_B_status_2026-08-05.md`.)_

---

## 3. PASTA EXISTE MAS FALTA O INSTRUMENTO DA LEASE — 9

| Lease | Lessor | O que falta | O que a pasta tem |
|---|---|---|---|
| 0220953-005 | Deanne Deaton Trodden | LEASE — royalty e termo | só source deed, ownership report, TO, plat |
| 0221055-002 | Marlee McConnell Stewart | LEASE legível (OCR falhou) | LEASE.TIF + LEASE - REC.TIF — **re-scan ou abrir manualmente** |
| 0220604-026 | Christopher Cayce Walker | LEASE | só COA (change of address) |
| 0220750-018 | Johnny Hunt | LEASE | só "stale check" |
| 0220936-006 | Frances Caswell | LEASE | só letter extension |
| 0220750-008 | Nan Kirkendahl | royalty (termo OK pelo TO) | — é a Lease 36 do TO, gravada depois no Vol. 610, Pg. 245 |
| 0220953-008 | Dale Harrison | royalty individual | grupo Bra-De |
| 0220953-010 | Dorothy McKeen | royalty individual | grupo Bra-De |
| 0220953-011 | Jan Irons | royalty individual | grupo Bra-De |

---

## 4. DIVERGÊNCIAS A CONFIRMAR NO CARTÓRIO / COM O EXAMINADOR

1. **0220604-002 (Dr. Suzanne Schmidt)** — DPU Exhibit "A" e o TO dizem **Vol. 427, Pg. 385**;
   o Lease & Mineral Schedule do seller diz **Vol. 427, Pg. 685**. Confirmar qual.
2. **Lease 19 do TO A-319 (Steve Walker)** — o sumário diz Tract 2 / 1/80, mas o quadro de royalties
   do mesmo TO lista a Lease 19 no Tract 1 a 1/40 (e a Lease 28 separada no Tract 2). Erro interno
   do parecer — resolver com o examinador (liga com o Requirement 10c).
3. **0220953-005 / -006** — TO diz Vol. **514**, Pgs. 412 e 414; o schedule diz Vol. **515**. Confirmar.
4. **0220953-007 (Sporn)** — TO diz Vol. 520, Pg. **2**; schedule diz Pg. **26**. Confirmar.
5. **Grupo Bra-De (0220953-008/-009/-010/-011)** — o TO A-669 trata como **uma** lease
   (Vol. 441, Pg. 275, de 31/03/2008). Os registros da EOG são 4 números de lease com recordings
   no Vol. 555 e data 31/03/2011. Confirmar se o Vol. 555 é ratificação/assignment e não uma nova lease.

---

## 5. REQUIREMENTS DO TO A-319 QUE SEGUEM ABERTOS (curativa, não é download)

- **Req. 4** — deeds do Kramer Mineral Trust II gravados só em Wichita County; arquivar cópias certificadas em Montague.
- **Req. 6 (parte)** — herdeiros de Leonard Lewis Walker III não identificados (1/96 + 1/480).
- **Req. 10a/10c** — quitclaims do James W. Farrell Trust para Steven Ray Walker; e confirmar que o
  "Steve Walker" das Leases 19 e 28 é a mesma pessoa.
- **Req. 15** — identidade lessor/titular de registro nas Leases 1, 2, 8 e 32.
- **Req. 17** — leases anteriores nunca liberadas de registro; obter affidavit of nonproduction.

Já **curados** e documentados no Runsheet: Req. 1, 2, 3, 6 (parcial), 11 e 14.

---

## 6. OPCIONAL — só se o Trevor pedir runsheet certificado

O Runsheet foi montado a partir da DPU + 2 TOs + instrumentos achados nas 53 pastas do seller.
**Não houve busca independente no índice grantor/grantee de Montague County** pós-certificação
(03/03/2010 para o A-669; 09/09/2010 para o A-319). Se for exigido, rodar no TexasFile por
**nome (grantor/grantee) + data**, nunca por abstract.
