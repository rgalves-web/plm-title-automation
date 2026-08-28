# ORDEM — ETAPA H: CAMADA DE COLETA + PADRÃO DE SUBMISSÃO (lições da Webb B)
**Data:** 2026-08-28 · **Autor:** sessão Cowork · **Aprovada pelo operador em 28/08/2026 ("FAÇA").**
Mesmas regras da arquitetura governante de 23/08: LLM-first puro, a caneta protege bytes e
não decide title, parar em checkpoint, teto de custo por unit. Esta ordem ensina ao sistema
o que a rodada manual da Webb B provou que funciona, para que a **WEBB B UNIT** (pasta nova)
saia com a mesma qualidade da **WEBB B UNIT - Copia**, que fica como gabarito.

## Gabarito

`C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates\WEBB B UNIT - Copia\SUBMISSION PLM\1. Landman Submitted\`

Árvore conferida item a item contra o spec da PLM em 28/08/2026 e considerada pronta para
submissão. Durante o replay ela entra em **quarentena** como qualquer gabarito: o sistema
nunca a lê para decidir valor, só a régua de medição compara no fim. Números do gabarito,
por aba e por pasta, para a régua:

- DDR: 3.050 células escritas com citação, 912 brancas com motivo e dono, 0 divergências.
- Runsheet: **27 itens, todos pós-certificação** (certificações dos TOs: 25/01–08/02/2012).
- `Leases/`: 90 PDFs soltos (85 `L# - book.page - Lessor OGL` + 5 `(Not on Exhibit A) ...`).
- `Title Documents/`: 48 PDFs book.page puro (45 dos 46 instrumentos do runsheet + 3 de
  suporte a defeito). 1 instrumento declarado ausente (Vol 1834 Pg 659, sem imagem no CD).
- `Title Opinions/`: 32 pastas `Unit Tract N` (9 vazias, declaradas), 1 opinião solta na
  raiz (não correlaciona, declarada).
- `Unit Designations/`: 1 arquivo, `1810.202.pdf`.
- `PLM Report/`: só o DDR. `Phase I - Checklist.xlsx`: 15 "Yes", Notes em inglês.
- Missing Files do Project Log: 17 linhas, só documento faltante, rótulos canônicos.

---

## H1 — Escopo vem do spec, e o runsheet é pós-certificação

A maior perda da rodada manual (4 horas) foi abrir cadeia pré-2012 que o spec exclui.
O sistema deve internalizar como **invariante de escopo**, aplicado pelo modelo e conferido
pelo Auditor, nunca por `if`:

1. Antes de qualquer projeção, o modelo lê o spec de submissão e escreve no estado da unit
   um `ESCOPO.md`: o que entra em cada aba, a data de certificação de cada TO, e a regra
   "Runsheet = instrumentos protocolados APÓS a última certificação". Checkpoint: o operador
   aceita o ESCOPO.md antes de o ship começar.
2. Todo item de runsheet carrega a data que o qualifica. Item sem data pós-certificação não
   embarca; vira linha do relatório de fora-de-escopo, não do DDR.
3. Achado fora de escopo não é lixo nem vira trabalho: vai para `FORA DO ESCOPO PHASE I/`
   com um índice de uma página (padrão da Copia), e o ship segue.

## H2 — Camada de coleta (o que o sistema não tinha)

A coleta da Webb B custou ~US$ 33 por 41 documentos (172 páginas) contra ~US$ 63 do caminho
ingênuo. O método, para virar comando (`minorh coletar`, plumbing burro; o que baixar é
decisão do modelo via pull list citada):

**H2.1 Pull list nasce no dia 1.** Ao fechar o rascunho do runsheet, o modelo emite
`PULL LIST - <unit>.csv`: book.page, data, instrumento, grantor, arquivo-alvo `book.page.pdf`,
condado. É a mesma lista que mede completude de `Title Documents/` no fim.

**H2.2 CourthouseDirect — abrir custa US$ 0,50, baixar custa US$ 1,00 a mais.** O caminho
barato: abrir o documento no Historical File Viewer e capturar os canvases já renderizados.
Receita provada (Playwright/CDP na conta corporativa da PLM, com o operador logado):

- Navegação: árvore dynatree em `#tree` → `Cooke` → `Deeds_OPR_ByVolume (1994 to Current)`
  → faixa `1801-1900` → volume → arquivo. **Nome do arquivo**: volumes antigos usam página
  com 4 dígitos (`1822_0310.tif`); volumes recentes usam sem zero à esquerda
  (`2625_179.tif`). Tentar as duas formas antes de declarar ausente.
- Espera de carga: `#lblpath` termina com o nome do arquivo E os canvases do
  `viewerDocuVieware1` existem (filtrar `height > width`; ignorar thumbnails e canvases
  300×150).
- Zoom por API, não por clique: `DocuViewareAPI.GetCurrentZoom('DocuVieware1')` /
  `SetCurrentZoom(...)` no iframe `ctl00_html5ViewerIFrame`, alvo ≥ ~1150 px de largura de
  canvas (≈130 DPI). Guardar **as alturas individuais dos canvases**: elas são as fronteiras
  exatas de página para o corte.
