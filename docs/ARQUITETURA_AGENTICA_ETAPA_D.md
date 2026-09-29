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
- `aprovar_proposta` exige ator `human:<id>` e nota não vazia. Antes de gravar, rechecha a proposta contra o estado **atual** do Case File. A aprovação cria as tarefas e marca a proposta como `aprovada`, gravando `decided_by`, `decided_at`, `decision_note` e `applied_task_ids`, tudo **na mesma transação**. Depois disso, a tarefa do Coordenador vai para `aceita`.
- `recusar_proposta` marca `recusada` com autor, data e nota e preserva o plano integral. A tarefa do Coordenador vai para `recusada`, e nenhuma tarefa é criada.
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

## 4. Teto real de custo

- O limite de um run é `min(budget da tarefa − custo dos runs anteriores dela, teto da unit − gasto da unit)`.
- Se esse limite for **≤ 0**, nenhuma chamada paga é feita: a tarefa vai para `bloqueada`, com escalonamento `orcamento_tarefa`. Orçamento zero nunca vira execução ilimitada; o antigo `budget_usd or None` foi removido.
- Antes de **cada** chamada, o cliente contado soma o gasto do run e o **pior caso estimado** da próxima resposta. Se passar do limite, a chamada não é feita (`teto_da_tarefa`). Se nada foi entregue até ali, a tarefa vai para `bloqueada`, com escalonamento, em vez de gastar tentativas.
- **Limite técnico:** o teto não é absolutamente exato. A API cobra por resposta, e o custo real só é conhecido depois dela. O pior caso é uma estimativa conservadora: entrada ≈ caracteres/3, sem desconto de cache, com `max_tokens` inteiro de saída. A tokenização real e as tarifas de cache fazem o custo real divergir, normalmente para menos. Uma imagem em base64 superestima muito a entrada.
- O `run_loop` também recebe o limite como `max_cost_usd`, conferido depois de cada turno.

## 5. Perfil surface (Cibola)

`coordenar`, `trabalhar`, `worker.executar_uma`, `semear_coordenador` e `aprovar_proposta` chamam `project_profile.require_supported`. Por isso, uma unit com perfil selecionado é recusada (`surface_title_stage_not_ready:<comando>`) antes de qualquer efeito: nenhuma tarefa criada, nenhum estado alterado, nenhuma chamada. O planejamento suportado continua sendo o `planejar` com o prompt do perfil. Coleta, reconciliação, exame e avanço continuam recusados. O perfil Emirates não é usado como atalho.

## 6. Replay isolado (aceite da Etapa D)

```powershell
python -X utf8 -m src.casefile.replay_coordenador "JOSH B UNIT" --saida=<pasta fora do repo>
```

Como o replay funciona:
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
