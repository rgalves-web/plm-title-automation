# JOSH B UNIT — Documentos a buscar (3ª rodada) — GABARITO, parte 2 de 4
_Snapshot do projeto Claude. Sequência do gabarito Josh B: kickoff (2ª rodada) → **este (3ª rodada)** → submissão 06/08 → encerramento 10/08. O replay do sistema é comparado contra os quatro._

**Poço:** Josh B Unit #1H · API 42-337-34773 · Montague Co., TX · EOG Resources
**Unidade:** 220,00 ac · DPU Vol. 611, Pg. 526 · efetiva 08/01/2012 · profundidade: só Barnett Shale
**Lease Review nesta rodada: 85% preenchida** (era 68%). Restam 12 leases das 67.
**Regra:** célula em branco = documento não localizado. Nada foi estimado.

---

## O QUE MUDOU NESTA RODADA (2 achados que fecham perguntas abertas)

**1. Existe um title opinion que ninguém tinha aberto.**
`T-O ORIG A-811 TEL CO SURVEY 3422 50AC.PDF` está dentro das pastas 0220936-002/-003/-004/-005/-007.
É um Original Title Opinion da Harris Finley & Bogle, 30/12/2011, certificado em 05/10/2011.
Dele saíram os termos das 6 leases da série Caswell — inclusive a **0220936-006 (Frances Caswell)**,
cuja pasta não tem o instrumento.

**2. O "conflito de survey" A-669 x A-811 está resolvido — e a má notícia é que o bloqueador continua.**
O source deed (Warranty Deed 04/01/1940, **Vol. 217, Pg. 491**, Hughes → Yentes) conveia **DOIS** tratos de 50 acres:
- **FIRST TRACT** — 50 ac na **Wm. Scarbrough Survey, A-669** → é o **Unit Tract 1** da DPU → leases Fitzsimmons (0221055-001) e Stewart (0221055-002).
- **SECOND TRACT** — 50 ac na **Seção 3422, T.E.&L. Co., A-811** → é o que o title opinion novo cobre → leases Whitecotton + Caswell (série 0220936).

Consequências:
- A série **0220936 está FORA do perímetro da unidade** e contribui **zero acres**, mesmo constando do Exhibit "A". Não precisa de mais nada dela.
- O **Unit Tract 1 continua sem title opinion**. O A-811 não serve.

---

## 1. BLOQUEADOR — sem isto o DDR não fecha

### 1.1 Title Opinion do Unit Tract 1 (A-669, 50 ac — FIRST TRACT do Yentes)
São 13,05 ac = 5,93% da unidade. Sem ele as colunas **O e Q da aba Ownership - Wells** (WI e NRI verificados do wellbore) não podem ser certificadas.

**Onde procurar, nesta ordem:**
1. **Drive, pastas de outras unidades que tocam o mesmo trato** — Josh A Unit, Josh Unit, Deaton / Deaton A, South Hills, McCartney A. Foi assim que o A-811 apareceu (estava na pasta de lease, não na de unidade).
   Nome provável: `T-O ORIG ... SCARBROUGH ... A-669 ... 50AC`.
2. **Pastas 0221055-001 e 0221055-002** — reconferidas: idênticas às da 1ª rodada (mesmo md5 de conteúdo).
3. **Se não existir**: pedir ao Collin/Trevor. É plausível que a EOG nunca tenha mandado examinar esse trato (era o menor da unidade).

### 1.2 Well Files do RRC — não estão no Drive, puxar no navegador
`webapps.rrc.texas.gov` e `gis.rrc.texas.gov`, **API 42-337-34773**:

| Documento | Onde | Preenche no DDR |
|---|---|---|
| Form W-1 (drilling permit) | Drilling Permit (W-1) Query | Total Depth Drilled (col. G) |
| Form W-2/G-1 (completion) | Completion Query | Completion Date (col. I) e confirma Target Zone |
| Well Plat | anexo do W-1 / GIS Viewer | pasta Well Files do pacote |
| Production Report | Production Data Query | Gaps in Production (col. K) |

---

## 2. LEASES QUE NÃO TÊM PASTA NENHUMA NO DRIVE — 8

