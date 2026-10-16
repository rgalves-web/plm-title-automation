# ARQUITETURA GOVERNANTE — decisão de 2026-08-23
_Decidido pelo operador (Renato) em 23/08/2026, em sessão Cowork, após revisão completa do repo, das 4 units entregues e das retrospectivas. Este documento encerra o conflito entre as três arquiteturas registradas e **prevalece sobre qualquer documento anterior em caso de contradição**._

Atualização operacional autorizada em 11–12/10/2026: `OPERACAO_VISUAL.md` descreve a esteira de dez funções, PostgreSQL, quatro executores, conhecimento versionado e migração do Cibola. Mantém integralmente a separação entre julgamento por IA e proteção de arquivos/custos pelo código. Renato autorizou o piloto Cibola de quatro tracts, acervo local, through date 11/10/2026, Claude na produção e OpenAI na revisão, com teto de US$ 50 por tract. Posteriormente impôs **US$ 20 adicionais no total para o restante desta implementação**. O novo limite compartilhado prevalece sobre a disponibilidade individual; custos anteriores e incertos são preservados. Essas autorizações não incluem compra, comunicação externa, PREP ou submissão.

## 1. A lei

Transporte vigente por ordem de Renato em 16/10/2026: Claude Code e Codex pelos terminais oficiais, sem chaves locais de API. `EXECUCAO_TERMINAL.md` descreve autenticação, isolamento, recibos e limitações. O núcleo continua LLM-first, com produção e revisão de famílias independentes; a mudança não libera conclusões nem apaga custos históricos.

**LLM-first puro, conforme a ordem de 12/08 (`docs/ARQUITETURA_LLM_FIRST.md`).** Nenhuma decisão de title em Python: nem limiar, nem tabela de autoridade, nem fórmula, nem portão que aprove ou repita julgamento. Quem confere um julgamento de IA é outra IA (Auditor de família independente), nunca um `if`.

Precedência entre os documentos existentes:

| Documento | Papel a partir de hoje |
|---|---|
| `ARQUITETURA_LLM_FIRST.md` (12/08) | **Arquitetura governante** |
| Manual Técnico (16/08) | **Fonte de requisitos e precedentes** (caps. 6–12, 15, 16, 19). Os "engines" dos caps. 4 e 13–17 são desenho descartado, não requisito. |
| `DDR_JOB_FLOW_SPEC.md` (05–11/08) | Fonte de requisitos de processo (estágios S1–S8, critério de convergência). A divisão "código prova aritmética" está **revogada**. |
| Esteira determinística (`src/dd`, `src/knowledge`, MOR) | Congelada. História, fixtures e fonte de plumbing reaproveitável (cópia de arquivos, leitura de template). Nunca volta ao caminho de decisão. |

## 2. A régua: proteger bytes não é decidir title

O pivô dá ao Python quatro tarefas burras: abrir arquivo, renderizar página, chamar modelo, salvar bytes. Esta seção fixa a fronteira para que nenhuma sessão futura a reabra em silêncio.

**São propriedades da caneta (permitidas, obrigatórias):**
- recusar escrever em célula que contém fórmula, com hash do conjunto de fórmulas do template antes e depois de todo save;
- write-roots declarados antes de escrever; recusa de escrita fora deles; pacotes entregues congelados;
- quarentena do gabarito durante um replay;
- cópia de arquivos em árvore de nomes definidos (kit), com round-trip md5;
- contagem de custo, tokens e teto de orçamento;
- hash/md5 para detectar duplicata byte a byte e "o que é novo em FILES/".

Nada disso escolhe valor, compara fato de title ou aprova conteúdo. Uma escrita recusada volta ao modelo como erro nomeado ("célula de fórmula — o valor verificado vai na célula branca"), e o modelo decide o que fazer.

**São julgamento (só IA, sempre com citação):** o que um documento é; o que ele diz; que valor entra em cada célula; se a página sustenta o valor; o censo e sua conta; se produção zero é defeito ou shut-in documentado; se duas fontes divergem e qual prevalece; quando perguntar ao operador.

## 3. Parâmetros de operação aprovados (23/08)

- **Teto duro de custo: US$ 25 por unit**, acumulado no estado da unidade. Ao bater, o sistema para, reporta o que falta e espera ordem. Nunca estoura em silêncio.
- **Busca de documentos: manual.** O sistema instrui (PEDIDOS.md com o quê/onde/termo/método, empacotado para uma sentada — invariante "one brief item per decision"); o operador busca. A pull list de cartório nasce no dia 1 da unidade, não no fim.
- **Meta de horas do operador: ≤ 1h por unit** (aprovações, respostas, upload). Tensão conhecida com a busca manual; medir na primeira unit real e revisitar com número na mão.
- **Auditor de família B: OpenAI** (`OPENAI_API_KEY` no `.env`). Enquanto a chave não existir, o carimbo de limitação continua em todo relatório.
- **Método de trabalho do Code: ordem única com 3 checkpoints obrigatórios** (`docs/CODE_INSTRUCTIONS_CONSERTO_DEFINITIVO.md`). O Code para em cada checkpoint e só segue com aceite registrado do operador.
- **Divisão Cowork/Code:** Cowork (esta sessão) escreve docs e fichas direto no repo e verifica entregas pelos bytes; **todo `.py` passa pelo Code**, com suíte verde antes e depois.
- **Prova real: replay da Josh B, operado pelo Code.** A prova de operabilidade pelo Renato fica para a primeira unit nova (Fase 4).
- **Depois do conserto:** fechar a rodada de cartório da Webb B (21 docs, ~$32, pull list de 21/08).

## 4. O que não muda

FILES/ é somente leitura; corpus lido in-place dos zips originais; branco declarado com motivo e dono vence número plausível; toda célula com citação literal ou branca; célula reprovada não embarca; `SUBMISSION PLM/` de unit entregue é intocável; dados de cliente nunca saem da máquina além do trecho necessário à API; gabarito em quarentena durante replay; correto-e-menor vence plausível-e-errado.
