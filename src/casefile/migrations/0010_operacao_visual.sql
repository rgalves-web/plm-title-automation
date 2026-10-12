-- Execution state is separate from title acceptance. No title decisions here.
CREATE TABLE operation_cases (
  unit_id bigint PRIMARY KEY REFERENCES units,
  revision bigint NOT NULL DEFAULT 1,
  execution_state text NOT NULL DEFAULT 'paused' CHECK (execution_state IN ('paused','running','waiting','finished')),
  reference_budget_usd numeric(10,4) NOT NULL DEFAULT 50,
  approved_budget_usd numeric(10,4) NOT NULL DEFAULT 0 CHECK (approved_budget_usd >= 0),
  approval jsonb NOT NULL DEFAULT '{}',
  scope jsonb NOT NULL DEFAULT '{}',
  profile jsonb NOT NULL DEFAULT '{}',
  last_dispatched_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE operation_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint REFERENCES units,
  task_id bigint REFERENCES tasks,
  kind text NOT NULL,
  actor text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}',
  at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON operation_events (unit_id,id);
CREATE TABLE operation_commands (
  command_id text PRIMARY KEY,
  body_sha256 char(64) NOT NULL,
  unit_id bigint REFERENCES units,
  response jsonb NOT NULL,
  at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE operation_artifacts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint NOT NULL REFERENCES units,
  task_id bigint REFERENCES tasks,
  kind text NOT NULL,
  path text NOT NULL,
  sha256 char(64) NOT NULL,
  size_bytes bigint NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id,path,sha256)
);
CREATE INDEX ON operation_artifacts (unit_id,kind);
CREATE TABLE operation_artifact_links (
  artifact_id bigint NOT NULL REFERENCES operation_artifacts,
  unit_id bigint NOT NULL REFERENCES units,
  allocation jsonb NOT NULL,
  linked_by text NOT NULL,
  PRIMARY KEY (artifact_id,unit_id)
);
CREATE TABLE operation_requirements (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint NOT NULL REFERENCES units,
  report_sha256 char(64) NOT NULL,
  criterion text NOT NULL CHECK (criterion IN ('Q1','Q2','Q3','Q4','Q5','Q6')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','observed','verified','invalidated')),
  evidence jsonb NOT NULL DEFAULT '{}',
  reviewed_by text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id,report_sha256,criterion)
);
CREATE TABLE operation_source_jobs (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint NOT NULL REFERENCES units,
  task_id bigint REFERENCES tasks,
  source text NOT NULL,
  request_key char(64) NOT NULL,
  request jsonb NOT NULL,
  status text NOT NULL DEFAULT 'requested' CHECK (status IN ('requested','running','complete','blocked')),
  receipt jsonb NOT NULL DEFAULT '{}',
  owner text NOT NULL DEFAULT 'Renato',
  impact text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id,request_key)
);
CREATE TABLE operation_resources (
  resource text PRIMARY KEY,
  holder text NOT NULL,
  lease_until timestamptz NOT NULL
);
CREATE TABLE operation_lessons (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint NOT NULL REFERENCES units,
  task_id bigint REFERENCES tasks,
  version char(64) NOT NULL UNIQUE,
  card jsonb NOT NULL,
  status text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','verified','approved','rejected','withdrawn')),
  verification jsonb NOT NULL DEFAULT '{}',
  decision jsonb NOT NULL DEFAULT '{}',
  release_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE operation_services (
  name text PRIMARY KEY,
  heartbeat_at timestamptz NOT NULL DEFAULT now(),
  detail jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE operation_followups (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint NOT NULL REFERENCES units,
  ref text NOT NULL,
  role text NOT NULL,
  title text NOT NULL,
  input_json jsonb NOT NULL,
  output_schema text NOT NULL,
  budget_usd numeric(10,4) NOT NULL CHECK (budget_usd > 0),
  task_id bigint REFERENCES tasks,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(unit_id,ref)
);
ALTER TABLE tasks ADD CONSTRAINT task_budget_finite CHECK
  (budget_usd <> 'NaN'::numeric AND budget_usd <> 'Infinity'::numeric AND budget_usd <> '-Infinity'::numeric);
ALTER TABLE task_runs ADD COLUMN operation_session_id bigint REFERENCES model_sessions;
ALTER TABLE task_runs ADD COLUMN knowledge_release_id text;
ALTER TABLE task_runs ADD COLUMN usage_state text NOT NULL DEFAULT 'legacy';
CREATE TABLE operation_requests (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES task_runs,
  ordinal int NOT NULL,
  status text NOT NULL DEFAULT 'inflight' CHECK (status IN ('inflight','confirmed','nonbillable','unknown')),
  provider_request_id text NOT NULL DEFAULT '',
  usage jsonb NOT NULL DEFAULT '{}',
  cost_usd numeric(10,6),
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  UNIQUE(run_id,ordinal)
);
