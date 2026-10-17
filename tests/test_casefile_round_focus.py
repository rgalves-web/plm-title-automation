"""Round focus (issue 10) — plumbing on isolated PostgreSQL schemas.

Synthetic Claims and outputs only; no test asserts a title conclusion.
"""
from __future__ import annotations

import pytest

from src.casefile import operations, rounds, worker
from tests.helpers_casefile import ClientRoteirizado, Use
from tests.test_casefile_case_records import _claim
from tests.test_casefile_function_files import BAD_RESEARCH, BLIND_OUTPUT, _terminal
from tests.test_casefile_operational_flow import source
from tests.test_casefile_operations import (RESEARCH, operation_case,  # noqa: F401
                                            request, task)
from tests.test_casefile_terminal import ScriptedTerminal


def _start(repo, unit, scope, **extra):
    operations.command(repo, request(repo, unit, "start", budget_usd=50,
                                     scope=scope, **extra))


def _run(repo, unit, steps, client=None):
    return worker.executar_uma(repo, unit["id"], "synthetic-worker", teto=50,
                               operation=True,
                               client=client or ClientRoteirizado(steps))


def _coordinators(repo, unit):
    return [t for t in repo.tarefas(unit["id"]) if t["role"] == "coordenador"]


def test_a_focused_round_creates_no_coordinator(operation_case):
    repo, unit, scope = operation_case
    item = task(repo, unit)
    _start(repo, unit, scope, turn_cap=10, focus_task_id=item["id"])
    assert _coordinators(repo, unit) == []
    state = rounds.state(repo, unit["id"])
    assert (state["focus_task_id"], state["focus_title"], state["open"]) == \
        (item["id"], item["title"], True)
    assert repo.operation_case(unit["id"])["approval"]["focus_task_id"] == item["id"]
    assert rounds.focus_scope(repo, unit["id"]) == [item["id"]]


def test_without_focus_the_coordinator_is_still_created(operation_case):
    repo, unit, scope = operation_case
    _start(repo, unit, scope, turn_cap=10)
    assert len(_coordinators(repo, unit)) == 1
    assert rounds.state(repo, unit["id"])["focus_task_id"] is None


@pytest.mark.parametrize("case", ["missing", "not_an_id", "blocked"])
def test_the_focus_must_be_a_ready_task_of_the_case(operation_case, case):
    repo, unit, scope = operation_case
    item = task(repo, unit)
    if case == "missing":
        focus, error = 999999, "round_focus_task_outside_case"
    elif case == "not_an_id":
        focus, error = "not-a-task", "round_focus_task_outside_case"
    else:
        repo.transicionar_tarefa(item["id"], ("pronta",), "bloqueada",
                                 "human:test", "Synthetic block.")
        focus, error = item["id"], "round_focus_task_must_be_ready"
    with pytest.raises(ValueError, match=error):
        _start(repo, unit, scope, turn_cap=10, focus_task_id=focus)
    assert rounds.current(repo, unit["id"]) is None
    assert _coordinators(repo, unit) == []


