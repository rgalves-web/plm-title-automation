"""Rounds and their turn caps (issue 08).

A Round is a bounded period of execution on a Case that ends in a
Disposition (GLOSSARY). Renato approves each Round with a turn cap. A turn is
one terminal call whose process was launched: its subscription receipt
counts toward the cap whatever it contains, and a turn is never converted to
dollars. The API ledger is neither read nor written here.

Before each launch the terminal client takes a turn. Once the Round's turns
are used up, the Round closes with the reason, no further call starts for
that Case, the running task goes back to ready and the Case waits for Renato
to approve a new Round. The per-process time limit and the per-task turn
limit still apply.

Issue 10: a Round may name one ready task as its focus. A focused Round seeds
no Coordinator; only the focus task and the follow-ups descending from it
(by parent task) are dispatched, and the Round closes as
`round_focus_complete` once nothing in that scope can still run.

Plumbing only: nothing here reads, judges or compares title content.
"""
from __future__ import annotations

from typing import Any

MAX_TURN_CAP = 10000
CAP_REACHED = "round_turn_cap_reached"
NOT_APPROVED = "round_not_approved"
FOCUS_COMPLETE = "round_focus_complete"
RUNNABLE = ("planejada", "pronta", "em_execucao")


class RoundTurnCapReached(RuntimeError):
    """No turn is left in the Case's current Round (or there is no Round)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.code = reason


def validate_cap(value: Any) -> int:
    """A Round's turn cap: a whole number from 1 to MAX_TURN_CAP."""
    if isinstance(value, bool):
        raise ValueError("round_turn_cap_required")
    try:
        cap = int(value)
    except (TypeError, ValueError):
        raise ValueError("round_turn_cap_required") from None
    if str(value).strip() != str(cap) and value != cap:
        raise ValueError("round_turn_cap_required")
    if not 1 <= cap <= MAX_TURN_CAP:
        raise ValueError("round_turn_cap_required")
    return cap


def current(repo: Any, unit_id: int) -> dict[str, Any] | None:
    return repo.conn.execute(
        "SELECT * FROM operation_rounds WHERE unit_id=%s ORDER BY number DESC "
        "LIMIT 1", (unit_id,)).fetchone()


def turns_used(repo: Any, round_row: dict[str, Any]) -> int:
    return repo.conn.execute(
        "SELECT count(*) AS n FROM operation_terminal_calls WHERE round_id=%s "
        "AND launched_at IS NOT NULL", (round_row["id"],)).fetchone()["n"]


