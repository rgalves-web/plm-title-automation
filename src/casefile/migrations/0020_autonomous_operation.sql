-- Issue 13: autonomous operation. Renato declares a Lot (the Cases PLM
-- assigned) and its Job; each Case runs inside an envelope to its finished
-- deliverable. The exceptions queue is the existing escalations table, so
-- there is one queue; acceptances and Coordinator decisions are Case files,
-- indexed here.
CREATE TABLE operation_lots (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job jsonb NOT NULL,
  envelope jsonb NOT NULL,
  created_by text NOT NULL,
  note text NOT NULL,
  command_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz
);
CREATE TABLE operation_lot_cases (
  lot_id bigint NOT NULL REFERENCES operation_lots,
  unit_id bigint NOT NULL REFERENCES units,
  status text NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'stopped', 'deliverable_ready', 'released')),
  stop_reason text NOT NULL DEFAULT '',
  turn_cap int NOT NULL CHECK (turn_cap > 0),
  deliverable_artifact_id bigint REFERENCES operation_artifacts,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (lot_id, unit_id)
);
CREATE UNIQUE INDEX operation_lot_cases_one_open_lot
  ON operation_lot_cases (unit_id) WHERE status <> 'released';

ALTER TABLE escalations
  ADD COLUMN kind text NOT NULL DEFAULT 'escalation',
  ADD COLUMN detail jsonb NOT NULL DEFAULT '{}',
  ADD COLUMN lot_id bigint REFERENCES operation_lots,
  ADD COLUMN exception_key text,
  ADD COLUMN resolution jsonb;
CREATE UNIQUE INDEX escalations_exception_key
  ON escalations (unit_id, exception_key) WHERE exception_key IS NOT NULL;

CREATE TABLE operation_acceptances (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  lot_id bigint REFERENCES operation_lots,
  unit_id bigint NOT NULL REFERENCES units,
  task_id bigint NOT NULL REFERENCES tasks,
  claim_types text[] NOT NULL DEFAULT '{}',
  relative text NOT NULL,
  sha256 char(64) NOT NULL,
  sampled boolean NOT NULL,
  audit_mark text CHECK (audit_mark IN ('right', 'wrong')),
  audit_note text NOT NULL DEFAULT '',
  marked_by text,
  marked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, relative)
);
CREATE TABLE operation_autoaccept_suspensions (
  claim_type text PRIMARY KEY,
  reason text NOT NULL,
  suspended_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE operation_coordinator_decisions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  lot_id bigint REFERENCES operation_lots,
  unit_id bigint NOT NULL REFERENCES units,
  kind text NOT NULL,
  relative text NOT NULL,
  sha256 char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (unit_id, relative)
);