### 2.1 Na DPU mas ausentes do XREF (prioridade — só aparecem no cross-check)
| Lease | Lessor | Data | Recording |
|---|---|---|---|
| 0220604-018 | Robert C. Donald, Jr. | 21/01/2010 | Vol. 506, Pg. 386 |
| 0220604-021 | Mallory W. Joiner | 24/01/2011 | Vol. 557, Pg. 240 |
| 0220604-023 | Jane L. Pendergast | 24/01/2011 | Vol. 562, Pg. 895 |
| 0220750-017 | Robert C. Donald, Jr. | 16/02/2010 | Vol. 509, Pg. 137 |

### 2.2 Leases curativas (fecham requirements do T-O A-319)
| Lease | Lessor | Recording | Cura |
|---|---|---|---|
| 0220604-022 | Kramer Mineral Trust II | Vol. 561, Pg. 757 | **Req. 1** — maior interesse não arrendado (0,08430990) |
| 0220604-024 | Steven Dewitt Walker | Vol. 567, Pg. 170 | Req. 6 (parte) |
| 0221851-004 | Methodist Home for Children (Waco) | Vol. 530, Pg. 612 | **maior cura do Tract 2** — 0,30645161 do mineral |
| 0222981-056 | Choctaw Energy LP | Vol. 581, Pg. 14 | **Req. 2** (0,00553386) |

> Se a pasta não existir no Drive, o instrumento gravado resolve: TexasFile / CourthouseDirect, busca por **nome (grantor/grantee) + data**, nunca por abstract.

---

## 3. PASTA EXISTE MAS FALTA O INSTRUMENTO — 4 (era 9)

| Lease | Lessor | O que a pasta tem | O que falta |
|---|---|---|---|
| 0220604-026 | Christopher Cayce Walker | só COA (change of address) | a lease inteira |
| 0220750-018 | Johnny Hunt | só "stale check" | a lease inteira |
| 0220953-005 | Deanne Deaton Trodden | source deed, ownership report, T-O A-669 155ac, plat | a lease inteira |
| 0220750-008 | Nan Kirkendahl | T-O A-319 + carta de extensão | royalty, shut-in, pooling, continuous drilling |

**Nota sobre a Kirkendahl:** o PDF `NANA KIRKENDAHL LSE 0220750-008.PDF` **não é a lease** — é a carta de 01/03/2011 em que a EOG exerce a opção de estender o prazo por 2 anos, pagando $447,20 ($400/acre mineral líquido). Serve para o Runsheet, não para a Lease Review. O instrumento está gravado no **Vol. 610, Pg. 245**.

**As 5 que saíram da lista** (recuperadas por OCR nesta rodada): Marlee Stewart (0221055-002), Frances Caswell (0220936-006, via T-O A-811), e os royalties individuais de Dale Harrison, Dorothy McKeen e Jan Irons (grupo Bra-De — todas 1/5).

---

## 4. DIVERGÊNCIAS A CONFIRMAR (não são download — são conferência)

1. **0220604-002 (Dr. Suzanne Schmidt)** — DPU e T-O dizem **Vol. 427, Pg. 385**; o Lease & Mineral Schedule do seller diz **Vol. 427, Pg. 685**. Um dos dois está errado.
2. **Lease 19 do T-O A-319 (Steve Walker)** — o sumário põe no Tract 2 a 1/80; o quadro de royalties do mesmo parecer põe no Tract 1 a 1/40. Erro interno do parecer; liga com o Requirement 10c.
3. **0220953-005 / -006** — T-O diz Vol. **514**, Pgs. 412/414; o schedule diz Vol. **515**.
4. **0220953-007 (Sporn)** — T-O diz Vol. 520, Pg. **2**; schedule diz Pg. **26**.
5. **Grupo Bra-De (0220953-008/-009/-010/-011)** — o T-O A-669 trata como **uma** lease (Vol. 441, Pg. 275, de 31/03/2008); a EOG registra 4 leases com recordings no Vol. 555 e data 31/03/2011. Confirmar se o Vol. 555 é ratificação/assignment e não lease nova.

---