def validate_focus(repo: Any, unit_id: int, value: Any) -> int | None:
    """Issue 10: the optional focus of a Round — one ready task of this Case.
    A blocked task is retried first; the focus is never widened silently."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("round_focus_task_outside_case")
    try:
        task_id = int(value)
    except (TypeError, ValueError):
        raise ValueError("round_focus_task_outside_case") from None
    task = repo.tarefa(task_id)
    if not task or task["unit_id"] != unit_id:
        raise ValueError("round_focus_task_outside_case")
    if task["status"] != "pronta":
        raise ValueError("round_focus_task_must_be_ready")
    return task_id


def approve(repo: Any, unit_id: int, cap: int, actor: str, note: str,
            command_id: str, focus_task_id: int | None = None
            ) -> dict[str, Any]:
    """Open the next Round with its turn cap and optional focus task; an
    earlier open Round closes."""
    previous = current(repo, unit_id)
    if previous and previous["closed_at"] is None:
        _close(repo, unit_id, previous, "superseded_by_new_round", actor)
    return repo.conn.execute(
        "INSERT INTO operation_rounds(unit_id,number,turn_cap,approved_by,note,"
        "command_id,focus_task_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (unit_id, (previous["number"] if previous else 0) + 1,
         validate_cap(cap), actor, note, command_id, focus_task_id)).fetchone()


def focus_scope(repo: Any, unit_id: int) -> list[int] | None:
    """The tasks an open focused Round may run: the focus task and every
    follow-up descending from it (by parent task). None without a focus."""
    row = current(repo, unit_id)
    if row is None or row["closed_at"] is not None or not row["focus_task_id"]:
        return None
    return [r["id"] for r in repo.conn.execute(
        "WITH RECURSIVE scope(id) AS (SELECT %s::bigint UNION "
        "SELECT t.id FROM tasks t JOIN scope s ON t.parent_task_id = s.id) "
        "SELECT id FROM scope ORDER BY id", (row["focus_task_id"],))]


def close_focus_if_done(repo: Any, unit_id: int) -> bool:
    """Close an open focused Round once nothing in its focus can still run:
    no task of the scope is planned, ready or running, and no follow-up of
    it is waiting to become a task. True when it closed now."""
    scope = focus_scope(repo, unit_id)
    if scope is None:
        return False
    with repo.transacao():
        repo.operation_case(unit_id, lock=True)
        busy = repo.conn.execute(
            "SELECT 1 FROM tasks WHERE id = ANY(%s) AND status = ANY(%s) "
            "UNION ALL SELECT 1 FROM operation_followups WHERE unit_id=%s "
            "AND task_id IS NULL AND parent_task_id = ANY(%s) LIMIT 1",
            (scope, list(RUNNABLE), unit_id, scope)).fetchone()
        if busy:
            return False
        _close(repo, unit_id, current(repo, unit_id), FOCUS_COMPLETE,
               "process:worker")
        return True


def state(repo: Any, unit_id: int) -> dict[str, Any] | None:
    """What the dashboard shows: the current Round, turns used and left."""
    row = current(repo, unit_id)
    if row is None:
        return None
    used = turns_used(repo, row)
    focus = repo.tarefa(row["focus_task_id"]) if row["focus_task_id"] else None
    return {"id": row["id"], "number": row["number"],
            "turn_cap": row["turn_cap"], "turns_used": used,
            "turns_remaining": max(0, row["turn_cap"] - used),
            "open": row["closed_at"] is None, "close_reason": row["close_reason"],
            "approved_at": row["approved_at"], "approved_by": row["approved_by"],
            "closed_at": row["closed_at"],
            "focus_task_id": row["focus_task_id"],
            "focus_title": focus["title"] if focus else None}


def take_turn(repo: Any, unit_id: int) -> dict[str, Any]:
    """Before a terminal call starts: the open Round with a turn left, or
    RoundTurnCapReached (closing the Round if its turns are used up)."""
    with repo.transacao():
        repo.operation_case(unit_id, lock=True)
        row = current(repo, unit_id)
        if row is None:
            raise RoundTurnCapReached(NOT_APPROVED)
        if row["closed_at"] is not None:
            raise RoundTurnCapReached(row["close_reason"] or CAP_REACHED)
        if turns_used(repo, row) >= row["turn_cap"]:
            _close(repo, unit_id, row, CAP_REACHED, "process:worker")
            raise RoundTurnCapReached(CAP_REACHED)
        return row


def after_turn(repo: Any, unit_id: int, round_row: dict[str, Any]) -> None:
    """After a launched call: close the Round as soon as its last turn is
    used, so no further call starts and the Case stops being dispatched."""
    with repo.transacao():
        repo.operation_case(unit_id, lock=True)
        row = repo.conn.execute("SELECT * FROM operation_rounds WHERE id=%s",
                                (round_row["id"],)).fetchone()
        if row["closed_at"] is None and turns_used(repo, row) >= row["turn_cap"]:
            _close(repo, unit_id, row, CAP_REACHED, "process:worker")


def _close(repo: Any, unit_id: int, row: dict[str, Any], reason: str,
           actor: str) -> None:
    closed = repo.conn.execute(
        "UPDATE operation_rounds SET closed_at=now(), close_reason=%s "
        "WHERE id=%s AND closed_at IS NULL RETURNING id", (reason, row["id"])
    ).fetchone()
    if not closed:
        return
    used = turns_used(repo, row)
    repo.operation_event("round.closed", actor,
                         {"round": row["number"], "turn_cap": row["turn_cap"],
                          "turns_used": used, "reason": reason,
                          "focus_task_id": row.get("focus_task_id")},
                         unit_id=unit_id)
    if reason in (CAP_REACHED, FOCUS_COMPLETE):
        repo.operation_update(unit_id, execution_state="waiting")
