"""Function output files (issue 03) and input files (issue 02), ADR 0001.

Every Function output delivered in a task run is written as a write-once
Case file BEFORE anything is applied: accepted when it met its contract,
rejected with the reason when it did not. Only an accepted output file is
ever applied, and every row created while applying it cites the file's
sha256 (`plm.output_sha256`, read by the column defaults of migration 0014).

The index lives in `function_files` (one row per file, with the Call
lifecycle per run: received, valid output, result applied) and in the
operation artifact index, so the dashboard can open the file.

Every terminal call's exact context is written as an input file before the
process starts (issue 02), and the process is launched from that file read
back from disk (`read_input`, issue 04).

Plumbing only: nothing here reads, judges or compares title content.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from src.casefile import case_file_store

SCHEMA = 1


class FunctionOutputNotApplicable(ValueError):
    """The output about to be applied has no accepted output file."""
    code = "function_output_not_applicable"


class FunctionInputChanged(ValueError):
    """The input file on disk is not the one indexed for the call."""
    code = "function_input_changed"


def _dumps(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True,
                      default=str).encode("utf-8")


def write_output(repo: Any, task: dict[str, Any], run_id: int, attempt: int,
                 output: Any, errors: list[str]) -> dict[str, Any]:
    """Write one delivered output as its output file and index it.

    Called for EVERY delivery, valid or not, before any result is applied.
    Returns the `function_files` row."""
    unit_id = task["unit_id"]
    status = "rejected" if errors else "accepted"
    document = {"schema": SCHEMA, "kind": "function_output",
                "unit_id": unit_id, "task_id": task["id"], "run_id": run_id,
                "function": task["role"], "output_schema": task["output_schema"],
                "attempt": attempt, "status": status,
                "rejection_reason": list(errors), "output": output}
    record = case_file_store.write(
        unit_id, stage=repo.estado_da_unit(unit_id), function=task["role"],
        task=task["id"], name=f"output_run{run_id}_attempt{attempt:02d}.json",
        data=_dumps(document))
    artifact = repo.operation_add_artifact(
        unit_id, "function_output", record.path, record.sha256, record.size,
        {"display_name": f"Saída da função · tarefa {task['id']} · run "
                         f"{run_id} · tentativa {attempt}",
         "relative": record.relative, "run_id": run_id, "attempt": attempt,
         "status": ("Saída aceita" if status == "accepted" else
                    "Saída recusada: " + "; ".join(errors)),
         "rejection_reason": list(errors)}, task["id"])
    return repo.function_file_add(
        unit_id, task["id"], run_id, "output", attempt, record.relative,
        record.sha256, record.size, status, errors, artifact["id"])


def write_input(repo: Any, task: dict[str, Any], run: dict[str, Any],
                ordinal: int, sent: dict[str, Any]) -> dict[str, Any]:
    """Write the exact context of one terminal call as its input file and
    index it (issue 02). `sent` is `terminal.build_input(...)`: stdin bytes,
    images, system prompt, protocol and output schema. Must succeed before
    the process starts; any failure propagates to the caller."""
    unit_id = task["unit_id"]
    # The run row is re-read: the pinned Publication is set on it after the
    # worker picked the task, so a cached dict could miss it.
    run = repo.run(run["id"]) or run
    document = {"schema": SCHEMA, "kind": "function_input",
                "unit_id": unit_id, "task_id": task["id"],
                "run_id": run["id"], "function": task["role"],
                "output_schema": task["output_schema"],
                "call_ordinal": ordinal,
                "publication": run.get("knowledge_release_id"),
                "sent": sent}
    record = case_file_store.write(
        unit_id, stage=repo.estado_da_unit(unit_id), function=task["role"],
        task=task["id"], name=f"input_run{run['id']}_call{ordinal:02d}.json",
        data=_dumps(document))
    artifact = repo.operation_add_artifact(
        unit_id, "function_input", record.path, record.sha256, record.size,
        {"display_name": f"Entrada da função · tarefa {task['id']} · run "
                         f"{run['id']} · chamada {ordinal}",
         "relative": record.relative, "run_id": run["id"],
         "call_ordinal": ordinal,
         "status": "Entrada registrada antes da chamada"}, task["id"])
    return repo.function_file_add(
        unit_id, task["id"], run["id"], "input", ordinal, record.relative,
        record.sha256, record.size, "recorded", [], artifact["id"])


def read_input(repo: Any, file_row: dict[str, Any]) -> dict[str, Any]:
    """The input file document, read back from disk (issue 04): the terminal
    process is launched from these bytes, never from the in-memory call.
    Refuses bytes that differ from the indexed sha256."""
    data = case_file_store.read_bytes(file_row["unit_id"], file_row["relative"])
    if file_row["direction"] != "input" or \
            hashlib.sha256(data).hexdigest() != file_row["sha256"]:
        raise FunctionInputChanged(
            "function_input_changed: the input file is not the one indexed "
            "for this call")
    return json.loads(data)


def current_output(repo: Any, unit_id: int) -> dict[str, Any] | None:
    """Inside an apply transaction: the accepted output file being applied
    (from `plm.output_sha256`), or None outside one."""
    sha = repo.conn.execute(
        "SELECT nullif(current_setting('plm.output_sha256', true), '') AS sha"
    ).fetchone()["sha"]
    if not sha:
        return None
    rows = [f for f in repo.function_files(unit_id=unit_id, sha256=sha,
                                           direction="output")
            if f["status"] == "accepted"]
    return rows[-1] if rows else None


def begin_apply(repo: Any, file_row: dict[str, Any] | None) -> dict[str, Any]:
    """Inside the apply transaction: refuse anything but an accepted output
    file whose bytes are intact, then make every row inserted from here on
    cite its sha256."""
    if not file_row or file_row["direction"] != "output" or \
            file_row["status"] != "accepted":
        raise FunctionOutputNotApplicable(
            "function_output_not_applicable: only an accepted output file "
            "is applied")
    record = case_file_store.read(file_row["unit_id"], file_row["relative"])
    if record.sha256 != file_row["sha256"]:
        raise FunctionOutputNotApplicable(
            "function_output_not_applicable: indexed sha256 differs from the "
            "output file")
    repo.conn.execute("SELECT set_config('plm.output_sha256', %s, true)",
                      (file_row["sha256"],))
    return file_row


def finish_apply(repo: Any, file_row: dict[str, Any]) -> None:
    """Still inside the apply transaction: record that the result was
    applied, so it commits (or rolls back) with the derived rows."""
    repo.function_file_applied(file_row["id"])
    repo.conn.execute("SELECT set_config('plm.output_sha256', '', true)")


def accepted_output(repo: Any, run_id: int) -> dict[str, Any] | None:
    """The latest accepted output file of a run, if any."""
    files = [f for f in repo.function_files(run_id=run_id, direction="output")
             if f["status"] == "accepted"]
    return files[-1] if files else None


def lifecycle(repo: Any, run_id: int) -> dict[str, Any]:
    """The Call lifecycle of one task run, from the index: response
    received, valid output, result applied — each distinguishable."""
    outputs = repo.function_files(run_id=run_id, direction="output")
    return {"run_id": run_id,
            "response_received": bool(outputs),
            "valid_output": any(f["status"] == "accepted" for f in outputs),
            "result_applied": any(f["applied_at"] is not None
                                  for f in outputs),
            "outputs": [{"id": f["id"], "relative": f["relative"],
                         "sha256": f["sha256"], "status": f["status"],
                         "reason": f["reason"],
                         "applied_at": f["applied_at"]} for f in outputs]}
