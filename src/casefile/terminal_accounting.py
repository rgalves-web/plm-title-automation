"""Subscription receipts are separate from the historical API money ledger.

Issue 02: before every terminal call, the exact context sent to the Function
is written as the task's input file. A call whose input file cannot be
written never starts; the call is recorded as interrupted with the reason
and the task blocks for review.
"""
import hashlib

from src.casefile.operations import require_running
from src.casefile.repo import _json
from src.infra import terminal
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
        ordinal = self.turnos + 1
        with self.repo.transacao():
            row = self.repo.conn.execute(
                'INSERT INTO operation_terminal_calls(run_id,ordinal,family) VALUES (%s,%s,%s) RETURNING id',
                (self.run['id'], ordinal, self.family)).fetchone()
        sent = self._write_input(row, ordinal, kwargs)
        with self.repo.transacao():
            self.repo.conn.execute("UPDATE task_runs SET usage_state='subscription_running' WHERE id=%s", (self.run['id'],))
        try:
            message = self.inner.messages.create(**kwargs)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, TerminalError) else 'terminal_requires_review'
            with self.repo.transacao():
                self.repo.conn.execute("UPDATE operation_terminal_calls SET status='interrupted',failure=%s,finished_at=now() WHERE id=%s", (reason, row['id']))
                self.repo.conn.execute("UPDATE task_runs SET usage_state='subscription_interrupted' WHERE id=%s", (self.run['id'],))
            raise TerminalError('terminal_interrupted_no_automatic_retry') from None
        receipt = getattr(message, 'terminal_receipt', None) or {}
        expected = hashlib.sha256(sent['stdin'].encode('utf-8')).hexdigest()
        mismatch = bool(receipt.get('input_sha256')) and receipt['input_sha256'] != expected
        with self.repo.transacao():
            active=self.repo.conn.execute('SELECT finished_at IS NULL AND lease_until>now() AS active FROM task_runs WHERE id=%s FOR UPDATE',(self.run['id'],)).fetchone()['active']
            failure = 'terminal_input_differs_from_input_file' if mismatch else ('' if active else 'terminal_run_lease_lost')
            self.repo.conn.execute("UPDATE operation_terminal_calls SET status=%s,receipt=%s,failure=%s,finished_at=now() WHERE id=%s", ('completed' if active and not mismatch else 'interrupted',_json(receipt),failure,row['id']))
            self.repo.conn.execute("UPDATE task_runs SET usage_state=%s WHERE id=%s", ('subscription' if active else 'subscription_interrupted',self.run['id']))
            self.repo.operation_event('terminal.response', 'process:worker',
                {'run_id': self.run['id'], 'terminal_call_id': row['id'], 'billing_mode': 'subscription'},
                unit_id=self.task['unit_id'], task_id=self.task['id'])
        if mismatch:
            raise TerminalError('terminal_input_differs_from_input_file')
        if not active:
            raise TerminalError('terminal_run_lease_lost')
        self.usage.add(message.usage)
        self.turnos += 1
        return message

    def _write_input(self, row, ordinal, kwargs):
        """The input file, before the process starts. On any failure the
        call is closed as interrupted with the reason and never started."""
        from src.casefile import function_files
        try:
            sent = terminal.build_input(self.family, model=kwargs['model'], system=kwargs['system'],
                                        messages=kwargs['messages'], tools=kwargs['tools'])
            with self.repo.transacao():
                written = function_files.write_input(self.repo, self.task, self.run, ordinal, sent)
                self.repo.conn.execute('UPDATE operation_terminal_calls SET input_sha256=%s,input_file_id=%s WHERE id=%s',
                                       (written['sha256'], written['id'], row['id']))
                self.repo.conn.execute('UPDATE task_runs SET input_sha256=%s WHERE id=%s',
                                       (written['sha256'], self.run['id']))
            return sent
        except Exception as exc:
            reason = 'terminal_input_file_not_written: ' + (getattr(exc, 'code', '') or type(exc).__name__)
            with self.repo.transacao():
                self.repo.conn.execute("UPDATE operation_terminal_calls SET status='interrupted',failure=%s,finished_at=now() WHERE id=%s", (reason, row['id']))
                self.repo.conn.execute('UPDATE task_runs SET usage_state=%s WHERE id=%s',
                                       ('subscription_interrupted' if self.turnos else 'not_called', self.run['id']))
            raise TerminalError(reason) from None