def test_only_the_focus_and_its_follow_ups_run(operation_case, tmp_path):
    repo, unit, scope = operation_case
    artifact = source(repo, unit, tmp_path / "synthetic.pdf")
    other = task(repo, unit)                       # ready, picked first otherwise
    focus = task(repo, unit, "examinador", "claims", mode="obrigatoria")
    _start(repo, unit, scope, turn_cap=50, focus_task_id=focus["id"])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}

    produced = _run(repo, unit, [[Use("entregar_saida", {"saida": {
        "claims": [_claim(artifact, "focus reading")]}})]])
    assert produced["tarefa"]["id"] == focus["id"]
    [cid] = repo.claims_da_tarefa(focus["id"])
    blind = repo.tarefa_por_ref(unit["id"], f"review-claim-{cid}")
    assert blind["parent_task_id"] == focus["id"]

    reviewed = _run(repo, unit, [[Use("ler_pagina_confirmada", page)],
                                 [Use("entregar_saida", {"saida": BLIND_OUTPUT})]])
    assert reviewed["tarefa"]["id"] == blind["id"]
    compare = repo.tarefa_por_ref(unit["id"], f"compare-claim-{cid}")
    assert compare["parent_task_id"] == blind["id"]

    compared = _run(repo, unit, [[Use("read_page", page)], [Use("entregar_saida", {"saida": {
        "claim_id": cid, "verdict": "concordancia",
        "source_sha256": artifact["sha256"], "page": "1",
        "quote": "Synthetic fixture only.", "reason": "Synthetic plumbing only.",
        "material_divergence": False}})]])
    assert compared["tarefa"]["id"] == compare["id"]
    assert set(rounds.focus_scope(repo, unit["id"])) == \
        {focus["id"], blind["id"], compare["id"]}

    # nothing left in the focus: the Round closes and the other task waits
    assert _run(repo, unit, []) is None
    state = rounds.state(repo, unit["id"])
    assert (state["open"], state["close_reason"]) == (False, rounds.FOCUS_COMPLETE)
    assert repo.operation_case(unit["id"])["execution_state"] == "waiting"
    assert repo.tarefa(other["id"])["status"] == "pronta"
    assert repo.runs_da_tarefa(other["id"]) == []
    assert _coordinators(repo, unit) == []


def test_the_turn_cap_applies_inside_the_focus(operation_case):
    repo, unit, scope = operation_case
    task(repo, unit)
    focus = task(repo, unit)
    _start(repo, unit, scope, turn_cap=1, focus_task_id=focus["id"])
    _terminal(repo, unit)
    result = _run(repo, unit, None, client=ScriptedTerminal([
        [Use("entregar_saida", {"saida": BAD_RESEARCH})],
        [Use("entregar_saida", {"saida": RESEARCH})]]))
    assert result["tarefa"]["id"] == focus["id"]
    assert result["parada"] == rounds.CAP_REACHED
    state = rounds.state(repo, unit["id"])
    assert (state["turns_used"], state["open"], state["close_reason"]) == \
        (1, False, rounds.CAP_REACHED)


def test_a_closed_focused_round_dispatches_nothing_until_a_new_round(
        operation_case):
    repo, unit, scope = operation_case
    other = task(repo, unit)
    focus = task(repo, unit)
    _start(repo, unit, scope, turn_cap=10, focus_task_id=focus["id"])
    assert _run(repo, unit, [[Use("entregar_saida",
                                  {"saida": RESEARCH})]])["erros"] == []
    assert _run(repo, unit, []) is None                  # the focus is done
    assert rounds.state(repo, unit["id"])["close_reason"] == rounds.FOCUS_COMPLETE
    # the race of 16/10: a worker that read the Case as running before the
    # Round closed must still pick nothing
    repo.operation_update(unit["id"], execution_state="running")
    assert _run(repo, unit, []) is None
    assert repo.runs_da_tarefa(other["id"]) == []
    assert repo.tarefa(other["id"])["status"] == "pronta"
    # a new Round is what lets the Case dispatch again
    _start(repo, unit, scope, turn_cap=10)
    picked = _run(repo, unit, [[Use("entregar_saida", {"saida": RESEARCH})]])
    assert picked["tarefa"]["id"] == other["id"]


