---
concept: custo-xlsx-ilegivel-pelas-ferramentas
type: custo
sources:
- 'read_page texto em bkv122tx - project log (2).xlsx p.1 → caracteres: 0'
- 'read_page texto em lease & mineral schedule 6.9.26 (3).xlsx p.1 → caracteres: 0'
- 'read_page texto em lease to well and contract xref 06-16-2026 (1).xlsx p.1 → caracteres:
  0'
- 'read_page texto em well to lease and contract xref 05-22-2026 (3).xlsx p.1 → caracteres:
  0'
- read_page ocr em bkv122tx - project log (2).xlsx p.1 → UnidentifiedImageError
- 'search_corpus: os .xlsx aparecem sempre na lista nao_pesquisavel_sem_ocr'
links:
- custo-corpus-sintetico-6-docs-legibilidade-total
- custo-legibilidade-do-corpus-montague-eog
unit: ''
confidence: alta — medido em 5 arquivos distintos
---

## .xlsx nao e legivel por nenhum dos tres modos — nao gaste chamadas

Testado em 5 workbooks de 1,4 a 11,8 MB, todos com o mesmo resultado:

| modo | resultado |
|---|---|
| `texto` | `caracteres: 0` (silencioso, parece pagina vazia) |
| `ocr` | `UnidentifiedImageError: cannot identify image file` |
| `imagem` | nao testado; nao ha pixels a extrair de um zip OOXML — presumivelmente falha igual, a 4x o custo |

**Regra pratica:** 1 chamada `texto` por workbook para registrar a ilegibilidade e pronto. NAO escale para `ocr` nem `imagem` — `ocr` estoura com excecao e `imagem` custa 4x por nada. Custo minimo desta licao: eu gastei 6 chamadas para aprende-la; a proxima unidade gasta 1 por arquivo, ou zero se confiar nesta ficha.

**Consequencia de metodo:** `search_corpus` lista os .xlsx como `nao_pesquisavel_sem_ocr`. Ausencia de um termo na busca NUNCA prova ausencia no corpus quando ha .xlsx presente — a nota da propria ferramenta diz isso. Se o dado que falta plausivelmente mora num workbook, o caminho e `pedir_documento` pedindo export CSV/PDF, nao mais leitura.

**Nomes recorrentes de workbook neste projeto** (aparecem provavelmente em varias das 300 unidades): `bkv122tx - project log`, `lease & mineral schedule`, `lease to well and contract xref`, `well to lease and contract xref`, `well list`. Pelo nome sao a espinha dorsal de dados (schedule de leases/minerais, lista de pocos, cruzamento lease↔poco↔contrato). Vale um pedido unico e permanente de conversao para CSV valendo para todo o projeto, em vez de 300 pedidos identicos — ver PERGUNTAS P2 da unidade WEBB B.

**Armadilha de nome:** `lease & mineral schedule 6.9.26 (3).xlsx` falha com `FileNotFoundError` se o `&` for passado escapado como `&amp;`. Passe o nome literal, com `&` cru.
