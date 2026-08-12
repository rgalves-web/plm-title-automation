---
concept: custo-legibilidade-do-corpus-montague-eog
type: custo
sources:
- 'Tentativas de leitura no corpus da unidade JOSH B UNIT (Montague County): read_page
  em .tif, .pdf, .html, .csv, .png'
links:
- exclusion-reasons-captura-de-tela
- formulario-eog-declaration-of-pooled-unit-montague
- sources-rrc
unit: ''
confidence: alta — medido na unidade Josh B
---

## O que da para ler neste corpus, e por qual modo (medido)

- **.tif (a maioria: leases, LARs, ownership reports, source deeds, unit decs)**: sem camada de texto — `texto` devolve vazio. Use `ocr`. Funciona bem em corpo de texto corrido; **destroi tabelas** (Exhibit "A" de DPU sai com linhas fundidas e colunas perdidas). Para tabela e plat, `imagem`.
- **.pdf de title opinion (Harris, Finley & Bogle)**: tambem **sem camada de texto** — `texto` devolve vazio, use `ocr`. A pagina 1 ja entrega o que o DDR precisa: escritorio, data da opiniao, "ORIGINAL/FIRST SUPPLEMENTAL TITLE OPINION", descricao das terras por tract com Vol/Pg do deed de origem, a data de certificacao ("as of <data>, the Land was owned") e o quadro SURFACE/MINERALS com quem esta **unleased**.
- **.html (e-mails exportados: "release ...", "... owns no interest", "decimal interest ...")**: `texto` devolve **vazio**. Nao foram legiveis por nenhum modo testado. Sao justamente os itens de curative — trate como pendencia, nunca como fato, e cite so o nome do arquivo.
- **.csv (`wellborequeryresults_reportcsv`, `specificleasequery_prodandtotaldisp_reportcsv`)**: `texto` vazio e `ocr` estoura (`UnidentifiedImageError`). **Nao gaste chamada**; o mesmo conteudo esta nos PNGs de tela do RRC.
- **.png "captura de tela ..."**: mistura. As **grandes (>1 MB)** sao paginas de documentos digitalizados; as **pequenas (7-60 KB)** sao ou lixo de UI em portugues (formularios "Envio de documentos", listagem de pasta do Windows — ignore) ou **telas do RRC Online System**, que sao ouro barato: `Lease Detail/Wellbore` (API, lease no., district, field, operador, API depth), `Wellbore Data by API No.` (drilling permit, internal completion date) e `Specific Lease Query` (producao mensal). Leia em `imagem`.

**Ordem eficiente para abrir uma unidade nova:** (1) DPU recorded da pasta `k14xxxxx` — ocr pp. 1-2 e 5, imagem pp. 3-4 e 6; (2) telas pequenas do RRC em `imagem`; (3) title opinions `t-o ...pdf` em `ocr`, pagina 1; (4) cessoes `asmt ...rec.tif` em `ocr`, pp. 1-2. Isso fecha Summary, Unit and Pooling, Ownership - Wells, Runsheet e PLM Title Review sem tocar nas centenas de TIFFs de lease.
