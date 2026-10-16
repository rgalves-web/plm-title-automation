ALTER TABLE task_runs ADD COLUMN execution_backend text NOT NULL DEFAULT 'api';
CREATE TABLE operation_terminal_calls (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id bigint NOT NULL REFERENCES task_runs,
  ordinal int NOT NULL,
  family text NOT NULL CHECK (family IN ('A','B')),
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','completed','interrupted')),
  receipt jsonb NOT NULL DEFAULT '{}',
  failure text NOT NULL DEFAULT '',
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  UNIQUE(run_id,ordinal)
);
