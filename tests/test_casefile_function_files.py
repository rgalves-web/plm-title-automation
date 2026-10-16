"""Function output files (issue 03) — plumbing on isolated PostgreSQL schemas.

Synthetic outputs only; no test asserts a title conclusion.
"""
from __future__ import annotations

import json

import pytest

from src.casefile import case_file_store, function_files, worker
from tests.helpers_casefile import ClientRoteirizado, Use
from tests.test_casefile_operational_flow import source
from tests.test_casefile_operations import (RESEARCH, approve, operation_case,  # noqa: F401
                                            task)

BAD_RESEARCH = {"fonte": "local"}          # misses required keys: rejected


def _run(repo, unit, steps):
    return worker.executar_uma(repo, unit["id"], "synthetic-worker", teto=50,
                               operation=True, client=ClientRoteirizado(steps))


def _outputs(repo, run_id):
    return repo.function_files(run_id=run_id, direction="output")


def test_each_delivery_writes_one_output_file_before_applying(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    item = task(repo, unit)
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": RESEARCH})]])
    assert result["erros"] == []
    [row] = _outputs(repo, result["run_id"])
    stage = repo.estado_da_unit(unit["id"]).lower()
    assert row["relative"] == (f"{stage}/pesquisador/{item['id']}/"
                               f"output_run{result['run_id']}_attempt01.json")
    record = case_file_store.read(unit["id"], row["relative"])
    assert record.sha256 == row["sha256"]
    body = json.loads(record.path.read_text("utf-8"))
    assert body["status"] == "accepted" and body["output"] == RESEARCH
    assert body["rejection_reason"] == []
    artifact = repo.operation_artifact(row["artifact_id"])
    assert artifact["kind"] == "function_output"
    assert artifact["sha256"] == row["sha256"]
    assert row["applied_at"] is not None


def test_rejected_output_is_kept_with_reason_and_never_applied(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    task(repo, unit)
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": BAD_RESEARCH})],
                               [Use("entregar_saida", {"saida": RESEARCH})]])
    rejected, accepted = _outputs(repo, result["run_id"])
    assert rejected["status"] == "rejected" and rejected["reason"]
    assert rejected["applied_at"] is None
    body = json.loads(case_file_store.read(unit["id"], rejected["relative"])
                      .path.read_text("utf-8"))
    assert body["status"] == "rejected" and body["rejection_reason"]
    assert accepted["status"] == "accepted" and accepted["applied_at"]
    assert rejected["relative"].endswith("attempt01.json")
    assert accepted["relative"].endswith("attempt02.json")


def test_only_rejected_outputs_mean_nothing_is_applied(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    task(repo, unit)
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": BAD_RESEARCH})]])
    assert result["erros"]
    [row] = _outputs(repo, result["run_id"])
    assert row["status"] == "rejected" and row["applied_at"] is None
    state = function_files.lifecycle(repo, result["run_id"])
    assert (state["response_received"], state["valid_output"],
            state["result_applied"]) == (True, False, False)
    assert not repo.conn.execute(
        "SELECT 1 FROM negative_searches WHERE output_sha256 IS NOT NULL"
    ).fetchone()


def test_rows_derived_from_an_output_cite_its_sha256(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    task(repo, unit)
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": RESEARCH})]])
    [row] = _outputs(repo, result["run_id"])
    searches = repo.conn.execute(
        "SELECT output_sha256 FROM negative_searches WHERE unit_id=%s",
        (unit["id"],)).fetchall()
    assert searches and {s["output_sha256"] for s in searches} == {row["sha256"]}
    observation = repo.conn.execute(
        "SELECT output_sha256 FROM operation_artifacts WHERE unit_id=%s AND "
        "kind='research_observation'", (unit["id"],)).fetchone()
    assert observation["output_sha256"] == row["sha256"]
    # the output file's own index row is NOT derived from itself
    assert repo.operation_artifact(row["artifact_id"])["output_sha256"] is None


def test_claims_cite_the_output_file(operation_case, tmp_path):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    artifact = source(repo, unit, tmp_path / "synthetic.pdf")
    task(repo, unit, "examinador", "claims", mode="obrigatoria")
    claim = {"tipo": "fact", "entidade": "Synthetic field",
             "valor": {"tipo_resultado": "fato_documental", "field": "sample"},
             "documento": "sha256:" + artifact["sha256"], "pagina": "1",
             "trecho": "Synthetic fixture only.", "confianca": "alta",
             "materialidade": "baixa"}
    result = _run(repo, unit, [[Use("entregar_saida",
                                    {"saida": {"claims": [claim]}})]])
    assert result["erros"] == []
    [row] = _outputs(repo, result["run_id"])
    claims = repo.claims_da_unit(unit["id"])
    assert claims and {c["output_sha256"] for c in claims} == {row["sha256"]}


def test_lifecycle_distinguishes_received_valid_applied(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    task(repo, unit)
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": RESEARCH})]])
    state = function_files.lifecycle(repo, result["run_id"])
    assert (state["response_received"], state["valid_output"],
            state["result_applied"]) == (True, True, True)
    from src.casefile import operations
    detail = operations.task_detail(repo, result["tarefa"]["id"])
    assert detail["lifecycle"][-1]["result_applied"] is True
    assert detail["function_files"][-1]["direction"] == "output"


def test_begin_apply_refuses_rejected_missing_or_changed_file(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    task(repo, unit)
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": BAD_RESEARCH})],
                               [Use("entregar_saida", {"saida": RESEARCH})]])
    rejected, accepted = _outputs(repo, result["run_id"])
    with pytest.raises(function_files.FunctionOutputNotApplicable):
        function_files.begin_apply(repo, rejected)
    with pytest.raises(function_files.FunctionOutputNotApplicable):
        function_files.begin_apply(repo, None)
    path = case_file_store.read(unit["id"], accepted["relative"]).path
    path.write_bytes(b"changed after receipt")
    with pytest.raises(case_file_store.CaseFileTampered):
        function_files.begin_apply(repo, accepted)
