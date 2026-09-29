-- 0009 — orquestração da firma de agentes (ARQUITETURA_AGENTICA_v1 §6,
-- etapa B). Tabelas novas; nenhuma tabela existente muda.
-- O código aqui só guarda forma: dependências, trava com expiração,
-- orçamento, versão das fichas, quarentena. Julgamento é das funções.
--
-- tasks.priority: menor número sai primeiro (1 antes de 2).
-- tasks.verificacao: o que a tarefa precisa depois de uma saída válida —
--   nenhuma (aceita direto), obrigatoria (verificação cega concordante),
--   operador (aceite humano), obrigatoria_e_operador (as duas).
-- task_runs.lease_until: a trava do worker; vencida, a tarefa volta a
--   `pronta` sem perda (o run fica fechado com stop_reason lease_expirado).

CREATE TABLE role_versions (
  sha256     char(64) PRIMARY KEY,
  path       text NOT NULL,
  kind       text NOT NULL,
  name       text NOT NULL,
  content    text NOT NULL,
  first_seen timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id       bigint NOT NULL REFERENCES units,
  parent_id     bigint REFERENCES tasks,
  ref           text   NOT NULL CHECK (length(ref) > 0),
  role          text   NOT NULL,
  pack          text   NOT NULL DEFAULT '',
  title         text   NOT NULL,
  input_json    jsonb  NOT NULL DEFAULT '{}',
  output_schema text   NOT NULL,
  acceptance    text   NOT NULL,
  depends_on    bigint[] NOT NULL DEFAULT '{}',
  budget_usd    numeric(10,4) NOT NULL DEFAULT 0 CHECK (budget_usd >= 0),
  priority      int    NOT NULL DEFAULT 0,
  verificacao   text   NOT NULL CHECK (verificacao IN
                  ('nenhuma','obrigatoria','operador',
                   'obrigatoria_e_operador')),
  justificativa text   NOT NULL DEFAULT '',
  status        text   NOT NULL DEFAULT 'planejada' CHECK (status IN
                  ('planejada','pronta','em_execucao',
                   'aguardando_verificacao','aguardando_operador','aceita',
                   'recusada','bloqueada','cancelada')),
  created_by    text   NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, ref)
);
CREATE INDEX ON tasks (unit_id, status);

CREATE TABLE task_transitions (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id     bigint NOT NULL REFERENCES tasks,
  from_status text   NOT NULL,
  to_status   text   NOT NULL,
  actor       text   NOT NULL,
  note        text   NOT NULL DEFAULT '',
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON task_transitions (task_id);

CREATE TABLE task_runs (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id           bigint NOT NULL REFERENCES tasks,
  worker            text   NOT NULL,
  role_version      char(64) NOT NULL REFERENCES role_versions,
  pack_version      char(64) REFERENCES role_versions,
  model             text   NOT NULL DEFAULT '',
  model_family      text   NOT NULL DEFAULT '',
  prompt_sha256     char(64),
  output_json       jsonb,
  output_valid      boolean,
  validation_errors jsonb  NOT NULL DEFAULT '[]',
  cost_usd          numeric(10,4) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
  tokens_in         int    NOT NULL DEFAULT 0,
  tokens_out        int    NOT NULL DEFAULT 0,
  started_at        timestamptz NOT NULL DEFAULT now(),
  finished_at       timestamptz,
  stop_reason       text   NOT NULL DEFAULT '',
  lease_until       timestamptz NOT NULL
);
CREATE INDEX ON task_runs (task_id);
-- no máximo um run aberto por tarefa: dois workers nunca executam a mesma
CREATE UNIQUE INDEX task_runs_um_aberto ON task_runs (task_id)
  WHERE finished_at IS NULL;

CREATE TABLE task_claims (
  task_id  bigint NOT NULL REFERENCES tasks,
  claim_id bigint NOT NULL REFERENCES claims,
  PRIMARY KEY (task_id, claim_id)
);

CREATE TABLE escalations (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id        bigint NOT NULL REFERENCES units,
  task_id        bigint REFERENCES tasks,
  motivo         text   NOT NULL,
  pergunta       text   NOT NULL,
  opcoes         jsonb  NOT NULL DEFAULT '[]',
  resposta       text   NOT NULL DEFAULT '',
  respondido_por text   NOT NULL DEFAULT '',
  respondido_em  timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON escalations (unit_id) WHERE respondido_em IS NULL;
