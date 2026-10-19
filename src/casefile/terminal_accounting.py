"""Subscription receipts are separate from the historical API money ledger.

Issue 02: before every terminal call, the exact context sent to the Function
is written as the task's input file. A call whose input file cannot be
written never starts; the call is recorded as interrupted with the reason
and the task blocks for review.

Issue 04: the process is launched from the input file read back from disk,
never from the in-memory call, so the Function receives only what its own
input file holds. Before launch, the quarantine of a blind extraction is
checked against that file; a violation stops the call the same way.

Issue 08: each launched call is one turn of the Case's current Round; a
call never starts once the Round's turn cap is reached (`rounds`).

Issue 14: a failed call keeps the CLI's failure text as a write-once Case
file beside its input file, indexed on the call row with its class (login,
limit, invalid output, crash), so the Coordinator can wait or stop.
"""
import json
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
        from src.casefile import rounds
        # Issue 08: no call starts without a turn left in the Case's Round.
        # Checked first: a Round closed by its cap also sets the Case waiting,
        # and the reason to report is the cap.
        current_round = rounds.take_turn(self.repo, self.task['unit_id'])
        require_running(self.repo, self.task['unit_id'])
        ordinal = self.turnos + 1
        with self.repo.transacao():
            row = self.repo.conn.execute(
                'INSERT INTO operation_terminal_calls(run_id,ordinal,family) VALUES (%s,%s,%s) RETURNING id',
                (self.run['id'], ordinal, self.family)).fetchone()
        sent = self._input_for_call(row, ordinal, kwargs)
        with self.repo.transacao():
            self.repo.conn.execute("UPDATE task_runs SET usage_state='subscription_running' WHERE id=%s", (self.run['id'],))
            self.repo.conn.execute('UPDATE operation_terminal_calls SET round_id=%s,launched_at=now() WHERE id=%s',
                                   (current_round['id'], row['id']))
        try:
            message = self._launch(sent, kwargs)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, TerminalError) else 'terminal_requires_review'
            text = exc.diagnostic if isinstance(exc, TerminalError) else \
                TerminalError('', f'{type(exc).__name__}: {exc}').diagnostic
            with self.repo.transacao():
                self.repo.conn.execute("UPDATE operation_terminal_calls SET status='interrupted',failure=%s,finished_at=now() WHERE id=%s", (reason, row['id']))
                self.repo.conn.execute("UPDATE task_runs SET usage_state='subscription_interrupted' WHERE id=%s", (self.run['id'],))
            kind = self._record_failure(row, ordinal, reason, text)
            rounds.after_turn(self.repo, self.task['unit_id'], current_round)
            raise TerminalError('terminal_interrupted_no_automatic_retry:' + kind) from None
        rounds.after_turn(self.repo, self.task['unit_id'], current_round)
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
        if failure:
            self._record_failure(row, ordinal, failure, '')
        if mismatch:
            raise TerminalError('terminal_input_differs_from_input_file')
        if not active:
            raise TerminalError('terminal_run_lease_lost')
        self.usage.add(message.usage)
        self.turnos += 1
        return message

    def _launch(self, sent, kwargs):
        """The process gets the input file's content and nothing else. A
        client that launches no process (a scripted one) gets the call
        rebuilt from that same content."""
        run_input = getattr(self.inner.messages, 'run_input', None)
        if run_input is not None:
            return run_input(sent)
        return self.inner.messages.create(**terminal.call_from_input(sent),
                                          max_tokens=kwargs.get('max_tokens'))

    def _input_for_call(self, row, ordinal, kwargs):
        """Write the input file, read it back and check its quarantine, all
        before the process starts. On any failure the call is closed as
        interrupted with the reason and never started."""
        from src.casefile import function_files, orquestracao
        try:
            sent = terminal.build_input(self.family, model=kwargs['model'], system=kwargs['system'],
                                        messages=kwargs['messages'], tools=kwargs['tools'])
            with self.repo.transacao():
                written = function_files.write_input(self.repo, self.task, self.run, ordinal, sent)
                self.repo.conn.execute('UPDATE operation_terminal_calls SET input_sha256=%s,input_file_id=%s WHERE id=%s',
                                       (written['sha256'], written['id'], row['id']))
                self.repo.conn.execute('UPDATE task_runs SET input_sha256=%s WHERE id=%s',
                                       (written['sha256'], self.run['id']))
        except Exception as exc:
            self._never_started(row, ordinal, 'terminal_input_file_not_written: ' + (getattr(exc, 'code', '') or type(exc).__name__))
        try:
            document = function_files.read_input(self.repo, written)
        except Exception as exc:
            self._never_started(row, ordinal, 'terminal_input_file_not_read: ' + (getattr(exc, 'code', '') or type(exc).__name__))
        try:
            orquestracao.afirmar_quarentena_do_arquivo(self.repo, self.task, document)
        except orquestracao.QuarentenaViolada as exc:
            self._never_started(row, ordinal, 'terminal_input_quarantine_violated: ' + str(exc)[:300])
        return document['sent']

    def _never_started(self, row, ordinal, reason):
        with self.repo.transacao():
            self.repo.conn.execute("UPDATE operation_terminal_calls SET status='interrupted',failure=%s,finished_at=now() WHERE id=%s", (reason, row['id']))
            self.repo.conn.execute('UPDATE task_runs SET usage_state=%s WHERE id=%s',
                                   ('subscription_interrupted' if self.turnos else 'not_called', self.run['id']))
        self._record_failure(row, ordinal, reason, '')
        raise TerminalError(reason) from None

    def _record_failure(self, row, ordinal, reason, text):
        """The failure text as a write-once Case file beside the call's input
        file, indexed on the call with its class. A file that cannot be
        written leaves the text on the row; it never hides the failure."""
        from src.casefile import case_file_store, cli_failures
        kind = cli_failures.classify(reason, text)
        relative = None
        try:
            record = case_file_store.write(
                self.task['unit_id'], stage=self.repo.estado_da_unit(self.task['unit_id']),
                function=self.task['role'], task=self.task['id'],
                name=f"failure_run{self.run['id']}_call{ordinal:02d}.json",
                data=json.dumps({'schema': 1, 'kind': 'function_call_failure',
                                 'unit_id': self.task['unit_id'], 'task_id': self.task['id'],
                                 'run_id': self.run['id'], 'call_ordinal': ordinal,
                                 'function': self.task['role'], 'family': self.family,
                                 'reason': reason, 'class': kind, 'text': text},
                                ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8'))
            relative = record.relative
        except Exception:
            pass
        with self.repo.transacao():
            self.repo.conn.execute(
                'UPDATE operation_terminal_calls SET failure_class=%s,failure_text=%s,'
                'failure_relative=%s WHERE id=%s', (kind, text or reason, relative, row['id']))
        return kind