def test_runs_that_launched_no_call_do_not_use_up_attempts(operation_case):
    """The command behind the dashboard's retry button counts only runs that
    launched a call toward its limit of three."""
    from src.casefile import orquestracao
    repo, unit, scope = operation_case
    item = task(repo, unit)
    _start(repo, unit, scope, turn_cap=10, focus_task_id=item["id"])

    def run_once(launched):
        got = orquestracao.pegar(repo, unit["id"], "synthetic-worker", teto=50,
                                 max_active_per_unit=1, rodada=True)
        if launched:
            repo.conn.execute(
                "INSERT INTO operation_terminal_calls(run_id,ordinal,family,"
                "status,launched_at) VALUES (%s,1,'A','completed',now())",
                (got[1]["id"],))
        repo.fechar_run(got[1]["id"], "synthetic-worker", output_json=None,
                        output_valid=None, validation_errors=["synthetic"],
                        stop_reason="synthetic_block", para="bloqueada")

    def retry():
        operations.command(repo, request(repo, unit, "retry_task",
                                         task_id=item["id"]))

    for _ in range(3):                    # stopped before any call was made
        run_once(launched=False)
        retry()
    assert len(repo.runs_da_tarefa(item["id"])) == 3
    assert repo.task_attempts(item["id"]) == 0
    for attempt in (1, 2, 3):
        run_once(launched=True)
        assert repo.task_attempts(item["id"]) == attempt
        if attempt < 3:
            retry()
            assert repo.tarefa(item["id"])["status"] == "pronta"
    with pytest.raises(ValueError, match="two_new_attempts_exhausted"):
        retry()
    assert repo.tarefa(item["id"])["status"] == "bloqueada"
    assert operations.task_detail(repo, item["id"])["attempts"] == 3


def test_migration_0019_restores_attempts_of_runs_stopped_before_a_call(
        operation_case):
    """The data fix applied to the real database (task 65, run 100)."""
    from pathlib import Path
    from src.casefile import orquestracao
    from src.casefile.db import _statements
    repo, unit, scope = operation_case
    item = task(repo, unit)
    _start(repo, unit, scope, turn_cap=10, focus_task_id=item["id"])
    old = orquestracao.pegar(repo, unit["id"], "synthetic-worker", teto=50,
                             max_active_per_unit=1, rodada=True)[1]
    repo.fechar_run(old["id"], "synthetic-worker", output_json=None,
                    output_valid=None, validation_errors=[], stop_reason="concluida",
                    para="pronta")
    stopped = orquestracao.pegar(repo, unit["id"], "synthetic-worker", teto=50,
                                 max_active_per_unit=1, rodada=True)[1]
    repo.fechar_run(stopped["id"], "synthetic-worker", output_json=None,
                    output_valid=False, validation_errors=[rounds.FOCUS_COMPLETE],
                    stop_reason=rounds.FOCUS_COMPLETE, para="pronta")
    # calls recorded before launch tracking existed: one ran, one never started
    repo.conn.execute("INSERT INTO operation_terminal_calls(run_id,ordinal,"
                      "family,status) VALUES (%s,1,'A','completed')", (old["id"],))
    repo.conn.execute("INSERT INTO operation_terminal_calls(run_id,ordinal,family,"
                      "status,failure) VALUES (%s,2,'A','interrupted',"
                      "'terminal_input_file_not_written: synthetic')", (old["id"],))
    assert repo.task_attempts(item["id"]) == 0           # before the fix
    sql = (Path(__file__).resolve().parents[1] / "src" / "casefile" / "migrations"
           / "0019_attempts_count_launched_calls.sql").read_text("utf-8")
    for statement in _statements(sql):
        repo.conn.execute(statement)
    launched = [c["launched_at"] is not None for c in repo.conn.execute(
        "SELECT * FROM operation_terminal_calls ORDER BY ordinal")]
    assert launched == [True, False]       # the call that never started stays
    assert repo.task_attempts(item["id"]) == 1           # the old run counts
    assert repo.run(stopped["id"])["output_valid"] is None


def test_a_round_stop_without_delivery_leaves_validity_unset(operation_case):
    repo, unit, scope = operation_case
    item = task(repo, unit)
    _start(repo, unit, scope, turn_cap=10, focus_task_id=item["id"])
    repo.conn.execute("DELETE FROM operation_rounds WHERE unit_id=%s", (unit["id"],))
    _terminal(repo, unit)
    result = _run(repo, unit, None, client=ScriptedTerminal([
        [Use("entregar_saida", {"saida": RESEARCH})]]))
    assert result["parada"] == rounds.NOT_APPROVED
    run = repo.run(result["run_id"])
    assert run["output_valid"] is None and repo.task_attempts(item["id"]) == 0
