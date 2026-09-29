# Arquitetura agêntica — Etapa D (Coordenador): contratos

_Correção de 29/09/2026 sobre o commit `511fd3f`, por ordem do operador. Código: `src/casefile/coordenacao.py`, `src/casefile/worker.py`, `src/casefile/orquestracao.py`, `src/casefile/replay_coordenador.py`; migração `0009_orquestracao.sql` (**não aplicada ao banco de produção**)._

O Coordenador é uma função como as outras (`agentes/nucleo/coordenador.md`) e roda no worker genérico. Esta página fixa o que o código em volta dele garante. Nada aqui julga title: o código confere forma, IDs, estados, orçamento e autoria de decisão.

## 1. Cobertura antes da gravação

A saída do Coordenador só passa na validação mecânica (`coordenacao.checar_proposta`) quando:

1. passa em `orquestracao.checar_plano` (esquema `plano_tarefas`, funções existentes, refs únicas, dependências sem ciclo, quarentena do Verificador, orçamento dentro do saldo);
2. a unit tem **plano de investigação aprovado** (o mais recente com status `aprovado`); sem ele, `sem_plano_aprovado`;
3. toda pesquisa **aberta** da sessão desse plano é citada em `pendencias` por pelo menos uma tarefa; senão, `cobertura_incompleta`, com a lista do que falta. Um plano vazio falha aqui;
4. nenhuma tarefa cita pendência inexistente (`pendencia_inexistente`). São válidas `pesquisa:N` da unit, desde que não esteja cancelada, e `decisao:N` da unit;
5. nenhuma tarefa cita pesquisa cancelada (`pendencia_cancelada`).

O erro volta ao modelo durante o run, pela resposta de `entregar_saida`. O código não julga se a tarefa resolve a pesquisa; isso cabe ao operador ao aprovar.

Josh B (plano v1 aprovado): são 10 alvos, as pesquisas 1, 2, 3, 4, 5, 7, 8, 9, 11 e 12. As pesquisas 6 e 10 estão canceladas.

## 2. Proposta e aceite humano

- Uma saída válida de `plano_tarefas` **não cria tarefas**. Ela vai para `plan_proposals` com status `proposta`, junto com os alvos e a cobertura calculados, e a tarefa do Coordenador fica em `aguardando_operador`. Isso é regra de código (`ESQUEMAS_COM_ACEITE_HUMANO`), independente do `verifica` da ficha.
- `aprovar_proposta` exige ator `human:<id>` e nota não vazia. **Tudo acontece numa única transação** (`repo.transacao()`), que confirma junto ou reverte junto:
  - trava a proposta;
  - exige que a tarefa do Coordenador esteja em `aguardando_operador`;
  - rechecha a proposta contra o estado **atual** do Case File;
  - cria as tarefas e marca a proposta como `aprovada`, com `decided_by`, `decided_at`, `decision_note` e `applied_task_ids`;
  - libera as tarefas sem dependência para `pronta`;
  - leva a tarefa do Coordenador para `aceita`.
- `recusar_proposta` também é uma transação única: marca a proposta como `recusada`, com autor, data e nota, preservando o plano integral, e leva a tarefa do Coordenador para `recusada`. Nenhuma tarefa é criada.
- Há testes que injetam falha depois de `criar_tarefas`, em `promover_prontas`, em `decidir` e depois de `recusar_proposta`, no fake e no Postgres. Todos comprovam o estado idêntico ao anterior à tentativa. Uma checagem de mutação (a transação trocada por um contexto vazio) faz 9 dos 10 casos falharem.
- Uma nova proposta marca a anterior ainda aberta como `substituida`, sem apagá-la.
- O banco exige autor, data e nota em proposta aprovada ou recusada (CHECK na 0009).
- CLI: `propostas`, `cobertura --proposta=N`, `aprovar-proposta|recusar-proposta --id=N --por=<operador> --nota="..."`.

## 3. Entrada do Coordenador: o que chega, exatamente

