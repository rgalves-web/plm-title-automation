# ARQUITETURA IA-FAZ-O-TRABALHO — v3
_Revisão de 2026-08-12. A v1 deixava cálculo em Python. A v2 tirou o código da decisão mas pagava caro porque cada unidade relia tudo do zero. Esta versão mantém o princípio e derruba o custo pela reutilização de conhecimento entre unidades. Preços da tabela pública Anthropic, 12/08/2026._

## 1. A regra única

**Nenhuma decisão em Python.** Nem limiar, nem tabela de autoridade, nem fórmula, nem portão. Onde hoje existe decisão em código, passa a existir julgamento de IA, e quem confere um julgamento é **outra IA**, nunca um `if`.

Python fica com quatro tarefas burras: abrir arquivo, transformar página em imagem, mandar e receber do modelo, salvar bytes. Caneta e mesa, não examinador.

## 2. O que é apagado

Saem do caminho de decisão, porque são regras que a IA passa a julgar:

`classifier` · `triage` · `perimeter` · `recording_authority` · `interest_formula` · `term_source` · `to_schedule` · `lease_disposition` · `unit_ownership` · `gap_hunter` · `runsheet` · `fetch_brief` · `ddr_tabs` · `clean_output` · `cross_tab` · `row_completeness` · `template_structure` · `source_truth_check` · `ddr_validator` · `dd_qa_gates`

Vinte arquivos, alguns milhares de linhas. Cada um nasceu de um defeito e nenhum cobre o defeito seguinte. Foi essa a esteira das dez rodadas.

## 3. O painel — quatro papéis, cabeças independentes

Dois modelos da mesma família erram juntos. Redundância só vale com cabeças independentes, e por isso o Conferente e o Promotor vêm de fornecedores diferentes do Examinador. Trocar é linha de configuração.

| papel | o que faz | modelo |
|---|---|---|
| **Triador** | lê os documentos e diz o que cada um é, com citação | Haiku 4.5 |
| **Examinador** | o landman. Pede documento, decide, calcula, escreve ou recusa | Opus 5 |
| **Conferente** | mesmo campo, mesma evidência, **sem ver** a resposta do examinador | família B |
| **Promotor** | relê o arquivo salvo com uma ordem só: derrube esta célula | família C |

## 4. Aritmética sem uma linha de código

O Examinador conclui o número. O Conferente conclui o dele às cegas. Batendo, adota; divergindo, entra a terceira cabeça e vale dois de três; três discordâncias viram branco com motivo e pergunta para ti.

O `0220604-010` — 0,025 contra 0,0125 — teria caído aí, sem `Fraction` e sem gate.

## 5. Ferramentas que a IA opera

```
list_documents(filtro)            inventário do corpus
read_page(doc, página, modo)      modo: texto (barato) ou imagem (caro) — a IA escolhe
search_corpus(termo)              onde esse nome, volume ou número aparece
read_knowledge(conceito)          consulta a base OKF (item 6)
write_knowledge(conceito, ficha)  a IA registra o que aprendeu, para as próximas unidades
get_precedent(campo)              vereditos teus, como jurisprudência
ask_second_opinion(campo, evid.)  chama o Conferente — a IA decide quando vale a pena
write_cell(aba, célula, valor, citação, confiança)
record_blank(aba, célula, motivo, dono)
flag_for_human(pergunta, candidatos, o que desempataria)
```

## 6. O corte de custo — conhecimento lido uma vez, usado trezentas

O que faz uma unidade custar $70 não é a inteligência, é a releitura. Hoje a unidade 200 relê do zero exatamente o que a unidade 1 já tinha lido.

As 300 unidades do BKV122TX compartilham quase tudo: mesmo Seller, mesmo condado, os mesmos escritórios de parecer, os mesmos formulários de lease, as mesmas cadeias de cessão. O assignment `K1400170` Encana→EOG aparece **nas três unidades já feitas**, e foi pago três vezes.

**A base de conhecimento é o cofre.** A IA lê um documento uma vez, escreve uma ficha, e as próximas unidades **consultam em vez de reler**:

| o que se lê uma vez | o que se economiza depois |
|---|---|
| cadeia de cessão Encana → EOG | 300 unidades consultam, nenhuma relê |
| formulário de lease EOG Barnett 2008 | a IA só lê o que **diverge** do formulário em cada lease |
| layout de cada escritório de parecer | onde fica a frase de certificação, sem varrer 36 páginas |
| XREF e Lease Schedule | tabelas viram índice consultável, não leitura repetida |
| cada veredito teu | a cert date respondida uma vez serve as trezentas |

Cinco alavancas, todas preservando o princípio:

1. **Ficha em vez de página.** Consultar uma ficha de conhecimento custa centenas de tokens; reler o documento custa milhares.
2. **Cache de página global, não por unidade.** O mecanismo já existe, mas hoje vive dentro da pasta da unidade. Movido para global, documento repetido custa zero na segunda vez.
3. **Texto antes de imagem.** Página como imagem custa ~2.000 tokens, a mesma em texto ~500. A IA pede texto primeiro e só chama a imagem se o texto não bastar. Continua sendo escolha dela.
4. **Conferente sob demanda.** Não se confere tudo, confere-se o que o Examinador marcar como incerto ou de risco. Ele decide.
5. **Batch API**, 50% no que não é interativo.

