-- 0014 — Function files (issue 03, ADR 0001).
-- `function_files` indexes the write-once Case files a Function receives or
-- produces (the files are the source of truth; this table is rebuildable).
-- For outputs it carries the Call lifecycle per task run: a row means the
-- response was received; status says whether the output met its contract;
-- applied_at says the result was applied. Rejected outputs keep their file
-- and reason and are never applied.
--
-- Rows created while an output is applied cite that output file: the apply
-- transaction sets `plm.output_sha256` (set_config(..., true)) and every
-- insert into the tables below defaults to it.

CREATE TABLE function_files (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id     bigint NOT NULL REFERENCES units,
  task_id     bigint REFERENCES tasks,
  run_id      bigint REFERENCES task_runs,
  direction   text NOT NULL CHECK (direction IN ('input','output')),
  ordinal     int  NOT NULL,
  relative    text NOT NULL,
  sha256      char(64) NOT NULL,
  size_bytes  bigint NOT NULL,
  status      text NOT NULL CHECK (status IN ('recorded','accepted','rejected')),
  reason      jsonb NOT NULL DEFAULT '[]',
  artifact_id bigint REFERENCES operation_artifacts,
  received_at timestamptz NOT NULL DEFAULT now(),
  applied_at  timestamptz,
  UNIQUE (unit_id, relative),
  UNIQUE (run_id, direction, ordinal),
  CHECK (applied_at IS NULL OR (direction = 'output' AND status = 'accepted'))
);
CREATE INDEX ON function_files (task_id);

ALTER TABLE claims ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE verifications ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE plan_proposals ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE escalations ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE collection_items ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE negative_searches ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE triage_labels ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE operation_artifacts ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
ALTER TABLE operation_lessons ADD COLUMN output_sha256 char(64)
  DEFAULT nullif(current_setting('plm.output_sha256', true), '');
