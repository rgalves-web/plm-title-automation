"""Additional shared API cap, reserved per request across all four workers."""
import math
from decimal import Decimal,ROUND_CEILING
from uuid import uuid4


class SharedSpendingCap(RuntimeError):
    pass


def installed(repo):
    return bool(repo.conn.execute("SELECT to_regclass('operation_spending_limits') IS NOT NULL AS ok").fetchone()['ok'])


def state(repo,unit_id=None,lock=False):
    if not installed(repo):return None
    limit=repo.conn.execute("SELECT * FROM operation_spending_limits WHERE status='active' AND (%s::bigint IS NULL OR %s=ANY(unit_ids)) ORDER BY activated_at DESC LIMIT 1"+(' FOR UPDATE' if lock else ''),(unit_id,unit_id)).fetchone()
    if not limit:return None
    totals=repo.conn.execute("SELECT coalesce(sum(cost_usd) FILTER (WHERE status='confirmed'),0) AS known,coalesce(sum(reserved_usd) FILTER (WHERE status IN ('inflight','unknown')),0) AS reserved,count(*) FILTER (WHERE status='unknown') AS unknown FROM operation_requests WHERE spend_limit_id=%s",(limit['id'],)).fetchone()
    return {**limit,'known_cost_usd':totals['known'],'reserved_usd':totals['reserved'],'unknown_requests':totals['unknown'],
            'available_usd':max(Decimal(0),limit['budget_usd']-totals['known']-totals['reserved'])}


def reserve(repo,unit_id,estimate):
    limit=state(repo,unit_id,lock=True)
    if not limit:return None,0
    if estimate is None or not math.isfinite(float(estimate)) or float(estimate)<=0:
        raise SharedSpendingCap('shared_cap_requires_call_estimate')
    amount=Decimal(str(estimate)).quantize(Decimal('.000001'),rounding=ROUND_CEILING)
    if amount>limit['available_usd']:
        raise SharedSpendingCap('shared_api_budget_exhausted_or_reserved')
    return limit['id'],amount


def approve(repo,unit_ids,budget,actor,note):
    from src.casefile.operations import require_human
    require_human(actor,note)
    if not installed(repo):raise ValueError('shared_cap_migration_required')
    amount=float(budget)
    ids=sorted(set(int(i) for i in unit_ids))
    if not ids or not math.isfinite(amount) or amount<=0 or amount>200:
        raise ValueError('explicit_shared_budget_required')
    registered={c['unit_id'] for c in repo.operation_cases()}
    if set(ids)-registered:raise ValueError('shared_budget_case_not_registered')
    if repo.conn.execute('SELECT 1 FROM operation_cases WHERE unit_id=ANY(%s) AND execution_state=%s LIMIT 1',(ids,'running')).fetchone():
        raise ValueError('pause_cases_before_shared_budget_change')
    if repo.conn.execute('SELECT 1 FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=ANY(%s) AND r.finished_at IS NULL LIMIT 1',(ids,)).fetchone():
        raise ValueError('wait_calls_before_shared_budget_change')
    repo.conn.execute('SELECT pg_advisory_xact_lock(781876,6)')
    repo.conn.execute("UPDATE operation_spending_limits SET status='superseded' WHERE kind='development' AND status='active'")
    return repo.conn.execute('INSERT INTO operation_spending_limits(id,kind,unit_ids,budget_usd,approved_by,approval_note) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *',
        ('additional-'+uuid4().hex,'development',ids,amount,actor,note)).fetchone()
