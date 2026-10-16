"""Claims and reviews as Case files; corrections as superseding files (issue 05).

When an accepted output is applied, every Claim it yields and every review
(verification) it records gets its own write-once Case file in the applying
task's folder, named after that output file. A correction never edits a file:

- replacing a Claim writes the new Claim's file superseding the old Claim's
  file, with the reason;
- invalidating a review writes an invalidation file superseding the review
  file, with the reason and the invalidated file.

`case_file_store` puts a `.superseded_by` marker beside the superseded file,
so the history of a Claim can be followed by opening files alone
(`history`). Files hold no ids that a rolled-back apply could change, so
repeating the same apply rewrites the same bytes and is accepted.

Outside an apply of an output file (legacy runs, from before issue 03) no file
is written: the database stays authoritative there (ADR 0001). A Claim or
review from before this issue gets a file backfilled from its index row the
first time a correction needs to supersede it, marked as such.

Plumbing only: nothing here reads, judges or compares title content.
"""
from __future__ import annotations

import json
from typing import Any

from src.casefile import case_file_store
from src.casefile.function_files import _dumps

SCHEMA = 1
CLAIM_FIELDS = ("claim_type", "entity", "value", "source_sha256", "page",
                "evidence", "confidence", "materiality", "limitations",
                "ddr_candidates")
REVIEW_FIELDS = ("question", "verdict", "verifier_model", "verifier_value",
                 "comparison", "source_sha256", "page", "prompt_sha256",
                 "request_id", "model_params")


def _write(unit_id: int, *, stage: str, function: str, task: Any, name: str,
           document: dict[str, Any], supersedes: str | None = None,
           reason: str = "") -> case_file_store.CaseFileRecord:
    """Write once; the same bytes already written (a repeated apply) count
    as written."""
    data = _dumps(document)
    try:
        return case_file_store.write(unit_id, stage=stage, function=function,
                                     task=task, name=name, data=data,
                                     supersedes=supersedes, reason=reason)
    except case_file_store.CaseFileAlreadyWritten as exc:
        if not exc.same_content:
            raise
        return case_file_store.read(unit_id, exc.relative)


def _pointer(record: case_file_store.CaseFileRecord) -> dict[str, str]:
    return {"relative": record.relative, "sha256": record.sha256}


def _stem(output_file: dict[str, Any]) -> str:
    """`output_run5_attempt02.json` -> `run5_attempt02`."""
    name = output_file["relative"].rsplit("/", 1)[-1]
    return name.removeprefix("output_").removesuffix(".json")


def _index(repo: Any, unit_id: int, task: dict[str, Any],
           record: case_file_store.CaseFileRecord, label: str,
           status: str) -> None:
    repo.operation_add_artifact(
        unit_id, "case_record", record.path, record.sha256, record.size,
        {"display_name": label, "relative": record.relative,
         "status": status, "supersedes": record.supersedes,
         "reason": record.reason}, task["id"])


def _claim_document(claim: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"schema": SCHEMA, "kind": "claim", "unit_id": claim["unit_id"],
            "claim": {k: claim.get(k) for k in CLAIM_FIELDS}, **extra}


# --- Claims ------------------------------------------------------------------

def write_claim_files(repo: Any, task: dict[str, Any], claim_ids: list[int],
                      output_file: dict[str, Any] | None) -> list[str]:
    """One Case file per Claim of an applied output, unless it has one."""
    if output_file is None:
        return []
    unit_id = task["unit_id"]
    stage = repo.estado_da_unit(unit_id)
    written = []
    for index, claim_id in enumerate(claim_ids, start=1):
        claim = repo.claim(claim_id)
        if claim["case_file"]:
            continue
        record = _write(unit_id, stage=stage, function=task["role"],
                        task=task["id"],
                        name=f"claim_{_stem(output_file)}_{index:02d}.json",
                        document=_claim_document(
                            claim, task_id=task["id"], function=task["role"],
                            output_file={"relative": output_file["relative"],
                                         "sha256": output_file["sha256"]},
                            output_index=index))
        _set(repo, "claims", claim_id, record)
        _index(repo, unit_id, task, record, f"Afirmação {claim_id}",
               "Afirmação registrada")
        written.append(record.relative)
    return written


def claim_file(repo: Any, claim_id: int) -> case_file_store.CaseFileRecord:
    """The Case file of a Claim, backfilled from its index row when the
    Claim predates Claim files."""
    claim = repo.claim(claim_id)
    if claim["case_file"]:
        return case_file_store.read(claim["unit_id"], claim["case_file"])
    producer = repo.conn.execute(
        "SELECT t.id, t.role FROM task_claims tc JOIN tasks t ON t.id=tc.task_id "
        "WHERE tc.claim_id=%s ORDER BY t.id LIMIT 1", (claim_id,)).fetchone()
    record = _write(claim["unit_id"], stage=repo.estado_da_unit(claim["unit_id"]),
                    function=producer["role"] if producer else "examinador",
                    task=producer["id"] if producer else "sem-tarefa",
                    name=f"claim_index_{claim_id}.json",
                    document=_claim_document(claim, origin="index_backfill",
                                             claim_id=claim_id))
    _set(repo, "claims", claim_id, record)
    return record


