"""Round turn cap (issue 08) — plumbing on isolated PostgreSQL schemas.

Synthetic outputs only; no test asserts a title conclusion.
"""
from __future__ import annotations

import pytest

from src.casefile import operations, rounds, worker
from tests.helpers_casefile import Use
from tests.test_casefile_function_files import BAD_RESEARCH, _terminal
from tests.test_casefile_operations import (RESEARCH, operation_case,  # noqa: F401
                                            request, task)
from tests.test_casefile_terminal import ScriptedTerminal


def _approve(repo, unit, scope, **extra):
    operations.command(repo, request(repo, unit, "start", budget_usd=50,
                                     scope=scope, **extra))
    coordinator = [t for t in repo.tarefas(unit["id"])
                   if t["role"] == "coordenador" and t["status"] == "pronta"]
    for item in coordinator:
        repo.transicionar_tarefa(item["id"], ("pronta",), "cancelada",
                                 "human:test", "Only run the tested role.")


def _ledger(repo):
    """The API money ledger, which turns must never touch."""
    return (repo.conn.execute("SELECT count(*) AS n FROM operation_requests")
            .fetchone()["n"],
            repo.conn.execute("SELECT count(*) AS n FROM cost_entries")
            .fetchone()["n"])


@pytest.mark.parametrize("cap", [None, 0, -1, "two", 2.5, True,
                                 rounds.MAX_TURN_CAP + 1])
def test_approving_a_round_requires_a_turn_cap(operation_case, cap):
    repo, unit, scope = operation_case
    extra = {} if cap is None else {"turn_cap": cap}
    with pytest.raises(ValueError, match="round_turn_cap_required"):
        _approve(repo, unit, scope, **extra)
    assert rounds.current(repo, unit["id"]) is None
    assert repo.operation_case(unit["id"])["execution_state"] != "running"


def test_approved_round_records_its_cap(operation_case):
    repo, unit, scope = operation_case
    _approve(repo, unit, scope, turn_cap=3)
    state = rounds.state(repo, unit["id"])
    assert (state["number"], state["turn_cap"], state["turns_used"],
            state["turns_remaining"], state["open"]) == (1, 3, 0, 3, True)
    assert repo.operation_case(unit["id"])["approval"]["turn_cap"] == 3


def test_reaching_the_cap_stops_further_calls_and_records_the_reason(
        operation_case):
    repo, unit, scope = operation_case
    _approve(repo, unit, scope, turn_cap=2)
    _terminal(repo, unit)
    item = task(repo, unit)
    ledger = _ledger(repo)
    client = ScriptedTerminal([[Use("entregar_saida", {"saida": BAD_RESEARCH})],
                               [Use("entregar_saida", {"saida": BAD_RESEARCH})],
                               [Use("entregar_saida", {"saida": RESEARCH})]])
    result = worker.executar_uma(repo, unit["id"], "terminal-fixture",
                                 teto=50, operation=True, client=client)
    assert result["parada"] == rounds.CAP_REACHED
    assert result["erros"] == [rounds.CAP_REACHED]
    calls = repo.conn.execute("SELECT * FROM operation_terminal_calls").fetchall()
    assert len(calls) == 2 and all(c["launched_at"] for c in calls)
    run = repo.run(result["run_id"])
    assert run["stop_reason"] == rounds.CAP_REACHED
    assert repo.tarefa(item["id"])["status"] == "pronta"      # resumes later
    assert repo.operation_case(unit["id"])["execution_state"] == "waiting"
    state = rounds.state(repo, unit["id"])
    assert (state["turns_used"], state["turns_remaining"], state["open"],
            state["close_reason"]) == (2, 0, False, rounds.CAP_REACHED)
    events = [e for e in repo.operation_events(unit_id=unit["id"], limit=1000)
              if e["kind"] == "round.closed"]
    assert [e["detail"]["reason"] for e in events] == [rounds.CAP_REACHED]
    assert _ledger(repo) == ledger                          # no dollars
    assert repo.custo_acumulado(unit["id"]) == 0


def test_a_spent_round_resumes_only_through_a_new_round(operation_case):
    repo, unit, scope = operation_case
    _approve(repo, unit, scope, turn_cap=1)
    _terminal(repo, unit)
    task(repo, unit)
    worker.executar_uma(repo, unit["id"], "terminal-fixture", teto=50,
                        operation=True,
                        client=ScriptedTerminal([
                            [Use("entregar_saida", {"saida": BAD_RESEARCH})],
                            [Use("entregar_saida", {"saida": RESEARCH})]]))
    with pytest.raises(ValueError, match="approve_new_round_with_turn_cap"):
        operations.command(repo, request(repo, unit, "resume"))
    _approve(repo, unit, scope, turn_cap=5)
    result = worker.executar_uma(
        repo, unit["id"], "terminal-fixture", teto=50, operation=True,
        client=ScriptedTerminal([[Use("entregar_saida", {"saida": RESEARCH})]]))
    assert result["erros"] == []
    state = rounds.state(repo, unit["id"])
    assert (state["number"], state["turns_used"], state["turns_remaining"],
            state["open"]) == (2, 1, 4, True)


def test_a_case_started_before_rounds_needs_a_round_for_terminal_calls(
        operation_case):
    repo, unit, scope = operation_case
    _approve(repo, unit, scope, turn_cap=4)
    repo.conn.execute("DELETE FROM operation_rounds WHERE unit_id=%s",
                      (unit["id"],))
    _terminal(repo, unit)
    item = task(repo, unit)
    result = worker.executar_uma(
        repo, unit["id"], "terminal-fixture", teto=50, operation=True,
        client=ScriptedTerminal([[Use("entregar_saida", {"saida": RESEARCH})]]))
    assert result["parada"] == rounds.NOT_APPROVED
    assert not repo.conn.execute("SELECT 1 FROM operation_terminal_calls").fetchone()
    assert repo.tarefa(item["id"])["status"] == "pronta"
    assert repo.operation_case(unit["id"])["execution_state"] == "waiting"


def test_dashboard_reports_turns_used_and_remaining(operation_case):
    repo, unit, scope = operation_case
    _approve(repo, unit, scope, turn_cap=3)
    _terminal(repo, unit)
    task(repo, unit)
    worker.executar_uma(repo, unit["id"], "terminal-fixture", teto=50,
                        operation=True,
                        client=ScriptedTerminal([[Use("entregar_saida",
                                                      {"saida": RESEARCH})]]))
    [case] = operations.snapshot(repo)["cases"]
    assert {k: case["round"][k] for k in ("number", "turn_cap", "turns_used",
                                          "turns_remaining", "open")} == \
        {"number": 1, "turn_cap": 3, "turns_used": 1, "turns_remaining": 2,
         "open": True}
    assert operations.detail(repo, unit["id"])["round"]["turns_remaining"] == 2
