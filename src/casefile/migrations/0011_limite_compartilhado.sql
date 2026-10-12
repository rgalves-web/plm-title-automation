CREATE TABLE operation_spending_limits (
  id text PRIMARY KEY,
  kind text NOT NULL,
  unit_ids bigint[] NOT NULL,
  budget_usd numeric(12,6) NOT NULL CHECK
    (budget_usd > 0 AND budget_usd <> 'NaN'::numeric AND budget_usd <> 'Infinity'::numeric),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded')),
  approved_by text NOT NULL,
  approval_note text NOT NULL,
  activated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX operation_one_active_spending_limit ON operation_spending_limits(kind) WHERE status='active';
ALTER TABLE operation_requests ADD COLUMN spend_limit_id text REFERENCES operation_spending_limits;
ALTER TABLE operation_requests ADD COLUMN reserved_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK
  (reserved_usd >= 0 AND reserved_usd <> 'NaN'::numeric AND reserved_usd <> 'Infinity'::numeric);
