-- Issue 14: every failed terminal call keeps its failure text (a Case file,
-- indexed here) and its class, so the Coordinator can wait on a subscription
-- limit and stop on a crash. A Lot Case waiting on a limit resumes by itself
-- at resume_at.
ALTER TABLE operation_terminal_calls
  ADD COLUMN failure_class text
    CHECK (failure_class IN ('login', 'limit', 'invalid_output', 'crash')),
  ADD COLUMN failure_text text,
  ADD COLUMN failure_relative text;
ALTER TABLE operation_lot_cases ADD COLUMN resume_at timestamptz;
