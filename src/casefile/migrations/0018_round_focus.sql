-- Issue 10: a Round may focus on one task. Follow-ups record the task they
-- came from, so the focus covers that task and everything it produced.
ALTER TABLE operation_rounds ADD COLUMN focus_task_id bigint REFERENCES tasks;
ALTER TABLE operation_followups ADD COLUMN parent_task_id bigint REFERENCES tasks;
ALTER TABLE tasks ADD COLUMN parent_task_id bigint REFERENCES tasks;
