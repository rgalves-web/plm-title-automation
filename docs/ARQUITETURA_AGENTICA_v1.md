# ARQUITETURA AGÊNTICA v1 — a firma de agentes sobre o Case File

_Redigido em 27/09/2026 em sessão Cowork, a pedido do operador (Renato). Status: **proposta**, sem aceite. Não revoga `ARQUITETURA_GOVERNANTE.md`: a lei LLM-first continua valendo integralmente. Este documento organiza **quem** faz o trabalho de julgamento e **como** o trabalho se divide._

Leitura prévia obrigatória para o Code: `CLAUDE.md`, `docs/ARQUITETURA_GOVERNANTE.md`, `docs/CASEFILE_VS1.md`, `docs/TRAINING_SUITE_INTEGRACAO.md`, `docs/CIBOLA_RETROSPECTIVA_1128_2026-09-21.md`, e as fichas em `agentes/`.

---

## 1. Diagnóstico que motiva a mudança

O sistema atual é uma sequência de sessões. Há três papéis de fato (Triador, Examinador, Verificador de família B), mas não há coordenador que divida o trabalho, a coleta é manual, as sessões rodam em série e, segundo a retrospectiva do 1128 (§3.10), um mesmo agente chegou a pesquisar, interpretar, escrever e aprovar. Os tracts BBT-SNN-1128 e 1129 foram produzidos fora do sistema, porque o perfil de surface title recusa tudo depois do planejamento. O repo mantém cinco gerações convivendo.

O objetivo desta arquitetura é que um projeto novo seja decomposto por um coordenador em tarefas, que cada tarefa seja executada por uma função especializada com instruções versionadas, que toda saída de julgamento seja conferida por outra função independente, e que cada entrega melhore as instruções das funções por um ciclo de aprendizado com aprovação humana. A mesma estrutura deve servir a outra área trocando apenas o pacote de domínio.

## 2. Princípios

1. **Nenhuma decisão de title em Python** (lei vigente). O código valida forma, identidade, existência de evidência, orçamento e dependências entre tarefas. Julgamento é das funções; conferência de julgamento é de outra função de família independente; decisão final é do operador.
2. **Quem faz não confere.** Toda saída com efeito sobre o entregável passa por verificação cega de outra família de modelo antes de ser aceita.
3. **Agentes não conversam entre si.** Comunicam-se pelo Case File (quadro compartilhado): leem o estado, gravam saídas tipadas. Isso permite paralelismo, retomada exata e auditoria completa.
4. **Contratos, não conversa.** Cada tarefa tem entrada, saída em esquema JSON e critério de aceite declarados. Saída fora do esquema é recusada com erro nomeado e devolvida à função.
5. **Funções são dados.** Instruções, ferramentas permitidas, esquemas e exemplos de cada função vivem em fichas OKF versionadas em `agentes/`, nunca em prompt embutido no código.
6. **Núcleo separado de domínio.** `agentes/nucleo/` vale para qualquer projeto de due diligence documental; `agentes/pacotes/<area>/` traz vocabulário, fontes, template, precedentes e critérios da área. Fato de caso nunca entra em nenhum dos dois (invariante OKF 7).
7. **Nada melhora sem medida.** Mudança de instrução, modelo ou pacote só entra depois de rodar contra a bateria de avaliação (§7) sem regressão.
8. **Humano no fim de cada fronteira de risco.** Compras, credenciais, comunicação externa, publicação de conhecimento e aceite final são do operador.

## 3. Visão geral

```
                    PROJETO NOVO (escopo, template, fontes, orçamento)
                                     │
                              ┌──────▼──────┐
                              │ COORDENADOR │  lê o pacote de domínio, monta o grafo de tarefas
                              └──────┬──────┘
                                     │ grava tasks (DAG) no Case File
        ┌────────────────────────────┼─────────────────────────────┐
        ▼                            ▼                             ▼
  PESQUISADORES (por fonte)    ARQUIVISTA / CLASSIFICADOR     EXAMINADOR
        │                            │                             │
        └──────────────┬─────────────┴──────────────┬──────────────┘
                       ▼                            ▼
                 CASE FILE (Postgres): tasks, task_runs, claims, evidências, custo
                       │                            │
                       ▼                            ▼
                 VERIFICADOR (família B, cego) → divergência → ÁRBITRO → operador
                       │
                       ▼
                 REDATOR (template) → QA DE PACOTE → operador aprova → entrega
                       │
                       ▼
                 RETROSPECTIVO → fichas candidatas → verificação → aprovação → publicação versionada
```

