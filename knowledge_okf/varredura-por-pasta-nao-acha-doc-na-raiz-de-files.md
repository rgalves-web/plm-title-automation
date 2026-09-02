---
concept: varredura-por-pasta-nao-acha-doc-na-raiz-de-files
type: regra
sources:
- files/t-o orig w.s. scarborough a-669 50ac.pdf (raiz de files/, 977.733 bytes)
- documentos a buscar - 2a rodada.md secao 1.1 e 3a rodada.md secao 1.1 (declaram
  o mesmo TO como inexistente e como BLOQUEADOR)
- list_documents(contains='a-669') na unidade JOSH B UNIT
links:
- dpu-eog-exhibit-a-layout-e-custo-ocr-vs-imagem
- pull-list-de-cartorio-derivada-do-exhibit-a-vs-pastas-de-files
- manual-10-missing-files
unit: ''
confidence: alta
---

## Documento faltante pode estar na RAIZ de `files/`, fora de qualquer pasta

**Caso JOSH B UNIT (Montague).** Tres rodadas sucessivas de coleta declararam o Original Title
Opinion do Unit Tract 1 (A-669, 50 ac) como **inexistente** e como o **unico bloqueador** da
certificacao de WI/NRI do wellbore — chegando a instruir "pedir ao PM/seller". O arquivo estava
no acervo desde o inicio, em `files/t-o orig w.s. scarborough a-669 50ac.pdf`, **na raiz de
`files/`**, fora de qualquer pasta de lease (`0221055-001/-002`) e fora de qualquer pasta
`t0......` de title opinion — os dois unicos lugares onde as rodadas anteriores olharam.

### Regra
Antes de declarar `document_missing`, rodar `list_documents(contains=<token>)` com tokens que
**nao dependem da pasta**:
- o **abstract** (`a-669`, `a-319`) — o mais discriminante para TO e plat;
- a **acreagem** do trato (`50ac`, `155ac`, `318.3ac`);
- o numero de lease em ambas as grafias (`0220604-018` e `0220604/018`).

Um documento cuja pasta esperada esta vazia **nao e um documento ausente**: e um documento cujo
caminho ainda nao foi encontrado. `document_missing` exige busca por nome, nao por pasta.

### Sinal de alerta barato
Na saida de `list_documents`, quase todos os itens vem com `bytes: 0` (arquivo referenciado dentro
de zip/estrutura). O item com **bytes reais preenchidos** costuma ser o solto na raiz — foi assim
que o TO apareceu. Vale escanear a coluna de bytes.

### Corolario para a pull list
Reverificar item a item, com `list_documents`, toda pull list herdada de rodada anterior antes de
gastar diligencia externa. Na JOSH B UNIT, das 8 leases declaradas "sem pasta nenhuma no Drive",
**4 tinham pasta com o `lease.tif`** (0220604-022, 0220604-024, 0221851-004, 0222981-056). A lista
de cartorio caiu de 8 para 4. Nota herdada e hipotese, nao inventario.
