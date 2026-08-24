---
concept: custo-search-corpus-em-dump-multiunidade
type: custo
sources:
- '_josh_b_replay: search_corpus("OIL, GAS AND MINERAL LEASE") devolveu ~6 acertos
  e ~700 caminhos em nao_pesquisavel_sem_ocr'
links:
- custo-legibilidade-do-corpus-montague-eog
- formulario-eog-affidavit-de-extensao-de-prazo-primario
unit: ''
confidence: alta
---

## `search_corpus` em corpus-dump: o custo está na lista de NÃO pesquisados

Em unidades cujo FILES/ é dump multi-unidade (centenas de .tif sem camada de texto), `search_corpus` devolve poucos acertos e **a lista inteira de arquivos não pesquisáveis** — milhares de linhas por chamada. Uma busca dessas custa mais que 20 páginas de OCR.

**Regra:** em corpus assim, usar `search_corpus` no máximo uma vez, e só para descobrir **quais documentos têm camada de texto** (planilhas, PDFs nativos). Para o resto, ir direto ao `read_page ... modo=ocr` por caminho deduzido do nome da pasta/arquivo — a nomenclatura do arquivista (`lease.tif`, `lease memo-rec.tif`, `letter extension.pdf`, `affidavit for montague county vol NNN page NNN.pdf`) é previsível e vale mais que a busca.

**Barato e produtivo:** OCR de página de instrumento datilografado neste acervo sai em ~1.000-1.200 caracteres; página de OGL cheia, ~12.000. Exhibit "A" de afidávit multi-lease: ~1.000 caracteres por página com 5 leases → o melhor rendimento por chamada do acervo.