## 4. Funções (núcleo)

As fichas completas estão em `agentes/nucleo/`. Resumo:

| Função | Ficha | Responsabilidade | Nível de modelo |
|---|---|---|---|
| Coordenador | `coordenador.md` | Decompor o projeto em tarefas, ordenar dependências, alocar orçamento, decidir a próxima ação, declarar parada | forte |
| Pesquisador | `pesquisador.md` | Executar buscas numa fonte específica e registrar resultados positivos e negativos com população, intervalo e termos | médio |
| Arquivista | `arquivista.md` | Capturar integralmente, conferir qualidade da captura, nomear, calcular hash, registrar no ledger | barato |
| Classificador | `classificador.md` | Dizer o que cada documento é e a que unidade/tract se vincula, com trecho literal | barato → médio |
| Examinador | `examinador.md` | Ler documentos e emitir claims de fato, efeito, cadeia e ônus com citação | forte |
| Verificador | `verificador.md` | Conferir às cegas cada claim material a partir só do documento e da página | forte, família B |
| Árbitro | `arbitro.md` | Examinar divergências entre examinador e verificador; resolver com citação ou escalar | forte |
| Redator | `redator.md` | Projetar claims aceitos no template do entregável, célula a célula, com proveniência | médio |
| Controlador de qualidade | `qa_pacote.md` | Conferir entregável × template × ledger × arquivos × links antes da entrega | médio + checagens de código |
| Retrospectivo | `retrospectivo.md` | Extrair lições da rodada em fichas OKF candidatas | médio |

O operador (Renato) é função externa: aprova plano, compras, credenciais, publicação de conhecimento e aceite final.

## 5. Pacotes de domínio

Um pacote é uma pasta OKF com: `index.md` (tipo `Domain Pack`), vocabulário e chaves de identidade, fontes e custos, template e mapa de campos, fluxo de tarefas padrão (gates), precedentes, critérios de verificação e itens da bateria de avaliação. Pacotes iniciais:

| Pacote | Origem do conhecimento | Situação |
|---|---|---|
| `title-texas-oil-gas-dd` | `knowledge_okf/` (Emirates, DDR) + Manual Técnico + SOP | conhecimento existe; migrar para o formato de pacote |
| `title-texas-surface` | `CIBOLA_RETROSPECTIVA_1128` (gates 0–5) + perfil Cibola + checkpoints 1128/1129 | fluxo descrito; faltam template/mapa de campos formais |
| `m-a-document-dd`, `brasil-fundiario` | a construir | fora do escopo desta fase; servem de teste de portabilidade do núcleo |

## 6. Mudanças no Case File

Novas tabelas (migração `0009_orquestracao.sql`), sem alterar tabelas existentes:

- `tasks`: `id, unit_id, parent_id, role, pack, title, input_json, output_schema, acceptance, depends_on[], budget_usd, priority, status (planejada|pronta|em_execucao|aguardando_verificacao|aguardando_operador|aceita|recusada|bloqueada|cancelada), created_by, created_at`.
- `task_runs`: `id, task_id, role_version (hash da ficha), pack_version, model, model_family, prompt_sha256, output_json, output_valid, cost_usd, tokens_in, tokens_out, started_at, finished_at, stop_reason, lease_until`.
- `role_versions`: hash e caminho de cada ficha de função/pacote usada em cada execução (reprodutibilidade).
- `escalations`: `task_id, motivo, pergunta, opções, resposta, respondido_por, respondido_em`.
- `eval_runs` e `eval_results`: execução da bateria (§7) por versão de função/pacote/modelo.

Reaproveitar sem mudança: `claims`, `verifications`, `research_items`, `negative_searches`, `collection_items`, `cost_entries`, `model_sessions`, `operator_decisions`, `deliverable_versions`, `derived_cells`.

Regras de código (forma, não julgamento):

1. Uma tarefa só fica `pronta` quando todas as `depends_on` estão `aceita`.
2. Um worker pega tarefa com `lease_until` (trava com expiração); queda libera a tarefa sem perda.
3. `output_json` é validado contra `output_schema`; inválido vira `recusada` com erro nomeado e nova tentativa limitada (máx. 2).
4. Tarefa de função com `verifica: obrigatória` na ficha só vai a `aceita` depois de `verifications` válida e concordante, ou de decisão do árbitro/operador.
5. Orçamento: soma de `task_runs.cost_usd` por unit respeita o teto vigente (`CASEFILE_TETO_UNIT_USD`); ao bater, todas as tarefas pendentes vão a `bloqueada` e o operador é avisado.
6. Verificador nunca recebe `output_json` da tarefa verificada (checagem mecânica de quarentena, como `afirmar_identidade`).
7. Toda tarefa registra `role_version` e `pack_version`.