- Captura: compor os canvases num único PNG **e gravar o blob em IndexedDB antes de
  disparar o download**. O Chrome bloqueia downloads automáticos em série SEM AVISO; a
  permissão "Downloads automáticos: Permitir" para o site é pré-requisito (vai no
  PEDIDOS.md), e o buffer garante que nada se perde se o download for barrado.
- **Conferir o disco após o primeiro documento, sempre, antes de rodar a fila.** A rodada
  manual perdeu 40 capturas por pular essa conferência.
- Custo: cada abertura lança US$ 0,50 na fatura da PLM. O comando conta aberturas no ledger
  da unit contra o teto; documento já no disco nunca é reaberto.

**H2.3 PNG → PDF multipágina.** Cortar pelo vetor de alturas dos canvases (nunca por
divisão uniforme: há documentos com páginas de alturas mistas — carta e ofício no mesmo
instrumento). Validação por página, e esta é julgamento do modelo, não `if`: **toda página
de registro do condado abre com o carimbo Doc / Bk / Vol / Pg no topo**. O Auditor amostra
páginas renderizadas e confirma carimbo no topo + book.page do carimbo == nome do arquivo.
Na Webb B essa checagem pegou 4 documentos cortados no meio do texto, recapturados com as
alturas exatas.

**H2.4 O que a coleta não resolve vira PEDIDOS.md**, um item por decisão: documento sem
imagem no CD (ex.: Vol 1834 Pg 659 → TexasFile ou cartório, com preço), permissão de
download, top-up de conta, e-mail de certificada ao cartório (minuta pronta, o operador
envia). O sistema **nunca** insere pagamento ou credencial.

## H3 — Padrão de montagem do pacote (carbon copy, com os detalhes que o spec não escreve)

1. `Title Documents/` = todo instrumento do runsheet, nome `book.page.pdf` **puro** — sem
   sufixo descritivo, sem TIF. Instrumentos de suporte a defeito (fora do runsheet) podem
   ficar, também em book.page puro, declarados na checklist com a conta exata.
2. `Title Opinions/` = uma pasta `Unit Tract N` para **cada** trato da Unit Designation,
   inclusive vazias — vazio declarado na checklist vence pasta inexistente. Uma opinião
   pode (e deve) ser copiada para todos os tratos que cobre. Opinião que não correlaciona
   não ganha pasta inventada ("Tract correlation pending" é não-conforme): fica solta na
   raiz com a razão declarada na checklist.
3. **Ler a opinião antes de aceitar o nome do arquivo.** O arquivo "AMIS 50 AC" da Webb B
   era o T0141078 e cobria 11 parcelas, seis tratos — o nome escondia isso, e a leitura
   derrubou um pedido de opinião que estava aberto havia 18 dias. Regra: a correlação
   trato↔opinião sai do texto da opinião (lista de tracts + anotações de lease na capa),
   nunca do nome do arquivo.
4. `Unit Designations/` book.page puro. `PLM Report/` só o DDR. Checklist com Notes **em
   inglês** (houve regressão em português na rodada manual), declarando lacuna com número:
   "45 of the 46", "9 tract folders empty", nunca advérbio vago.
5. Limpeza é movimento para `_LIXO`, nunca deleção, e a árvore final é varrida contra o
   spec pasta a pasta antes do ping de submissão (a régua compara com a lista do Gabarito
   acima).

## H4 — Disciplina do Missing Files (Project Log do time)

1. Só **documento faltante** entra. Curativa e observação de título vivem nos Potential
   Defects do DDR; a aba Title Defects é do title reviewer.
2. Rótulo canônico primeiro. O censo da planilha (2.044 linhas) usa ~42 rótulos; os que
   cobrem 95% dos casos: `Entire Lease Folder`, `No Lease Folder`, `Not covered by Title
   Opinion`, `Title Opinion(s)`, `Folder exists, but missing lease agreement`, `Full Lease
   (Have Memo Only)`, `Unit Designation`. Descrição livre só quando nenhum serve, curta,
   e sem induzir erro (ex.: "Unit Designation" sozinho sugere que o DPU falta; o certo é
   "Unit Designation - certified copy of recorded Exhibit \"C\"").
3. **Nunca editar linha de outro landman.** Linha desatualizada de terceiro → avisar o dono
   por mensagem, não corrigir na planilha.
4. Append-only ao fim da planilha, clonando o estilo da última linha, data real, coluna
   Landman com o operador.

## H5 — Régua desta etapa (aceite)

Replay da **WEBB B UNIT** (pasta nova, do zero, fichas frias) com H1–H4 no lugar:

- ESCOPO.md aceito no checkpoint 1; runsheet final 100% pós-certificação;
- pull list emitida no dia 1; `Title Documents/` fecha ≥ 45/46 da pull list com carimbo
  validado página a página; custo de coleta ≤ US$ 25 lançado por abertura no ledger;
- árvore final idêntica em forma à do Gabarito (mesma contagem por pasta, nomes conformes),
  sem ler o conteúdo do gabarito durante o ship;
- correlação trato↔opinião derivada do texto das opiniões, com citação por pasta;
- Missing Files: só documentos, rótulos conforme H4, zero edição em linha alheia;
- zero deleção (tudo que sai vai a `_LIXO`), FILES/ intocado, teto respeitado por comando.

## Fora

Nada nas units entregues; a Copia é gabarito em quarentena, não fonte; automação de
pagamento/credencial está proibida em qualquer hipótese; achado que não move esta prova →
BACKLOG.
