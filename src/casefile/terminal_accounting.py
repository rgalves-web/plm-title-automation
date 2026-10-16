"""Subscription receipts are separate from the historical API money ledger."""
from src.casefile.operations import require_running
from src.casefile.repo import _json
from src.infra.terminal import TerminalError


class TerminalClient:
    manages_retries = True

    def __init__(self, inner, repo, task, run, usage, family):
        self.inner, self.repo, self.task, self.run = inner, repo, task, run
        self.usage, self.family = usage, family
        self.turnos = 0
        self.messages = self

    def create(self, **kwargs):
        require_running(self.repo, self.task['unit_id'])
        with self.repo.transacao():
            row = self.repo.conn.execute(
                'INSERT INTO operation_terminal_calls(run_id,ordinal,family) VALUES (%s,%s,%s) RETURNING id',
                (self.run['id'], self.turnos + 1, self.family)).fetchone()
            self.repo.conn.execute("UPDATE task_runs SET usage_state='subscription_running' WHERE id=%s", (self.run['id'],))
        try:
            message = self.inner.messages.create(**kwargs)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, TerminalError) else 'terminal_requires_review'
            with self.repo.transacao():
                self.repo.conn.execute("UPDATE operation_terminal_calls SET status='interrupted',failure=%s,finished_at=now() WHERE id=%s", (reason, row['id']))
                self.repo.conn.execute("UPDATE task_runs SET usage_state='subscription_interrupted' WHERE id=%s", (self.run['id'],))
            raise TerminalError('terminal_interrupted_no_automatic_retry') from None
        with self.repo.transacao():
            active=self.repo.conn.execute('SELECT finished_at IS NULL AND lease_until>now() AS active FROM task_runs WHERE id=%s FOR UPDATE',(self.run['id'],)).fetchone()['active']
            self.repo.conn.execute("UPDATE operation_terminal_calls SET status=%s,receipt=%s,failure=%s,finished_at=now() WHERE id=%s", ('completed' if active else 'interrupted',_json(message.terminal_receipt),'' if active else 'terminal_run_lease_lost',row['id']))
            self.repo.conn.execute("UPDATE task_runs SET usage_state=%s WHERE id=%s", ('subscription' if active else 'subscription_interrupted',self.run['id']))
            self.repo.operation_event('terminal.response', 'process:worker',
                {'run_id': self.run['id'], 'terminal_call_id': row['id'], 'billing_mode': 'subscription'},
                unit_id=self.task['unit_id'], task_id=self.task['id'])
        if not active:
            raise TerminalError('terminal_run_lease_lost')
        self.usage.add(message.usage)
        self.turnos += 1
        return message
