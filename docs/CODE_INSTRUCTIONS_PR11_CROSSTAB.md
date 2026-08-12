# ORDEM DE TRABALHO — PR-11 · Proveniência não é corretude
_Emitida 2026-08-12 pela sessão Cowork, após verificação externa do artefato PR-10 (md5 `8b5faee2566200b63f298b4b9c5b709d`) célula a célula contra a trilha **e** contra o DDR à mão._

**Branch:** `pr11-crosstab-consistency` a partir de `pr10-real-tabs`.

## O que a verificação ratificou

Gate whitelist confere: **1.330 células não vazias, 144 fora da trilha e todas as 144 são estrutura declarada** (rótulos terminados em dois-pontos, cabeçalhos, Disclaimer). Zero contaminação da unidade de amostra — nenhuma ocorrência de Bone Spring, Wolfcamp, Ma Chona Adaya, 0,9896248, 636.16, 300%/300%. Trilha: 1.549 entradas, 1.186 com valor e 363 branco-com-motivo, conjuntos disjuntos. Comparação por lease reproduzida de forma independente: **60/60 leases nos dois documentos, 27 MI idênticos, 1 divergente, 18 em branco declarado, nenhuma lease só de um lado.**

## O achado que o gate não podia pegar — e por que

O gate prova que **uma fonte foi citada**. Não prova que **o campo certo foi lido dela**. Três defeitos passaram por ele com trilha completa.

### 1. BLOQUEANTE — Runsheet com registro errado, contradizendo a própria Lease Review do mesmo arquivo

| aba | lease | valor |
|---|---|---|
| Lease Review L25 | 0220604-024 Steven Dewitt Walker | `Vol. 567, Pg. 170` ✔ |
| **Runsheet C5** | mesma lease | **`Volume 199, Page 356`** ✘ |
| Lease Review L28 | 0220604-027 Kevin Chandler Walker | `Vol. 571, Pg. 343` ✔ |
| **Runsheet C6** | mesma lease | **`Volume 199, Page 336 of the Deed Records of Montague County, Texas`** ✘ |

O DDR à mão confirma 567.170 e 571.343 (entradas 12 e 15 do runsheet dele). `Volume 199, Page 336` é **a referência de deed da descrição da terra** — exatamente o defeito corrigido no PR-8, cujo conserto foi aplicado no ponto de escrita da Lease Review e **não virou regra**. A trilha da Lease Review prova que a regra existe e funciona ali: ela registra "extraction read 'Volume 199, Page 336…'" e **não adota**. O escritor do Runsheet nunca consultou a autoridade. É a quinta instância da mesma lição: conserto no ponto de erro, não regra no ponto de acerto.

**Ordem:** a autoridade sobre registro (`categories.yaml dpu.authority`, Exhibit "A") passa a ser consultada por **todo** escritor de campo de registro, em qualquer aba, num único ponto de código. Fixture com esta contradição exata.

### 2. BLOQUEANTE — entrada de Runsheet cuja única fonte é uma captura de tela

Runsheet linha 7 (Choctaw, VOL 581 PAGE 14) tem os **dez** campos citando `Captura de tela 2026-08-06 130244.png p.1`. O grantee saiu `ENEGRY LIMITED PARTNERSHIP, hereinafter refer…` — erro de leitura mais o recital das partes, o defeito que o PR-7 listou e não fechou.

O PR-6 já decidiu que *uma foto de um documento não é o documento* — mas a regra governa só o que **embarca no kit**, nunca o que **serve de citação**. Captura é evidência de segunda mão: não tem carimbo de registro, não tem página, não se re-lê.

**Ordem:** captura de tela deixa de ser citação admissível para valor que vai ao cliente. Ou o documento entra em `FILES/` e é lido, ou a célula fica branca com motivo e item de brief. Registrar como **invariante 27**.

### 3. Brancos órfãos nas abas novas — o gate olha só o que foi escrito

`Ownership - Worksheet` A5:E5 — o recap de unidade sob os cabeçalhos declarados A4:E4 (**Company Net Acres · Company Net Revenue Acres · Seller WI · Seller NRI**) — está vazio **e sem entrada na trilha**. São os números-título do DDR inteiro. O DDR à mão tem o bloco "Unit Verified Totals (Josh B Unit #1H)", então a PLM os espera.

O invariante 18 diz que branco órfão é FAIL, mas o gate de whitelist inspeciona células escritas. É o mesmo erro na forma espelhada: o check foi definido pelo que o erro parece, não pelo que o acerto exige.

**Ordem:** o gate passa a exigir cobertura das duas pontas — toda célula da região de dados declarada (do yaml de estrutura) é escrita-com-trilha **ou** branca-com-motivo-e-dono. Aplicar às abas novas. Depois disso, computar o recap de unidade com `Fraction` a partir das linhas por lease, ou declará-lo branco com motivo e item de veredito.

## Também neste PR

4. **Gate de consistência entre abas.** Mesma identidade (lease, poço, trato) em abas diferentes = mesmo valor, ou FAIL. É o check que teria pego o item 1 mecanicamente, sem depender de eu abrir o arquivo.

5. **Denominadores nos relatórios.** A tabela "trilha por aba" do relatório PR-10 põe 742 células com valor contra 882 "com trilha" na Ownership - Worksheet: a segunda coluna conta linhas de trilha (valor + branco-com-motivo), a primeira conta células escritas. Populações diferentes na mesma tabela. Separar em três colunas nomeadas: escritas-com-trilha · brancas-com-motivo · estrutura. (O texto do PR também disse 393 brancos declarados; a contagem no arquivo dá **363**.)

6. **`0220604-010` (Steve Walker), MI gerado 0,025 contra 0,0125 à mão — exatamente o dobro.** Fica em veredito humano, como está. Investigar se a cadeia royalty → dono → minerals soma dois interesses do mesmo dono (o mesmo padrão dos direitos executivos já achado nesta rodada).

## Aceitação

Gate CLEAN nas duas pontas; consistência entre abas 0 violações; Runsheet sem citação de captura; recap resolvido (computado ou declarado); fixture por defeito; Bowen/Maxwell 0 FAIL / 0 MISMATCH em leitura; suíte verde. **Artefato + relatório + write_manifest anexados.**

## Continua travado no operador

Cert dates **3/3/2010 (A-669)** e **9/9/2010 (A-319)**: origem? Os candidatos do sistema (9/4/2010, 21/5/2010) não batem. Sem isso o Runsheet segue com 4 entradas em base provisória contra 23 do documento à mão, e Title Documents não sai de 1/19.