## 5. REQUIREMENTS DO T-O A-319 AINDA ABERTOS (curativa, não download)

- **Req. 4** — deeds do Kramer Mineral Trust II gravados só em Wichita County; arquivar cópias certificadas em Montague.
- **Req. 6 (parte)** — herdeiros de Leonard Lewis Walker III não identificados (1/96 + 1/480).
- **Req. 10a/10c** — quitclaims do James W. Farrell Trust para Steven Ray Walker; confirmar que o "Steve Walker" das Leases 19 e 28 é a mesma pessoa.
- **Req. 15** — identidade lessor/titular de registro nas Leases 1, 2, 8 e 32.
- **Req. 17** — leases anteriores nunca liberadas de registro; obter affidavit of nonproduction.

Já curados e documentados no Runsheet: Reqs. 1, 2, 3, 6 (parcial), 11 e 14.

---

# ADENDO 05/08/2026 (noite) — REGRA DO ABSTRACT + 4ª rodada não rendeu

## A regra que evita as buscas erradas

O **survey/abstract** é o filtro definitivo. A Josh B Unit está inteira dentro de apenas dois:
- **A-669** — W. Scarbrough Survey (Unit Tract 1)
- **A-319** — Hill County School Land Survey, **Blocos 5 e 6** (Unit Tracts 2, 3 e 4)

**Qualquer pasta ou title opinion cujo nome traga outro abstract está fora da unidade.** Já apareceram e foram
descartados: A-730 (Titus CSL), A-811 (T.E.&L. Co.), A-1100 (E. L. Lehman), A-257, A-1148, A-254 (ETRR),
e até **A-319 Bloco 12** — mesmo abstract, bloco errado.

Antes de abrir qualquer pasta nova: olhe o abstract no nome do arquivo. Não sendo A-669 ou A-319 Blocos 5/6, pule.

## Por que buscar por nome do lessor não funciona aqui

Os lessores têm leases em várias unidades. Buscar "DONALD" trouxe 0126714-182, 0190087-018 e 0190427-098
(todas A-730); buscar "CHOCTAW" trouxe 0220568-014, 0221122-006, 0221123-035 e 0221124-008 (todas A-730);
buscar "PRENDERGAST" trouxe Betty Joyce Caswell Prendergast (A-730) — que **não é** a Jane L. Pendergast
da nossa lease, nem tem o mesmo sobrenome.

**A chave é o par: número de lease EOG + recording (volume/página).** Sem os dois batendo, não é a nossa.

## As 6 leases que ainda faltam — identificação definitiva

| Lease EOG | Lessor exato | Recording | Abstract esperado |
|---|---|---|---|
| 0220604-018 | Robert C. Donald, Jr. | Vol. 506, Pg. 386 | A-319 Blocos 5/6 |
| 0220750-017 | Robert C. Donald, Jr. | Vol. 509, Pg. 137 | A-319 Blocos 5/6 |
| 0220604-021 | Mallory W. Joiner | Vol. 557, Pg. 240 | A-319 Blocos 5/6 |
| 0220604-023 | Jane L. Pendergast | Vol. 562, Pg. 895 | A-319 Blocos 5/6 |
| 0221851-004 | Methodist Home for Children (Waco) | Vol. 530, Pg. 612 | A-669 155ac (Tract 2) |
| 0222981-056 | Choctaw Energy LP | Vol. 581, Pg. 14 | A-319 Blocos 5/6 |

## O que a 4ª rodada trouxe (12 itens, nenhum aproveitável)

Todos fora da unidade: 0126714-182, 0190087-018, 0190427-098 (Donald, A-730); 0220563-003, 0220570-005,
0224167-017 (Prendergast, A-730); 0220568-014, 0221122-006, 0221123-035, 0221124-008 (Choctaw, A-730);
T0140692 (A-257), T0141177 e T0141636 (A-730), T0141702 (A-1148), T0141504 (A-669/A-1100 — cadeia
Giles/McMinn/Stephens), T0141729 (A-319 **Bloco 12**, lease de 2012 para Newark E&P — outro trato).

**Pendências: as mesmas.** Nada novo entrou, nada novo saiu.
