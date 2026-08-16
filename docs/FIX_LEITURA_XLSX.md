# FIX PEQUENO — read_page precisa ler .xlsx (bloqueia o SOP inteiro)

O SOP do Project Emirates (docs/SOP_DDR_PROJECT_EMIRATES.md) exige reconciliar
as DUAS abas do Lease-to-Well XREF contra a DPU, tirar os TOs da coluna G do
project log e comparar WI/NRI contra o Well List – Prelim AV%. Tudo isso é
.xlsx — e hoje `read_page(modo=texto)` devolve 0 caracteres para .xlsx e
`modo=ocr` estoura UnidentifiedImageError (visto na rodada real da WEBB B).

Branch `sistema-operavel`, mudança contida em src/examinador/corpus.py:

1. `.xlsx`/`.xlsm` no `modo=texto`: "páginas" = abas. `read_page(doc, N)` devolve
   a aba N como texto tabular (openpyxl read_only, values_only, células unidas
   por " | ", linhas por \n). Página 0/listagem: nomes das abas + dimensões.
2. Aba grande: devolver em janelas (ex.: 200 linhas por página lógica,
   `read_page(doc, "2:3")` = aba 2, janela 3), para o modelo pedir só o que
   precisa — os XREFs têm dezenas de milhares de linhas e o modelo vai filtrar
   por "WEBB B" via search_corpus.
3. `search_corpus` passa a varrer .xlsx também (mesma extração, cacheada por
   hash no cache global — paga uma vez para as 300 unidades).
4. Teste com os 5 workbooks reais da WEBB B UNIT: aceitação =
   `search_corpus("WEBB B")` encontra as linhas nos XREFs e `read_page` devolve
   a janela que as contém. Suíte verde. Nada de decisão em Python: extração é
   transporte, quem interpreta é o modelo.
