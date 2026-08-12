# RODADA 1 — o Examinador escreve o DDR sozinho

_Josh B Unit, Montague County. Branch `r1-examinador-ia`. Executada 12/08/2026._

Um agente, um corpus, um workbook. Nenhum portão, nenhum vocabulário fechado,
nenhuma fórmula em código, nenhum dos vinte módulos que a arquitetura aposenta.
O gabarito ficou em quarentena a rodada inteira, e a quarentena foi estendida ao
kit entregue à mão (`1. Landman Submitted`), que antes estava aberto.

## O número

Populações declaradas **antes** de contar:

| população | definição | tamanho |
|---|---|---|
| gabarito | células não vazias do DDR à mão, todas as abas | **2.905** |
| escritas pela IA | células que o ledger registra como escritas pelo modelo | **176** |
| template | células não vazias do template antes de qualquer escrita | **3.041** |

Resultado, célula a célula:

| balde | n | o que significa |
|---|---|---|
| concordou | **63** | mesmo valor, caractere a caractere, após normalizar caixa, espaço e data |
| equivalente | **29** | mesmo valor com mais ou menos prosa em volta. **Não é acerto** — o estilo da casa faz parte do produto |
| divergiu | **84** | conteúdo diferente |
| calou | **2.627** | a mão escreveu, a IA não |
| escreveu a mais | **0** | — |
| herdado do template | **102** | bateu porque o template já tinha o valor. **Não é obra do modelo** |

**Cobertura: 176 de 2.905 = 6,1% do entregável à mão foi endereçado.** Contra a
esteira atual, que produz 1.178 células com proveniência: a rodada 1 escreveu
**15% do que o pipeline determinístico escreve**.

### A régua mudou depois de eu ver o resultado — os dois números

A primeira medição dava `concordou 43 · divergiu 74`. Três ajustes, todos
declarados no `comparacao.json`:

1. **Data.** O workbook guarda `2010-01-21` como datetime, o modelo escreve como
   texto. Contar isso como divergência mede o meu harness, não o modelo.
2. **Apelido de aba.** O template chama `Ownership Report` o que o kit entregue
   chama `Ownership - Worksheet`. Sem o alias, cada célula da aba conta duas
   vezes como falha — uma como silêncio, outra como excedente.
3. **Balde `equivalente`**, separado de acerto, para "mesmo valor com outra
   prosa em volta".

Depois disso, a reconstrução do workbook foi corrigida (ver abaixo) e o número
subiu de `43` para `63` sem que o modelo escrevesse nada a mais.

### O que "divergiu" ainda esconde

Amostrando as 84: uma parte é **grão de linha**, não fato errado. Em
`Ownership - Worksheet` a mão repete o tract por lease e a IA numerou uma linha
por tract — `A9` mão=`1` IA=`2`, `R9` mão=`13,05` IA=`80,02`. São as mesmas
duas tracts, em linhas diferentes. Comparação por coordenada pune layout
diferente e válido. Não construí motor de alinhamento: a ordem pedia célula a
célula, e o confundidor fica nomeado em vez de corrigido em silêncio.

## O achado que importa: ele parou sozinho achando que tinha terminado

A rodada não bateu no teto de turnos (34 de 400) nem no de custo. **O modelo
parou de pedir ferramentas e escreveu um relatório de encerramento** — com 6% do
entregável escrito. Não faltou orçamento nem paciência: faltou saber o tamanho
do que faltava.

É o defeito central da rodada 1 e não se resolve com prompt melhor. O que o
pipeline determinístico tem e o Examinador não é **um censo**: a lista do que
precisa existir, contra a qual o que existe é conferido. Sem isso, "terminei" é
uma opinião.

## O que ele fez bem, e que nenhum `if` fazia

- **Achou a sujeira do template sozinho.** As abas `Ownership - 1H (No FO
  Option)` e `delete - A.E. Carroll 4H` são 100% dados de exemplo de outra
  unidade. Ele identificou, limpou com `record_blank` em faixa, e **perguntou**
  se a política correta é excluir a aba ou mantê-la vazia — pedindo que a
  resposta virasse precedente para as 300 unidades.
