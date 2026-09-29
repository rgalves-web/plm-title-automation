# ORDEM PARA O CODE — Arquitetura Agêntica, Etapa A (fichas como dados)

_Emitida em 28/09/2026 pelo operador (Renato) via Cowork. Autocontida: você não tem acesso à conversa que a originou._

## Contexto em cinco linhas

1. O operador aceitou em 28/09 a direção descrita em `docs/ARQUITETURA_AGENTICA_v1.md` (leia inteiro; §12 traz as decisões).
2. A lei continua sendo `docs/ARQUITETURA_GOVERNANTE.md` e as invariantes de `CLAUDE.md`: nenhuma decisão de title em Python.
3. As funções da firma de agentes e os pacotes de domínio vivem como fichas OKF v0.2 em `agentes/` (escritas pelo Cowork, `status: draft`).
4. Ordem de pacotes: `title-texas-surface` primeiro, depois `title-texas-oil-gas-dd`.
5. Esta etapa não chama modelo, não toca banco e não gasta API.

## Passo 0 — Situação do git (checkpoint 0, pare e reporte)

1. `git status` e `git log --oneline -5` na branch atual (esperada: `cibola-surface-preparation`).
2. A preparação Cibola de 12/09 (`docs/CIBOLA_PREPARACAO.md`, `src/casefile/project_profile.py`, testes associados, alterações em `CLAUDE.md`) pode estar sem commit. Rode a suíte completa (`python -m pytest -q`). Se verde, reporte a lista exata de arquivos que seriam commitados.
3. `agentes/`, `docs/ARQUITETURA_AGENTICA_v1.md` e esta ordem também estão sem commit.
4. **Pare e reporte** a lista e o resultado da suíte. Só prossiga com aceite do operador. Plano esperado após aceite: commit da preparação Cibola na branch atual; criar `arquitetura-agentica` a partir dela; commit de `agentes/` e dos dois docs na nova branch.

## Passo A — Carregador e validador das fichas

Crie `src/casefile/agentes.py` (plumbing puro, sem julgamento):

1. **Carregar** todos os `.md` sob `agentes/` com frontmatter YAML. `index.md` e `log.md` seguem as regras de arquivo reservado do OKF v0.2 (o `index.md` raiz só pode ter `okf_version`).
2. **Validar por tipo** e devolver erros nomeados (nunca corrigir em silêncio):
   - todos: `type` não vazio; `status` ∈ {draft, stable, deprecated}; `generated.by` e `generated.at`; `verified` lista (vazia permitida); atores no formato `agente/versao`, `human:<id>` ou `process:<id>`;
   - `Role`: `title`, `description`, `saida_esquema`, `nivel_modelo` ∈ {forte, medio, barato, barato_a_medio}, `verifica`, `ferramentas` (lista);
   - `Domain Pack`: `title`, `description`, `sources` com `resource` e `id`;
   - `Lesson`: `funcao` (deve existir como Role), `escopo.pacote` (deve existir como Domain Pack), `sources` com `resource` e `id`;
   - links markdown internos quebrados: **aviso**, não erro (OKF tolera).
3. **Esquemas de saída**: crie `agentes/esquemas/<nome>.json` (JSON Schema draft 2020-12) para os 10 valores de `saida_esquema`. Derive os campos do texto de cada ficha (seções "Saída"/"Regras"). Onde a ficha e o Case File já têm formato (claims: `src/casefile/validacao.py` e `migrations/0002_seed_claim_types.sql`; verificações: `migrations/0007_auditoria_verificacao.sql`), **o esquema segue o formato existente**. O validador acusa `saida_esquema` sem arquivo correspondente.
4. **Identidade**: função `versao(caminho)` = sha256 do conteúdo do arquivo (será gravada em `task_runs.role_version` na etapa B).
5. **CLI**: `python -X utf8 -m src.casefile agentes validar` imprime tabela por arquivo (tipo, status, erros, avisos) e sai com código ≠ 0 se houver erro. `python -X utf8 -m src.casefile agentes listar` mostra funções, pacotes e lições com versão.

## Testes (plumbing, nunca julgamento)

- ficha válida de cada tipo carrega; cada campo obrigatório ausente gera o erro nomeado correspondente;
- `index.md` raiz com chave diferente de `okf_version` é recusado;
- lição com `funcao` ou `escopo.pacote` inexistente é recusada;
- `saida_esquema` sem arquivo é recusado;
- link quebrado gera aviso, não erro;
- `versao()` muda quando um byte muda e é estável quando não muda;
- o conjunto real de `agentes/` do repo passa na validação (teste de integração sobre os arquivos reais).

## Critério de aceite (checkpoint A, pare e reporte)

1. Suíte completa verde antes e depois; número de testes novos.
2. `agentes validar` sobre o repo: zero erros (avisos listados).
3. Os 10 esquemas criados, com nota curta de onde cada campo veio (ficha ou formato existente).
4. Divergências encontradas entre fichas e código existente listadas para o operador decidir (não resolva mudando ficha por conta própria; invariante 7).
5. Commits na branch `arquitetura-agentica`, nunca em `main`.

## Fora do escopo desta etapa

Migração 0009, tabelas de tarefas, worker, coordenador, qualquer chamada de modelo, publicação de lições (as 3 lições em `pacotes/title-texas-surface/licoes/` ficam `draft` até aprovação do operador), mudança em `src/minorh`, `src/examinador`, `src/dd`, `src/knowledge`.
