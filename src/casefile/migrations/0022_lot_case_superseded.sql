-- Issue 17: a stopped Lot case can be superseded by a new Lot declaration
-- for the same Case (a wider envelope). The old row stays as history.
ALTER TABLE operation_lot_cases DROP CONSTRAINT IF EXISTS operation_lot_cases_status_check;
ALTER TABLE operation_lot_cases ADD CONSTRAINT operation_lot_cases_status_check
  CHECK (status IN ('running', 'stopped', 'deliverable_ready', 'released', 'superseded'));
DROP INDEX IF EXISTS operation_lot_cases_one_open_lot;
CREATE UNIQUE INDEX operation_lot_cases_one_open_lot
  ON operation_lot_cases (unit_id) WHERE status NOT IN ('released', 'superseded');