- **Recusou certificar o que não podia provar.** Sem Division Order Title
  Opinion, não escreveu Company Net Acres, Net Revenue Acres, Seller WI nem
  NRI. E apontou onde procurar: existem `doi_-_hansen unit.xlsx` para outras
  unidades no mesmo corpus.
- **51 brancos, todos com motivo e dono**, sem vocabulário fechado para
  consultar. Ex.: `Summary!B2` — "nome do cliente não consta de documento algum
  do corpus; o template trazia `***`" → dono: gerente do engajamento.
- **Escreveu 5 fichas de conhecimento**, entre elas uma medindo, por tipo de
  arquivo, qual modo de leitura funciona neste corpus — que é exatamente a
  reutilização que a arquitetura promete para as unidades 2 a 300.
- Confiança declarada: **156 alta, 20 média**. Nenhuma baixa.

## Três defeitos meus, nenhum dele

A primeira rodada completa terminou o laço e **caiu na escrita do workbook**,
depois de todo token pago. O ledger sobreviveu porque é gravado a cada turno, e
os artefatos foram reconstruídos sem comprar a conversa de novo.

1. **Faixa.** `openpyxl` devolve tupla para `A1:Z44` e célula para `C12`. A
   diferença derrubou a rodada.
2. **Mesclada.** A sombra de um bloco mesclado é somente-leitura.
3. **Ordem — o pior.** Eu aplicava todas as escritas e depois todos os brancos.
   O modelo limpou as linhas de amostra 8 a 24 e **então** escreveu dentro
   delas; a inversão apagou 31 células de trabalho dele. O ledger agora é um
   fluxo único de ações com número de sequência.

E um quarto, achado pela ficha que o próprio modelo escreveu: **`.csv` e
`.html` são texto puro e o meu `read_page(texto)` só sabia ler PDF**, devolvendo
vazio. Ele concluiu, corretamente do que via, "não gaste chamada" — e gravou
isso como conhecimento para as 300 unidades. São **23 arquivos** do corpus,
incluindo deeds em HTML e os CSVs de poço do RRC que alimentam
`Ownership - Wells`. Uma ferramenta que mente sobre o que não consegue ler
ensina a lição errada em escala. Corrigido.

## Custo

**Não sei o custo real desta rodada.** O log completo é escrito no fim e a
rodada caiu antes; o piso, somando as linhas por turno, é **$2,85**, e essas
linhas omitiam os tokens de cache — que num laço longo são a maior parte da
conta. Ambos os defeitos estão corrigidos, então a próxima rodada reporta custo
de verdade.

O que dá para dizer: 34 turnos, 27 leituras de página, 1.127 documentos no
corpus. Ele leu **27 páginas** para escrever 176 células.

## O que a rodada 1 responde e o que não responde

**Responde:** o modelo produz trabalho de title real, cita fonte literal,
recusa o que não prova, nomeia dono para cada branco, acha problema que nenhum
gate tinha (a sujeira do template), e escreve conhecimento reutilizável. Nada
disso precisou de um `if`.

**Não responde** — e a rodada 2 tem de atacar: ele não sabe quando não terminou.
6,1% de cobertura com "terminei" é pior que 6,1% com "faltam 2.700 células que
não olhei". Antes de Conferente e Promotor, o Examinador precisa de um **censo**:
não um gate que aprova o que ele escreveu, mas a lista do que a unidade exige,
para ele mesmo medir o próprio buraco.

## Artefatos

- `data/units/_josh_b_replay/KIT_IA/DDR - Josh B Unit (IA).xlsx` — o workbook
- `.../comparacao.json` — a medição, populações declaradas
- `.../ledger.json` — as 176 escritas com citação, os 51 brancos, as 2 perguntas
- `.../progress.jsonl` — o log por turno
- `knowledge_okf/` — 75 fichas migradas + 5 escritas pelo modelo

871 testes verdes, 42 no pacote novo. Nenhum deles afirma uma conclusão de
title, porque nenhum código deste pacote chega a uma.
