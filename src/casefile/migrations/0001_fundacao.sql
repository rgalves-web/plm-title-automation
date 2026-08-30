-- 0001 — esqueleto completo do Case File por Unit.
-- Convenções: identidade de conteúdo por sha256 COMPLETO (64 hex); estados da
-- máquina com os nomes do documento CTO; tabelas rígidas só para o que o
-- código possui de fato (arquivos, estados, sessões, custo, planos,
-- pesquisas); entidades de title vivem como claims + views de projeção.

-- identidade e processo -------------------------------------------------------
CREATE TABLE projects (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  engagement  text NOT NULL,
  name        text NOT NULL,
  root_path   text NOT NULL UNIQUE,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE units (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id     bigint NOT NULL REFERENCES projects,
  name_input     text NOT NULL,
  canonical_name text NOT NULL,
  folder_path    text NOT NULL,
  state          text NOT NULL DEFAULT 'INDICADA'
                 CHECK (state IN ('INDICADA','PLANEJANDO','COLETANDO',
                                  'EXAMINANDO','VERIFICANDO','PREENCHENDO',
                                  'AUDITANDO','AGUARDANDO_RENATO','LIBERADA',
                                  'BLOQUEADA')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, canonical_name)
);

CREATE TABLE unit_state_transitions (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id    bigint NOT NULL REFERENCES units,
  from_state text NOT NULL,
  to_state   text NOT NULL,
  event      text NOT NULL,
  actor      text NOT NULL,
  note       text NOT NULL DEFAULT '',
  at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON unit_state_transitions (unit_id, at);

-- fontes: identidade por bytes ------------------------------------------------
CREATE TABLE source_files (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sha256        char(64) NOT NULL UNIQUE,
  size_bytes    bigint NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now()
);

-- O mesmo conteúdo aparece em N caminhos (um TO copiado em até 6 tracts) e o
-- mesmo NOME aparece com bytes diferentes (o XREF dentro da Webb B difere do
-- master da raiz). Sighting é observação de caminho; source_file é identidade.
CREATE TABLE file_sightings (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_file_id bigint NOT NULL REFERENCES source_files,
  unit_id        bigint REFERENCES units,
  container_path text NOT NULL,
  zip_member     text NOT NULL DEFAULT '',
  logical_name   text NOT NULL,
  origin         text NOT NULL CHECK (origin IN
                   ('unit_files','unit_folder','project_reference',
                    'entrega','outro')),
  mtime          timestamptz,
  seen_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_file_id, container_path, zip_member)
);
CREATE INDEX ON file_sightings (unit_id);
CREATE INDEX ON file_sightings (logical_name);

CREATE TABLE model_sessions (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id     bigint NOT NULL REFERENCES units,
  command     text NOT NULL,
  model       text NOT NULL,
  started_at  timestamptz NOT NULL DEFAULT now(),
  ended_at    timestamptz,
  stop_reason text NOT NULL DEFAULT '',
  turns       int  NOT NULL DEFAULT 0,
  usage       jsonb NOT NULL DEFAULT '{}',
  cost_usd    numeric(10,4),
  log_path    text NOT NULL DEFAULT ''
);

CREATE TABLE triage_labels (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_file_id bigint NOT NULL REFERENCES source_files,
  unit_id        bigint NOT NULL REFERENCES units,
  label          text NOT NULL,
  summary        text NOT NULL,
  confidence     text NOT NULL CHECK (confidence IN ('alta','media','baixa')),
  session_id     bigint REFERENCES model_sessions,
  at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_file_id, unit_id)
);

-- ledger de afirmações ----------------------------------------------------------
CREATE TABLE claim_types (
  claim_type      text PRIMARY KEY,
  description     text NOT NULL,
  required_fields jsonb NOT NULL DEFAULT '[]',
  active          boolean NOT NULL DEFAULT true
);