A entrada (`coordenacao.entrada_do_coordenador`) **não é cópia integral do Case File**. Ela leva um `manifesto` que declara, com estas mesmas categorias, o que foi incluído:

| Dado | Como chega |
|---|---|
| pendências abertas (todas as sessões): id `pesquisa:N`, título, o quê, onde, método | **integral** |
| plano de investigação aprovado: versão, status, resumo, pesquisas abertas a cobrir, canceladas (não citar), executadas | **integral** |
| decisões do operador: id `decisao:N`, tipo, pergunta, resposta | integral até **4.000 caracteres** por campo; as truncadas são listadas em `manifesto.truncado` |
| tarefas existentes (ref, função, status, pendências) e escalonamentos abertos | **integral** |
| orçamento: teto, gasto, comprometido em tarefas abertas, reserva da própria tarefa do Coordenador, saldo | **integral** (o saldo anunciado é o que a checagem aceita) |
| censo (conteúdos e caminhos por origem) e claims ativos por tipo | **somente contagem** |
| claims (id `claim:N`, tipo, entidade, valor, `sha256` do documento, página, trecho até 400 caracteres, confiança, materialidade) | **consulta** por `ler_case_file(secao="claims", tipo, filtro, offset, limite)` |
| nomes do censo com sha256 | **consulta** por `ler_case_file(secao="documentos")`; nomes vistos **só** em origem `entrega` ou `outro` ficam de fora, pela mesma quarentena do acervo das sessões |
| textos integrais de pesquisas (todos os estados) e decisões | **consulta** por `ler_case_file(secao="pesquisas" \| "decisoes")` |
| conteúdo de documentos e gabaritos | **não incluído** |

`ler_case_file` é a ferramenta declarada na ficha do Coordenador e implementada pelo código. É somente leitura, com páginas de 25 itens (máximo 100), e todo item leva seu id de proveniência. As demais ferramentas da ficha (`ler_pacote`, `criar_tarefas`, `atualizar_tarefa`, `abrir_escalonamento`) continuam indisponíveis, e o modelo é informado disso no contexto. O pacote de domínio já vai inteiro no sistema.

Josh B, medido no replay: sistema com 5.359 caracteres e tarefa com 26.554, cerca de 10,6 mil tokens pela estimativa de caracteres/3. São 16 pendências abertas integrais e 25 decisões, nenhuma truncada.

## 4. Teto de custo: reservado no banco e estimado por chamada

- **Reserva no banco antes de qualquer chamada** (`reservar_orcamento`, coluna `task_runs.reserved_usd`). Numa transação, com a linha da unit travada (`SELECT … FOR UPDATE`), o limite do run é calculado assim: `min(budget da tarefa − custo dos runs anteriores dela, teto da unit − gasto da unit − reservas dos OUTROS runs abertos da unit)`. Esse valor fica reservado para o run. Reservas concorrentes se serializam pela trava, e a soma delas nunca passa do saldo. A reserva é liberada quando o run fecha: `fechar_run` e `liberar_leases_vencidos` gravam `finished_at` na mesma transação em que o custo real entra em `cost_entries`.
- Se o limite for **≤ 0** porque a tarefa ou a unit não tem saldo, nenhuma chamada paga é feita: a tarefa vai para `bloqueada`, com escalonamento `orcamento_tarefa`. Orçamento zero nunca vira execução ilimitada; o antigo `budget_usd or None` foi removido.
- Se o limite for **≤ 0** só porque o saldo está **reservado por outros runs abertos**, a tarefa volta a `pronta` sem gastar tentativa nem abrir escalonamento. `executar_ate_parar` para nesse caso, com a parada `saldo da unit reservado por outros workers`.
- Há testes com duas conexões e duas threads reais no Postgres: reservas simultâneas nunca somam mais que o saldo (20 rodadas), e uma execução concorrente com saldo reservado não chama o modelo. Sem a trava da unit, uma checagem de mutação faz as duas reservas saírem com $0,80 sobre um saldo de $1,00.
- Antes de **cada** chamada, o cliente contado soma o gasto do run e o **pior caso estimado** da próxima resposta. Se passar do limite, a chamada não é feita (`teto_da_tarefa`). Se nada foi entregue até ali, a tarefa vai para `bloqueada`, com escalonamento, em vez de gastar tentativas.
- **Limite técnico, e por isso o teto é *estimado*:** o que se garante é a reserva e a recusa antes de cada chamada, não o valor exato cobrado. A API cobra por resposta, e o custo real só é conhecido depois dela. O pior caso é uma estimativa conservadora: entrada ≈ caracteres/3, sem desconto de cache, com `max_tokens` inteiro de saída. A tokenização real e as tarifas de cache fazem o custo real divergir, normalmente para menos. Uma imagem em base64 superestima muito a entrada. Se a estimativa errar para baixo, o custo real de uma resposta pode passar da reserva; o livro (`cost_entries`) registra o valor real, e as reservas seguintes já o descontam.
- O `run_loop` também recebe o limite como `max_cost_usd`, conferido depois de cada turno.

