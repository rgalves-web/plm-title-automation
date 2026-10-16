-- Issue 08: every Round Renato approves carries a turn cap. A turn is one
-- terminal call whose process was launched; it counts toward the cap of the
-- Round it was launched in and is never converted to dollars.
CREATE TABLE operation_rounds (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unit_id bigint NOT NULL REFERENCES units,
  number int NOT NULL CHECK (number > 0),
  turn_cap int NOT NULL CHECK (turn_cap > 0),
  approved_by text NOT NULL,
  note text NOT NULL,
  command_id text NOT NULL,
  approved_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  close_reason text NOT NULL DEFAULT '',
  UNIQUE (unit_id, number)
);
ALTER TABLE operation_terminal_calls
  ADD COLUMN round_id bigint REFERENCES operation_rounds,
  ADD COLUMN launched_at timestamptz;
