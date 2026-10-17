-- A task's attempts count only runs that launched a model call (a terminal
-- call marked launched, or a recorded API request). Terminal calls from before
-- launch tracking (0017) that were not stopped before their process are marked
-- launched at their start time. A run that a Round stopped before any delivery
-- delivered nothing, so it carries no output validity.
UPDATE operation_terminal_calls SET launched_at = started_at
 WHERE launched_at IS NULL AND status <> 'running'
   AND failure NOT LIKE 'terminal_input_%';
UPDATE task_runs SET output_valid = NULL
 WHERE output_valid IS FALSE
   AND (output_json IS NULL OR output_json = 'null'::jsonb)
   AND stop_reason IN ('round_focus_complete', 'round_turn_cap_reached',
                       'round_not_approved');