## 5. Perfil surface (Cibola)

`coordenar`, `trabalhar`, `worker.executar_uma`, `semear_coordenador` e `aprovar_proposta` chamam `project_profile.require_supported`. Por isso, uma unit com perfil selecionado é recusada (`surface_title_stage_not_ready:<comando>`) antes de qualquer efeito: nenhuma tarefa criada, nenhum estado alterado, nenhuma chamada. O planejamento suportado continua sendo o `planejar` com o prompt do perfil. Coleta, reconciliação, exame e avanço continuam recusados. O perfil Emirates não é usado como atalho.

## 6. Replay isolado (aceite da Etapa D)

```powershell
python -X utf8 -m src.casefile.replay_coordenador "JOSH B UNIT" --saida=<pasta fora do repo>
```

Como o replay funciona:
- **recusa programaticamente** um DSN de destino que aponte para o mesmo banco da origem (`destino_igual_a_origem`), antes de criar qualquer schema. A identidade é `(current_database, porta, início do postmaster)`, então `localhost` × `127.0.0.1` não engana a guarda. O núcleo `_replay` não tem essa guarda: os testes o usam porque o ambiente de teste tem um único banco disponível, e o role `plm` não pode criar bancos;
- lê a produção numa conexão somente leitura;
- copia as linhas da unit, com ids preservados, para um schema temporário no Postgres de **teste**, migrado até a 0009;
- roda o Coordenador pelo worker real com cliente **roteirizado** (0 chamadas de API): a primeira entrega é parcial e é recusada por cobertura, a segunda é completa e vira proposta #1;
- faz uma recusa simulada da #1 e uma aprovação simulada da #2;
- apaga o schema e grava o relatório (`.md` e `.json`) fora do repositório, porque ele contém dados do cliente. A saída dentro do repo é recusada.

A proposta do replay é um roteiro mecânico (uma tarefa de Pesquisador por pesquisa) e **não prova** a qualidade de um grafo real. O relatório separa o que o replay prova do que só um modelo real demonstra.

## 7. Rodada real futura (não executada)

É preciso decidir antes:
1. aplicar a 0009 em produção (`python -m src.casefile db migrar`);
2. autorizar o gasto de Opus (estimativa de US$ 0,30 a 0,60 por proposta, com teto de US$ 1,50 na tarefa).

```powershell
python -X utf8 -m src.casefile coordenar "JOSH B UNIT" --pacote=title-texas-oil-gas-dd --orcamento=1.5
python -X utf8 -m src.casefile trabalhar "JOSH B UNIT" --max=1
python -X utf8 -m src.casefile cobertura "JOSH B UNIT" --proposta=<id>
```

A aprovação ou recusa fica com o operador (`aprovar-proposta` / `recusar-proposta`). O `--max=1` limita a chamada à tarefa do Coordenador, que é a única pronta depois de `coordenar`.
