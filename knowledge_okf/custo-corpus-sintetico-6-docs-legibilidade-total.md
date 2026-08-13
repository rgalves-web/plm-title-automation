---
concept: custo-corpus-sintetico-6-docs-legibilidade-total
type: custo
sources:
- read_page modo=texto em todos os 6 documentos da unidade_sintetica
- dpu p.4 e title opinion p.2 devolveram 0 caracteres (fim do documento)
links:
- custo-legibilidade-do-corpus-montague-eog
- template-dados-de-exemplo-a-e-carroll
unit: ''
confidence: alta — medido nesta unidade
---

## Corpus sintetico: camada de texto em 100% dos documentos — nunca use `ocr`/`imagem` aqui

Nos fixtures sinteticos (`DOCUMENTO SINTETICO - FIXTURE DE TESTE`), os 6 documentos (3 leases PDF, DPU PDF, title opinion PDF, CSV de pocos) tem camada de texto limpa. `modo=texto` resolveu tudo; `ocr` e `imagem` seriam desperdicio de 4x.

**Numeros desta unidade:** 8 paginas com conteudo (DPU 3, leases 1 cada, opinion 1, csv 1). Todo o corpus foi lido em **2 rodadas paralelas de read_page**. Paginas alem do fim devolvem `caracteres: 0` — 1 chamada barata confirma o fim do documento, e vale gastar: e assim que se sabe que nao ha Exhibit "B" escondido.

**Sinal de sanidade que vale em qualquer unidade:** some os acres do Exhibit "C" e compare com o acreage declarado no corpo da DPU (aqui 40+60=100 = 100.00). Fechou, a decomposicao em tratos esta completa; nao fechou, falta trato ou pagina.

**Lembrete de template:** a copia entregue vem com linha de exemplo de outra unidade (aqui `Lease Review` A2/B2 = "0888888-001 / Amostra De Outra Unidade"). Tem que ser sobrescrita ou apagada — dado de unidade alheia no arquivo do cliente e pior que branco.
