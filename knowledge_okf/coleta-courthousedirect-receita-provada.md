---
concept: coleta courthousedirect receita provada
type: regra
sources:
- ordem CODE_INSTRUCTIONS_ETAPA_H (28/08/2026) — lições da rodada manual da Webb B
- '[[cartorio-courthousedirect-arvore-e-busca]]'
- '[[protocolo-captura-viewer-cartorio]]'
links: []
unit: ''
confidence: ''
---

## H2 — Coleta no CourthouseDirect: a receita provada (Webb B: 41 docs/172 págs por ~US$ 33 vs ~US$ 63 do caminho ingênuo)

**Preço:** abrir um documento no Historical File Viewer custa **US$ 0,50**; baixar o PDF custa **US$ 1,00 a mais**. O caminho barato: abrir e capturar os canvases já renderizados. Documento já no disco nunca se reabre; cada abertura é lançada no ledger de coleta da unit.

**Navegação** (Playwright/CDP na conta corporativa da PLM, operador logado; pagamento/credencial NUNCA pela automação): árvore dynatree em `#tree` → condado → `Deeds_OPR_ByVolume (1994 to Current)` → faixa (ex. `1801-1900`) → volume → arquivo. **Nome do arquivo:** volumes antigos usam página com 4 dígitos (`1822_0310.tif`); recentes sem zero à esquerda (`2625_179.tif`) — tentar as DUAS formas antes de declarar ausente.

**Espera de carga:** `#lblpath` termina com o nome do arquivo E os canvases do `viewerDocuVieware1` existem (filtrar `height > width`; ignorar thumbnails e canvases 300×150).

**Zoom por API, não por clique:** `DocuViewareAPI.GetCurrentZoom('DocuVieware1')` / `SetCurrentZoom(...)` no iframe `ctl00_html5ViewerIFrame`; alvo ≥ ~1150 px de largura de canvas (≈130 DPI). **Guardar as alturas individuais dos canvases** — são as fronteiras exatas de página para o corte.

**Captura:** compor os canvases num único PNG e **gravar o blob em IndexedDB ANTES de disparar o download** — o Chrome bloqueia downloads automáticos em série SEM AVISO; a permissão "Downloads automáticos: Permitir" para o site é pré-requisito (vai no PEDIDOS.md). **Conferir o disco após o PRIMEIRO documento, sempre, antes de rodar a fila** (a rodada manual perdeu 40 capturas por pular isso).

**PNG → PDF multipágina:** cortar pelo vetor de alturas dos canvases, NUNCA por divisão uniforme (há instrumentos com páginas carta e ofício misturadas). **Validação é julgamento do modelo:** toda página de registro do condado abre com o carimbo Doc/Bk/Vol/Pg no topo; o Auditor amostra páginas renderizadas e confirma carimbo no topo + book.page do carimbo == nome do arquivo. Na Webb B essa checagem pegou 4 documentos cortados no meio, recapturados.

**O que a coleta não resolve vira PEDIDOS.md**, um item por decisão: documento sem imagem no CD (→ TexasFile/cartório, com preço), permissão de download, top-up, e-mail de certificada (minuta pronta; o operador envia).
