---
concept: submission-example-e-pacote-modelo-knox-nao-e-evidencia
type: regra
sources:
- 'list_documents na unidade WEBB B UNIT: 55 arquivos sob submission example/1. landman
  submitted/ com bytes: 0'
- 'nomes dos arquivos: l1-l26 OGL (Wylie, Thalmueller, Grisso, Knox, Menser...), plm
  report/ddr - knox unit.xlsx, well files/p-12 knox unit.pdf, plat knox unit.pdf'
links:
- template-dados-de-exemplo-a-e-carroll
- exclusion-reasons-fora-do-perimetro
- exclusion-reasons-doc-nao-localizado
unit: ''
confidence: alta — inventario conferido arquivo a arquivo
---

## A pasta `submission example/` e material de formato, nao registro da unidade — e vem com 0 bytes

Estrutura encontrada (55 arquivos, **todos com `bytes: 0`**):

```
submission example/1. landman submitted/
  leases/            l1 … l26 (OGL de Wylie, Thalmueller, Grisso, Knox, Menser, Vick, Black…)
  plm report/        ddr - knox unit.xlsx
  seller files/      ownership report*.pdf
  title documents/   399.562, 482.140, 487.617, 548.797, 551.789, 597.643, 656.269
  title opinions/    unit tract 1,2,3,4,6,7
  unit designations/ 551.789, 597.643, 656.269
  well files/        form w-1, p-12 knox unit, plat knox unit, production report api
  phase i - checklist.xlsx
```

**Dois motivos independentes para nao usar nada dali como fonte:**
1. **Conteudo zero.** Nenhum byte para ler. Nao adianta `texto`, `ocr` nem `imagem`.
2. **Perimetro alheio.** Mesmo que tivessem conteudo, sao do **KNOX UNIT** — os proprios nomes dizem (`ddr - knox unit`, `plat knox unit`, `p-12 knox unit`, lessores Knox/Wylie/Grisso). E o pacote-modelo que mostra o *formato* de uma submissao completa, irmao do `template-dados-de-exemplo-a-e-carroll`: a casa distribui exemplos junto com o material de trabalho.

**Regra:** ao inventariar uma unidade, separe primeiro `submission example/` do resto. O denominador do censo sai do que sobra. Citar `l5 - 403.445 - altis davidson ogl.pdf` como fonte de uma celula seria reprovado no audit por dois motivos ao mesmo tempo.

**Uso legitimo:** a arvore acima e a melhor descricao disponivel de como um pacote completo de landman deveria chegar (leases numeradas L1..Ln, title opinions organizadas por unit tract, unit designations por volume.pagina, well files com W-1/P-12/plat/producao). Serve de checklist do que pedir quando falta material — foi assim que montei os PEDIDOS de WEBB B.

**Sinal de alerta de unidade vazia:** se depois de excluir `submission example/` sobrar so workbook ilegivel + BPM + amostra de outra propriedade, a unidade nao tem registro. Nao force celulas: declare censo, brancos com dono, pedidos e pergunte ao operador (precedente WEBB B UNIT).