### A curva

| | custo |
|---|---|
| unidade 1, que paga para aprender | ~$70 |
| unidade 20 | ~$35 |
| unidade 100 | ~$18 |
| unidade 300 | ~$12 |
| **média nas 300** | **~$20** |

**Total do projeto: $5 a $6 mil**, ou perto de $3 mil com Batch API. Era $12 a $21 mil na v2.

## 7. O formato: OKF, do Google

Só para alinhar os nomes, porque isso muda a decisão. **OKF é o Open Knowledge Format, do Google Cloud**, publicado em junho de 2026. **GraphRAG é da Microsoft.** São coisas diferentes e as duas interessam aqui.

**OKF** é apenas um formato de arquivo: uma árvore de markdown com frontmatter YAML, uma ficha por conceito, `index.md` e `log.md` reservados, links cruzados entre fichas, e um campo `type` que roteia. Não tem serviço, nem registro central, nem ferramenta obrigatória. E foi desenhado explicitamente para que **agentes de enriquecimento escrevam nele**.

É por isso que ele serve: a base de conhecimento deixa de ser YAML escrito à mão e passa a ser escrita e mantida **pela própria IA**, que é o teu princípio aplicado à camada de conhecimento. Sem dependência, sem lock-in, sem stack nova — são arquivos de texto no repo. O `knowledge/` de hoje migra para fichas OKF, e a ferramenta `write_knowledge` é como a IA deposita o que aprendeu.

**GraphRAG** resolve o mesmo problema por outro caminho: a IA indexa o corpus inteiro uma vez, monta um grafo de entidades e depois consulta o grafo em vez de reler. O padrão é o certo e é o do item 6. A implementação da Microsoft, porém, é feita para perguntas e respostas sobre um acervo, não para produzir um entregável com proveniência célula a célula, e traria uma dependência pesada. **Adotamos a ideia, não a stack.**

## 8. As rodadas

**Rodada 1 — o Examinador nasce e escreve o DDR inteiro.** Laço de agente, corpus da Josh B, workbook novo em paralelo. Nenhum portão, nenhum módulo velho no caminho. Sai um número: quantas células o painel acerta sozinho contra as 1.178 de hoje e contra o DDR à mão.

**Rodada 2 — Conferente e Promotor, e a base OKF.** Segundo e terceiro fornecedores plugados. A IA passa a escrever fichas de conhecimento enquanto trabalha. Aceitação: o Promotor reencontra sozinho os cinco defeitos das rodadas 8 a 12. Reencontrou, os vinte módulos do item 2 são apagados.

**Rodada 3 — unidade nova, ponta a ponta**, com Bowen e Maxwell em leitura como controle. Aqui sai a medida que importa: horas tuas por unidade, e o custo real da segunda unidade contra a primeira.

## 9. Ordem colável para o Code — Rodada 1

```
BRANCH: r1-examinador-ia

REGRA ÚNICA: nenhuma decisão em Python. Se um trecho de código escolhe,
compara, calcula, filtra ou aprova, ele não entra. Python só abre arquivo,
renderiza página, chama modelo, salva bytes.

1. Laço de agente a partir da tag archive/phase1-conversational-shell
   (orchestrator, router, registry já existem — partir dali, não do zero).

2. Ferramentas expostas ao modelo, exatamente estas:
   list_documents, read_page(modo texto|imagem), search_corpus,
   read_knowledge, write_knowledge, get_precedent,
   write_cell, record_blank, flag_for_human.
   write_cell exige valor + citação (doc, página, trecho) + confiança.

3. O Examinador é Opus 5 e recebe instrução de trabalho, não fluxograma:
   "você é o landman responsável por esta unidade; o corpus está nas
   ferramentas; produza o DDR; toda célula precisa de fonte; o que não
   puder provar, deixe em branco com motivo ou pergunte."

4. Base de conhecimento em formato OKF (markdown + frontmatter YAML, uma
   ficha por conceito, index.md e log.md). A IA escreve nela via
   write_knowledge enquanto trabalha. knowledge/ atual migra para lá.

5. Cache de página por hash movido para GLOBAL, fora da pasta da unidade.

6. Nenhum módulo da lista do item 2 entra no caminho. Ficam no repo,
   fora do caminho, até a Rodada 2.

7. Corpus: data/units/_josh_b_replay lido in-place. Quarentena do gabarito
   ativa. Saída em KIT_IA/, sem tocar no atual.

8. Ao fim, comparação célula a célula contra
   BKV122TX - Project Emirates/JOSH B UNIT/1. Landman Submitted/
   PLM Report/DDR - Josh B Unit.xlsx, populações declaradas antes de medir.

ENTREGA: workbook + comparação + log do agente (quais documentos pediu,
em que ordem, o que decidiu, quanto custou). Sem relatório sem artefato.
```

---

**Fontes sobre OKF e GraphRAG:** [Open Knowledge Format — spec no GitHub do Google Cloud](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) · [Google Cloud Blog sobre OKF](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) · [microsoft/graphrag no GitHub](https://github.com/microsoft/graphrag)