def replace_claim(repo: Any, task: dict[str, Any], old_claim_id: int,
                  new_claim_id: int, reason: str,
                  output_file: dict[str, Any] | None) -> str | None:
    """The new Claim's file supersedes the old Claim's file, with the reason;
    then the index marks the old Claim as replaced."""
    relative = None
    if output_file is not None:
        old = claim_file(repo, old_claim_id)
        new = repo.claim(new_claim_id)
        record = _write(task["unit_id"], stage=repo.estado_da_unit(task["unit_id"]),
                        function=task["role"], task=task["id"],
                        name=f"claim_{_stem(output_file)}_01.json",
                        document=_claim_document(
                            new, task_id=task["id"], function=task["role"],
                            output_file={"relative": output_file["relative"],
                                         "sha256": output_file["sha256"]},
                            output_index=1, supersedes=_pointer(old),
                            reason=reason),
                        supersedes=old.relative, reason=reason)
        _set(repo, "claims", new_claim_id, record)
        _index(repo, task["unit_id"], task, record, f"Afirmação {new_claim_id}",
               f"Substitui a afirmação {old_claim_id}: {reason}")
        relative = record.relative
    repo.atualizar_claim_status(task["unit_id"], old_claim_id, "substituido",
                                new_claim_id)
    return relative


# --- reviews -----------------------------------------------------------------

def _review_document(repo: Any, verification: dict[str, Any],
                     **extra: Any) -> dict[str, Any]:
    claim = claim_file(repo, verification["claim_id"])
    return {"schema": SCHEMA, "kind": "review",
            "claim_id": verification["claim_id"], "claim_file": _pointer(claim),
            "review": {k: verification.get(k) for k in REVIEW_FIELDS}, **extra}


def _verification(repo: Any, verification_id: int) -> dict[str, Any]:
    return repo.conn.execute("SELECT * FROM verifications WHERE id=%s",
                             (verification_id,)).fetchone()


def write_review_file(repo: Any, task: dict[str, Any], verification_id: int,
                      output_file: dict[str, Any] | None) -> str | None:
    """The Case file of a review recorded from an applied output."""
    if output_file is None:
        return None
    verification = _verification(repo, verification_id)
    record = _write(task["unit_id"], stage=repo.estado_da_unit(task["unit_id"]),
                    function=task["role"], task=task["id"],
                    name=f"review_{_stem(output_file)}.json",
                    document=_review_document(
                        repo, verification, task_id=task["id"],
                        function=task["role"],
                        output_file={"relative": output_file["relative"],
                                     "sha256": output_file["sha256"]}))
    _set(repo, "verifications", verification_id, record)
    _index(repo, task["unit_id"], task, record,
           f"Revisão da afirmação {verification['claim_id']}", "Revisão registrada")
    return record.relative


def review_file(repo: Any, verification_id: int
                ) -> case_file_store.CaseFileRecord:
    """The Case file of a review, backfilled from its index row when the
    review predates review files."""
    verification = _verification(repo, verification_id)
    claim = repo.claim(verification["claim_id"])
    if verification["case_file"]:
        return case_file_store.read(claim["unit_id"], verification["case_file"])
    record = _write(claim["unit_id"], stage=repo.estado_da_unit(claim["unit_id"]),
                    function="verificador", task="sem-tarefa",
                    name=f"review_index_{verification_id}.json",
                    document=_review_document(repo, verification,
                                              origin="index_backfill",
                                              verification_id=verification_id))
    _set(repo, "verifications", verification_id, record)
    return record


def invalidate_review(repo: Any, task: dict[str, Any], verification_id: int,
                      reason: str, output_file: dict[str, Any] | None
                      ) -> str | None:
    """An invalidation file supersedes the review file, naming it and the
    reason; then the index marks the review invalid."""
    relative = None
    if output_file is not None:
        review = review_file(repo, verification_id)
        record = _write(task["unit_id"], stage=repo.estado_da_unit(task["unit_id"]),
                        function=task["role"], task=task["id"],
                        name=f"invalidation_{review.name}",
                        document={"schema": SCHEMA, "kind": "review_invalidation",
                                  "unit_id": task["unit_id"],
                                  "invalidated_file": _pointer(review),
                                  "reason": reason, "task_id": task["id"],
                                  "function": task["role"]},
                        supersedes=review.relative, reason=reason)
        _index(repo, task["unit_id"], task, record, "Revisão invalidada",
               f"Invalida {review.relative}: {reason}")
        relative = record.relative
    repo.invalidar_verificacao(verification_id, reason)
    return relative


def _set(repo: Any, table: str, row_id: int,
         record: case_file_store.CaseFileRecord) -> None:
    repo.conn.execute(f"UPDATE {table} SET case_file=%s WHERE id=%s",
                      (record.relative, row_id))


# --- history from files alone --------------------------------------------------

def history(unit_id: int, relative: str) -> dict[str, Any]:
    """The history of the Claim whose file is `relative`, read from the Case
    folder only (no database): every version from the first to the current,
    each with the reason it replaced the previous one, and every review of
    any version with its invalidation, if any."""
    versions = list(reversed(case_file_store.chain(
        unit_id, case_file_store.latest(unit_id, relative))))
    chain = {v.relative for v in versions}
    reviews = []
    for record in case_file_store.records(unit_id):
        if not record.name.startswith("review_"):
            continue
        document = json.loads(case_file_store.read_bytes(unit_id, record))
        if document.get("claim_file", {}).get("relative") not in chain:
            continue
        later = case_file_store.superseded_by(unit_id, record)
        reviews.append({"relative": record.relative,
                        "claim_file": document["claim_file"]["relative"],
                        "invalidated_by": later[0].relative if later else None,
                        "reason": later[0].reason if later else None})
    return {"versions": [{"relative": v.relative, "sha256": v.sha256,
                          "supersedes": v.supersedes, "reason": v.reason}
                         for v in versions],
            "current": versions[-1].relative, "reviews": reviews}