CREATE TABLE claims (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id       bigint NOT NULL REFERENCES units,
  claim_type    text   NOT NULL REFERENCES claim_types,
  entity        text   NOT NULL,
  value         jsonb  NOT NULL,
  source_sha256 char(64) NOT NULL REFERENCES source_files (sha256),
  page          text   NOT NULL,
  evidence      text   NOT NULL CHECK (length(evidence) > 0),
  confidence    text   NOT NULL CHECK (confidence IN ('alta','media','baixa')),
  materiality   text   NOT NULL DEFAULT 'media'
                CHECK (materiality IN ('alta','media','baixa')),
  status        text   NOT NULL DEFAULT 'ativo'
                CHECK (status IN ('ativo','substituido','retirado')),
  superseded_by bigint REFERENCES claims,
  session_id    bigint NOT NULL REFERENCES model_sessions,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON claims (unit_id, claim_type) WHERE status = 'ativo';

-- pesquisas ---------------------------------------------------------------------
CREATE TABLE research_items (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id     bigint NOT NULL REFERENCES units,
  title       text NOT NULL,
  what        text NOT NULL,
  where_      text NOT NULL,
  method      text NOT NULL,
  status      text NOT NULL DEFAULT 'aberta'
              CHECK (status IN ('aberta','executada','cancelada')),
  session_id  bigint REFERENCES model_sessions,
  created_at  timestamptz NOT NULL DEFAULT now(),
  executed_at timestamptz
);

CREATE TABLE research_item_claims (
  research_item_id bigint NOT NULL REFERENCES research_items,
  claim_id         bigint NOT NULL REFERENCES claims,
  PRIMARY KEY (research_item_id, claim_id)
);

-- plano de investigação, versionado, com aprovação -------------------------------
CREATE TABLE investigation_plans (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id       bigint NOT NULL REFERENCES units,
  version       int    NOT NULL,
  markdown      text   NOT NULL,
  summary       jsonb  NOT NULL DEFAULT '{}',
  session_id    bigint NOT NULL REFERENCES model_sessions,
  status        text   NOT NULL DEFAULT 'proposto'
                CHECK (status IN ('proposto','aprovado','rejeitado',
                                  'substituido')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  decided_by    text,
  decided_at    timestamptz,
  decision_note text NOT NULL DEFAULT '',
  UNIQUE (unit_id, version)
);

-- custo ---------------------------------------------------------------------------
CREATE TABLE cost_entries (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id    bigint NOT NULL REFERENCES units,
  category   text NOT NULL,
  amount_usd numeric(10,4) NOT NULL,
  detail     jsonb NOT NULL DEFAULT '{}',
  at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON cost_entries (unit_id);

-- esqueleto pós-VS1 (nasce vazio; nada no VS1 escreve aqui) -----------------------
CREATE TABLE operator_decisions (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id    bigint NOT NULL REFERENCES units,
  kind       text NOT NULL,
  question   text NOT NULL,
  answer     text NOT NULL DEFAULT '',
  claim_id   bigint REFERENCES claims,
  decided_at timestamptz
);

CREATE TABLE deliverable_versions (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id    bigint NOT NULL REFERENCES units,
  kind       text NOT NULL,
  version    int  NOT NULL,
  path       text NOT NULL,
  sha256     char(64),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, kind, version)
);

CREATE TABLE derived_cells (
  id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  deliverable_version_id bigint NOT NULL REFERENCES deliverable_versions,
  sheet                  text NOT NULL,
  cell_ref               text NOT NULL,
  value                  text,
  claim_ids              bigint[] NOT NULL DEFAULT '{}',
  status                 text NOT NULL DEFAULT 'proposta'
);

-- views de projeção: leitura relacional dos claims ativos -------------------------
CREATE VIEW vw_unit_leases AS
  SELECT unit_id, entity, value->>'lease_no' AS lease_no,
         value->>'lessor' AS lessor, source_sha256, page, confidence, id
  FROM claims WHERE claim_type = 'lease_in_unit' AND status = 'ativo';

CREATE VIEW vw_unit_tracts AS
  SELECT unit_id, entity, value->>'tract_no' AS tract_no,
         source_sha256, page, confidence, id
  FROM claims WHERE claim_type = 'tract' AND status = 'ativo';

CREATE VIEW vw_unit_tos AS
  SELECT unit_id, entity, value->>'to_id' AS to_id,
         source_sha256, page, confidence, id
  FROM claims WHERE claim_type = 'title_opinion' AND status = 'ativo';

CREATE VIEW vw_unit_sellers AS
  SELECT unit_id, entity, value->>'party' AS party, value->>'papel' AS papel,
         source_sha256, page, confidence, id
  FROM claims WHERE claim_type = 'seller_interest' AND status = 'ativo';

CREATE VIEW vw_unit_cost AS
  SELECT unit_id, round(sum(amount_usd), 4) AS total_usd, count(*) AS entries
  FROM cost_entries GROUP BY unit_id;
