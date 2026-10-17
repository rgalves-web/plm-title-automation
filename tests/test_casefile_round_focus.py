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


def test_retry_makes_a_blocked_task_ready_until_the_attempt_limit(operation_case):
    """The command behind the dashboard's retry button keeps the limit."""
    from src.casefile import orquestracao
    repo, unit, scope = operation_case
    item = task(repo, unit)
    _start(repo, unit, scope, turn_cap=10, focus_task_id=item["id"])
    for attempt in range(3):
        got = orquestracao.pegar(repo, unit["id"], "synthetic-worker", teto=50,
                                 max_active_per_unit=1, somente_ids=[item["id"]])
        repo.fechar_run(got[1]["id"], "synthetic-worker", output_json=None,
                        output_valid=False, validation_errors=["synthetic"],
                        stop_reason="synthetic_block", para="bloqueada")
        if attempt < 2:
            operations.command(repo, request(repo, unit, "retry_task",
                                             task_id=item["id"]))
            assert repo.tarefa(item["id"])["status"] == "pronta"
    assert len(repo.runs_da_tarefa(item["id"])) == 3
    with pytest.raises(ValueError, match="two_new_attempts_exhausted"):
        operations.command(repo, request(repo, unit, "retry_task",
                                         task_id=item["id"]))
    assert repo.tarefa(item["id"])["status"] == "bloqueada"