## 7. Bateria de avaliação

Casos: Josh B, Bowen A, Webb B, Maxwell A (DDR oil & gas) e BBT-SNN-1128, 1129 (surface). Gabaritos ficam em quarentena por identidade (invariante 11). Métricas por função:

| Função | Métricas |
|---|---|
| Classificador | acurácia de tipo e de vínculo; taxa de `unplaced` |
| Pesquisador | recall de instrumentos do gabarito; buscas negativas com população declarada |
| Examinador | precisão e recall de claims materiais; falsas ausências; citação correta |
| Verificador | taxa de concordância; divergências reais detectadas (erros plantados); erros do verificador |
| Redator | células corretas; células com proveniência; fórmulas intactas |
| Sistema | custo por unit, horas do operador por unit, tarefas repetidas, escalonamentos |

Regra: nenhuma nova versão de ficha, pacote ou modelo é promovida com regressão nas métricas da sua função. Erros plantados (já usados na unidade sintética) entram na bateria.

## 8. Ciclo de aprendizado

1. Ao fechar uma unit, o Retrospectivo gera fichas candidatas com `status: draft`, `generated` e `sources` estruturadas.
2. O Verificador confere cada ficha contra as fontes citadas (`verified` com ator de máquina).
3. O operador aprova, corrige ou rejeita (`verified` com `human:renato`).
4. Publicação versionada via Training Suite (`training publish`), com escopo explícito.
5. Lição repetida em três units vira candidata a regra do pacote; regra válida para qualquer área sobe para o núcleo.

## 9. Ferramentas

Cada fonte vira ferramenta declarada na ficha do Pesquisador do pacote: leitura local (acervo), Drive, CountyRecords/TexasFile/CourthouseDirect via navegador, OCR. Permanecem com o operador: login, credenciais, pagamento, e toda operação paga acima do limite aprovado por rodada. `simulacao.py` continua valendo para replays.

## 10. Plano de implementação (para o Code), com checkpoints

| Etapa | Entrega | Aceite |
|---|---|---|
| A | Ler e validar as fichas de `agentes/` (loader + validador OKF v0.2: `type`, `status`, `generated`, esquemas de entrada/saída) | suíte verde; ficha inválida é recusada com erro nomeado |
| B | Migração 0009 + DAO + `RepoFake` para tasks/task_runs/escalations | testes de plumbing: dependências, lease, orçamento, quarentena do verificador |
| C | Worker genérico: pega tarefa, monta contexto (ficha da função + pacote + entradas), chama modelo, valida saída, grava | replay sintético com cliente roteirizado, sem modelo pago |
| D | Coordenador: gera o grafo de tarefas a partir do pacote e do censo | na Josh B (simulação), o grafo gerado cobre as tarefas do plano v1 existente |
| E | Bateria de avaliação sobre Josh B e 1128 com as funções atuais como linha de base | relatório de métricas por função; custo dentro do teto aprovado para avaliação |
| F | Execução paralela (N workers) e painel de tarefas no dashboard | duas units em paralelo sem conflito; retomada após queda simulada |
| G | Ciclo de aprendizado ligado à Training Suite | uma ficha candidata percorre draft → verificada → aprovada → publicada |

Cada etapa termina em checkpoint: o Code para, reporta com artefatos e só segue com aceite registrado do operador. Suíte verde antes e depois. Branch própria (`arquitetura-agentica`), nunca `main`.

## 11. Fora do escopo desta fase

Motor de orquestração próprio além do worker simples (avaliar Claude Agent SDK antes de escrever mais); pacotes M&A e Brasil; automação de compras; qualquer desligamento de geração antiga (só depois da etapa E provar paridade).

## 12. Decisões do operador (28/09/2026)

1. Arquitetura **aceita** como direção do sistema.
2. Teto da bateria de avaliação (etapa E): **US$ 25**.
3. Modelos: forte = Claude Opus; médio = Claude Sonnet; barato = Claude Haiku; verificador família B = OpenAI (chave já no `.env`).
4. Ordem dos pacotes: **`title-texas-surface` primeiro**, depois `title-texas-oil-gas-dd`.
