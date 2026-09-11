# Case File por Unit — Fundação + Vertical Slice 1 (Unit → Investigation Plan)

Atualização posterior (11/09/2026): [integração da Training Suite](TRAINING_SUITE_INTEGRACAO.md),
migração 0008, publicações/contextos versionados e revisão rastreável. O registro
do VS1 abaixo permanece histórico.

_Implementado em 2026-08-30, branch `casefile-vs1`. Direção estratégica aceita
pelo operador: reorganizar o produto em torno de um Case File por Unit; o
`minorh` congela e permanece para replays. Doc governante
(`ARQUITETURA_GOVERNANTE.md`) segue valendo: nenhuma decisão de title em
Python — o modelo afirma, o código valida forma, identidade e existência de
evidência._

## O que o VS1 faz

```
python -m src.casefile indicar "Josh B Unit"     resolve a pasta pelo NOME; unit INDICADA
python -m src.casefile planejar                  censo -> triagem -> Examinador -> plano
python -m src.casefile plano                     imprime o plano (sem modelo)
python -m src.casefile aprovar | rejeitar --motivo="..."
python -m src.casefile estado | unidades         painel textual (sem modelo)
python -m src.casefile db migrar | db estado
```

O entregável é o **Unit Investigation Plan** (versionado no banco +
`<UNIT>/_casefile/PLANO_INVESTIGACAO_vN.md`): inventário de XREFs, TOs,
tracts, sellers, documentos presentes/ausentes, divergências e pesquisas —
toda afirmação material como **claim com evidência obrigatória** (sha256 do
documento + página + trecho literal). Estados exercitados:
`INDICADA → PLANEJANDO → AGUARDANDO_RENATO → (COLETANDO | PLANEJANDO)`.

## Setup do PostgreSQL (uma vez, pelo operador)

O PostgreSQL 16 já roda como serviço nesta máquina (`postgresql-x64-16`).
Criar role e bancos (pede a senha do superusuário `postgres`):

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE ROLE plm LOGIN PASSWORD '<escolher>';"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE plm_casefile OWNER plm;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE plm_casefile_test OWNER plm;"
```

Depois, no `.env` (NUNCA commitado): `CASEFILE_DSN`, `CASEFILE_TEST_DSN`,
`CASEFILE_PROJECT_ROOT` (ver `.env.example`) e:

```powershell
python -m src.casefile db migrar
```

**Confidencialidade:** trechos de evidência no banco são dado de cliente. O
banco é local, o DSN vive só no `.env`, backup só via `pg_dump` local —
invariante 8 (nada sai da máquina) se aplica ao banco inteiro.

## Desenho (o que mora onde)

| Módulo | Papel |
|---|---|
| `db.py` + `migrations/*.sql` | conexão psycopg3 + migrações SQL versionadas com checksum |
| `repo.py` | DAO — a interface que `tests/helpers_casefile.py::RepoFake` implementa em memória |
| `estados.py` | máquina de estados CTO (INDICADA→…→LIBERADA + BLOQUEADA), transições sempre registradas |
| `referencia.py` | resolver por nome (extraído de `src/dd/project_reference.py` + `agreements_xref.unit_identity_tokens`) |
| `acervo.py` | índice RECURSIVO read-in-place; `Acervo(Corpus)` herda read_page/search e o PageCache global |
| `censo.py` | sha256 completo de cada conteúdo → `source_files` + `file_sightings`; origem classificada; homônimos expostos |
| `custo.py` | teto duro por unit (`CASEFILE_TETO_UNIT_USD`, default 25) — recusa limpa ANTES de gastar |
| `sessao.py` | sessões via `src/examinador/loop.py::run_loop` (import); custo no banco antes de qualquer print |
| `triagem.py` | Haiku rotula o censo (padrão do `triador.py`), rótulos por sha256 em `triage_labels` |
| `ferramentas.py` | leitura importada de `src/minorh/ferramentas.py`; escrita nova: `registrar_claims` / `registrar_pesquisas` / `propor_plano` |
| `validacao.py` | validação ESTRUTURAL de claims (tipo, required_fields, documento→sha256, trecho) — nunca conteúdo |
| `plano.py` | plano versionado + contagens declaradas × banco lado a lado |
| `caneta.py` | write-root: arquivos só em `<UNIT>/_casefile/`; FILES/, SUBMISSION PLM/ e `_minorh/` intocáveis |

Decisões registradas:

- **Identidade por sha256 completo** (64 hex) em todo o esquema — o Drive real
  tem o mesmo TO copiado em até 6 tracts (1 conteúdo, N sightings) e o mesmo
  nome com bytes diferentes (XREF da Webb B ≠ master; 50 casos na Josh B).
  Nome ambíguo num claim = erro nomeado com os hashes; o modelo cita
  `sha256:<hash>`.
- **Entrega quarentenada por origem**: sightings sob `Landman Submitted`/
  `SUBMISSION*` entram no censo como `origin='entrega'` e ficam FORA do
  acervo da sessão por padrão (invariante 11 — na Josh B a entrega é o
  gabarito de fato).
- **Tracts/sellers/TOs como claims + views** (`vw_unit_leases`, `vw_unit_tos`,
  …), não tabelas rígidas — LLM-first; tabelas rígidas só para o que o código
  possui (arquivos, estados, sessões, custo, planos, pesquisas).
- **Pertencimento ao XREF é julgamento do modelo** com duas vias no prompt
  (coluna UNIT LEVEL NAME quando existir; senão o contrato DPU `K…`);
  divergência vira claim `divergence`, nunca escolha de código.
- **SQLite rejeitado até para testes** — testes de banco rodam no Postgres
  real (`CASEFILE_TEST_DSN`, schema temporário por teste, skip visível sem
  DSN); o resto usa `RepoFake`.

## Testes

`tests/test_casefile_*.py` — 27 de encanamento (estados, referencia, censo,
validacao, custo, cli, VS1 fim-a-fim com cliente roteirizado) + 8 `@postgres`
(migrações, DAO, FKs de evidência, versionamento de plano). Nenhuma asserção
conclui title. Suíte completa: 966 verdes.

## Fora do escopo do VS1 (próximos slices)

VS2 coleta (`research_items` nasce; `minorh coletar` continua onde está) ·
VS3 exame documental (fact/conclusion inativos no vocabulário) · VS4+
projeção/`derived_cells`/template compiler/verificação cega/grafo/dashboard ·
promoção versionada de conhecimento · desligamento do minorh.

## Pendências

1. Operador: criar role/DBs (receita acima) e preencher o `.env`; rodar
   `db migrar`; a partir daí os 8 testes `@postgres` rodam de verdade.
2. E7 — smoke com modelo na Josh B real (`planejar`) após 01/09 (limite
   mensal Anthropic), com teto vigente. Achados viram BACKLOG, não escopo.
