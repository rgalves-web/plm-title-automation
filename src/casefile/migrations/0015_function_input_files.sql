-- 0015 — Function input files (issue 02, ADR 0001).
-- Before every terminal call, the exact context sent to the Function is
-- written as that task's input file (indexed in function_files with
-- direction 'input'). Its sha256 is recorded on the terminal call and, as
-- the latest input, on the task run.

ALTER TABLE operation_terminal_calls
  ADD COLUMN input_sha256 char(64),
  ADD COLUMN input_file_id bigint REFERENCES function_files;
ALTER TABLE task_runs ADD COLUMN input_sha256 char(64);
