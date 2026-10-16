"""Rebuild a Case's index from its Case folder and compare it (issue 06).

`rebuild` reads only the Case folder, through `case_file_store`, and writes
the index into an empty schema of another connection: the tasks and runs
that Function files name, the Function files themselves, Claims, reviews and
supersessions. It never receives, opens or reads the live database.

`compare` then projects the live database into the same shape and lists
every difference with the file and the row involved: a value that differs,
a row with no file, a file with no row. A file that cannot be read intact is
reported as a problem of that file.

Only what Case files cover is compared. The rest is counted as "not file
backed" and left out: operational state (leases, budgets, titles of tasks
that never ran), rows from before issue 03, and when an accepted output was
applied (`applied_at`). Issue 07 makes files authoritative for new Cases.

Plumbing only: nothing here reads, judges or compares title content beyond
equality of what was recorded.
"""
from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from src.casefile import case_file_store

DDL = (
    "CREATE TABLE index_tasks (task_id bigint PRIMARY KEY, unit_id bigint NOT NULL,"
    " function text NOT NULL, output_schema text NOT NULL, file text NOT NULL)",
    "CREATE TABLE index_runs (run_id bigint PRIMARY KEY, task_id bigint NOT NULL,"
    " input_sha256 text, file text NOT NULL)",
    "CREATE TABLE index_function_files (relative text PRIMARY KEY,"
    " task_id bigint NOT NULL, run_id bigint NOT NULL, direction text NOT NULL,"
    " ordinal int NOT NULL, sha256 text NOT NULL, size_bytes bigint NOT NULL,"
    " status text NOT NULL, reason jsonb NOT NULL)",
    "CREATE TABLE index_claims (relative text PRIMARY KEY, sha256 text NOT NULL,"
    " claim_type text, entity text, value jsonb, source_sha256 text, page text,"
    " evidence text, confidence text, materiality text, limitations text,"
    " ddr_candidates jsonb, status text NOT NULL, superseded_by text)",
    "CREATE TABLE index_reviews (relative text PRIMARY KEY, sha256 text NOT NULL,"
    " claim_file text, question text, verdict text, verifier_model text,"
    " verifier_value jsonb, comparison jsonb, source_sha256 text, page text,"
    " prompt_sha256 text, request_id text, model_params jsonb,"
    " status text NOT NULL, invalidation_reason text NOT NULL)",
    "CREATE TABLE index_supersessions (superseded text PRIMARY KEY,"
    " superseded_sha256 text NOT NULL, by_file text NOT NULL,"
    " by_sha256 text NOT NULL, reason text NOT NULL)",
    "CREATE TABLE index_problems (file text NOT NULL, problem text NOT NULL)",
)
CLAIM_COLUMNS = ("claim_type", "entity", "value", "source_sha256", "page",
                 "evidence", "confidence", "materiality", "limitations",
                 "ddr_candidates")
REVIEW_COLUMNS = ("question", "verdict", "verifier_model", "verifier_value",
                  "comparison", "source_sha256", "page", "prompt_sha256",
                  "request_id", "model_params")
FILE_COLUMNS = ("task_id", "run_id", "direction", "ordinal", "sha256",
                "size_bytes", "status", "reason")


class RebuildTargetNotEmpty(ValueError):
    code = "rebuild_target_not_empty"


# --- rebuild: files only ---------------------------------------------------------

def _json_cols(row: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {k: (Jsonb(v) if k in names and v is not None else v)
            for k, v in row.items()}


def _insert(target: Any, table: str, row: dict[str, Any],
            json_columns: tuple[str, ...] = ()) -> None:
    row = _json_cols(row, json_columns)
    target.execute(
        f"INSERT INTO {table} ({','.join(row)}) "
        f"VALUES ({','.join(['%s'] * len(row))})", tuple(row.values()))


def rebuild(unit_id: int, target: Any) -> dict[str, int]:
    """Rebuild the index of Case `unit_id` from its Case folder into the
    current schema of `target`, which must be empty."""
    if target.execute(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_schema = current_schema()").fetchone()["n"]:
        raise RebuildTargetNotEmpty(
            "rebuild_target_not_empty: rebuild only into an empty schema")
    for statement in DDL:
        target.execute(statement)
    tasks: dict[int, dict[str, Any]] = {}
    runs: dict[int, dict[str, Any]] = {}
    inputs: dict[int, tuple[int, str]] = {}
    problems: list[tuple[str, str]] = []
    counts = {"function_files": 0, "claims": 0, "reviews": 0,
              "supersessions": 0}
    with target.transaction():
        for record in case_file_store.records(unit_id):
            try:
                document = json.loads(case_file_store.read_bytes(unit_id, record))
            except (case_file_store.CaseFileError, ValueError) as exc:
                problems.append((record.relative,
                                 getattr(exc, "code", "") or type(exc).__name__))
                continue
            if record.supersedes:
                _insert(target, "index_supersessions", {
                    "superseded": record.supersedes,
                    "superseded_sha256": record.supersedes_sha256,
                    "by_file": record.relative, "by_sha256": record.sha256,
                    "reason": record.reason})
                counts["supersessions"] += 1
            kind = document.get("kind")
            if kind in ("function_input", "function_output"):
                _function_file(target, record, document, tasks, runs, inputs,
                               problems)
                counts["function_files"] += 1
            elif kind == "claim":
                _claim(target, unit_id, record, document, problems)
                counts["claims"] += 1
            elif kind == "review":
                _review(target, unit_id, record, document, problems)
                counts["reviews"] += 1
        for task_id, task in tasks.items():
            _insert(target, "index_tasks", {"task_id": task_id, **task})
        for run_id, run in runs.items():
            _insert(target, "index_runs", {
                "run_id": run_id, **run,
                "input_sha256": inputs.get(run_id, (0, None))[1]})
        for file, problem in problems:
            _insert(target, "index_problems", {"file": file, "problem": problem})
    return {"tasks": len(tasks), "runs": len(runs), **counts,
            "problems": len(problems)}


def _same(seen: dict[int, dict[str, Any]], key: int, values: dict[str, Any],
          file: str, problems: list[tuple[str, str]], what: str) -> None:
    if key not in seen:
        seen[key] = {**values, "file": file}
    elif any(seen[key][k] != v for k, v in values.items()):
        problems.append((file, f"files_disagree_on_{what}_{key}"))


def _function_file(target, record, document, tasks, runs, inputs, problems):
    output = document["kind"] == "function_output"
    _same(tasks, document["task_id"],
          {"unit_id": document["unit_id"], "function": document["function"],
           "output_schema": document["output_schema"]},
          record.relative, problems, "task")
    _same(runs, document["run_id"], {"task_id": document["task_id"]},
          record.relative, problems, "run")
    ordinal = document["attempt"] if output else document["call_ordinal"]
    if not output and ordinal >= inputs.get(document["run_id"], (0, None))[0]:
        inputs[document["run_id"]] = (ordinal, record.sha256)
    _insert(target, "index_function_files", {
        "relative": record.relative, "task_id": document["task_id"],
        "run_id": document["run_id"],
        "direction": "output" if output else "input", "ordinal": ordinal,
        "sha256": record.sha256, "size_bytes": record.size,
        "status": document["status"] if output else "recorded",
        "reason": list(document.get("rejection_reason") or [])},
        ("reason",))


def _later(unit_id, record, problems):
    try:
        later = case_file_store.superseded_by(unit_id, record)
    except case_file_store.CaseFileError as exc:
        problems.append((record.relative, exc.code))
        return None
    return later[0] if later else None


def _claim(target, unit_id, record, document, problems):
    later = _later(unit_id, record, problems)
    _insert(target, "index_claims", {
        "relative": record.relative, "sha256": record.sha256,
        **{k: document["claim"].get(k) for k in CLAIM_COLUMNS},
        "status": "substituido" if later else "ativo",
        "superseded_by": later.relative if later else None},
        ("value", "ddr_candidates"))


def _review(target, unit_id, record, document, problems):
    later = _later(unit_id, record, problems)
    _insert(target, "index_reviews", {
        "relative": record.relative, "sha256": record.sha256,
        "claim_file": (document.get("claim_file") or {}).get("relative"),
        **{k: document["review"].get(k) for k in REVIEW_COLUMNS},
        "status": "invalidada" if later else "valida",
        "invalidation_reason": later.reason if later else ""},
        ("verifier_value", "comparison", "model_params"))


# --- compare: live database against the rebuilt index ----------------------------

def _diff(entity: str, live: dict[Any, dict[str, Any]],
          files: dict[Any, dict[str, Any]], columns: tuple[str, ...],
          out: list[dict[str, Any]]) -> None:
    for key in sorted(set(live) | set(files), key=str):
        row, built = live.get(key), files.get(key)
        where = {"entity": entity, "key": key,
                 "file": (built or {}).get("_file") or (row or {}).get("_file"),
                 "row": (row or {}).get("_row")}
        if row is None:
            out.append({**where, "difference": "file_without_row"})
        elif built is None:
            out.append({**where, "difference": "row_without_file"})
        else:
            for column in columns:
                if row[column] != built[column]:
                    out.append({**where, "difference": "value", "column": column,
                                "database": row[column], "files": built[column]})


def compare(live: Any, unit_id: int, target: Any) -> dict[str, Any]:
    """Every difference between the live database and the index rebuilt in
    `target`, each with the file and the row involved. Reads `live` only."""
    out: list[dict[str, Any]] = []
    built_files = {r["relative"]: {**r, "_file": r["relative"]} for r in
                   target.execute("SELECT * FROM index_function_files")}
    live_files = {r["relative"]: {**r, "_row": f"function_files:{r['id']}",
                                  "_file": r["relative"]}
                  for r in live.execute(
                      "SELECT * FROM function_files WHERE unit_id=%s", (unit_id,))}
    _diff("function_files", live_files, built_files, FILE_COLUMNS, out)

    built_tasks = {r["task_id"]: {**r, "_file": r["file"]}
                   for r in target.execute("SELECT * FROM index_tasks")}
    task_ids = sorted(set(built_tasks) | {r["task_id"] for r in live_files.values()})
    live_tasks = {r["id"]: {"unit_id": r["unit_id"], "function": r["role"],
                            "output_schema": r["output_schema"],
                            "_row": f"tasks:{r['id']}"}
                  for r in live.execute("SELECT * FROM tasks WHERE id = ANY(%s)",
                                        (task_ids,))}
    _diff("tasks", live_tasks, built_tasks,
          ("unit_id", "function", "output_schema"), out)

    built_runs = {r["run_id"]: {**r, "_file": r["file"]}
                  for r in target.execute("SELECT * FROM index_runs")}
    run_ids = sorted(set(built_runs) | {r["run_id"] for r in live_files.values()})
    live_runs = {r["id"]: {**r, "_row": f"task_runs:{r['id']}"}
                 for r in live.execute("SELECT * FROM task_runs WHERE id = ANY(%s)",
                                       (run_ids,))}
    _diff("runs", live_runs, built_runs, ("task_id", "input_sha256"), out)

    built_claims = {r["relative"]: {**r, "_file": r["relative"]}
                    for r in target.execute("SELECT * FROM index_claims")}
    live_claims = {}
    for r in live.execute(
            "SELECT c.*, s.case_file AS superseded_file FROM claims c "
            "LEFT JOIN claims s ON s.id = c.superseded_by WHERE c.unit_id=%s "
            "AND (c.case_file IS NOT NULL OR c.output_sha256 IS NOT NULL)",
            (unit_id,)):
        key = r["case_file"] or f"claims:{r['id']}"
        live_claims[key] = {**r, "superseded_by": r["superseded_file"],
                            "_row": f"claims:{r['id']}", "_file": r["case_file"]}
    _diff("claims", live_claims, built_claims,
          (*CLAIM_COLUMNS, "status", "superseded_by"), out)

    built_reviews = {r["relative"]: {**r, "_file": r["relative"]}
                     for r in target.execute("SELECT * FROM index_reviews")}
    live_reviews = {}
    for r in live.execute(
            "SELECT v.*, c.case_file AS claim_file FROM verifications v "
            "JOIN claims c ON c.id = v.claim_id WHERE c.unit_id=%s "
            "AND (v.case_file IS NOT NULL OR v.output_sha256 IS NOT NULL)",
            (unit_id,)):
        key = r["case_file"] or f"verifications:{r['id']}"
        live_reviews[key] = {**r, "_row": f"verifications:{r['id']}",
                             "_file": r["case_file"],
                             "invalidation_reason": r["invalidation_reason"]
                             if r["status"] == "invalidada" else ""}
    _diff("reviews", live_reviews, built_reviews,
          ("claim_file", *REVIEW_COLUMNS, "status", "invalidation_reason"), out)

    problems = [dict(r) for r in target.execute(
        "SELECT * FROM index_problems ORDER BY file")]
    return {"unit_id": unit_id, "differences": out, "file_problems": problems,
            "not_file_backed": _not_file_backed(live, unit_id),
            "ok": not out and not problems}


def same_database(first_dsn: str, second_dsn: str) -> bool:
    """Whether two DSNs name the same database (host, port and name)."""
    from psycopg.conninfo import conninfo_to_dict
    local = {"", "localhost", "127.0.0.1", "::1"}

    def key(dsn_text: str) -> tuple[str, str, str | None]:
        d = conninfo_to_dict(dsn_text)
        host = str(d.get("host") or "")
        return ("localhost" if host in local else host,
                str(d.get("port") or 5432), d.get("dbname"))
    return key(first_dsn) == key(second_dsn)


def run(unit_id: int, *, keep: bool = False) -> dict[str, Any]:
    """The `indice` command: rebuild into a new schema of the rebuild
    database (`CASEFILE_REBUILD_DSN`, else `CASEFILE_TEST_DSN`), never the
    live one, then compare with the live database through a read-only
    session. The schema is dropped afterwards unless `keep`."""
    import os
    from datetime import datetime, timezone

    from src.casefile.db import connect, dsn
    live_dsn = dsn()
    target_dsn = (os.environ.get("CASEFILE_REBUILD_DSN")
                  or os.environ.get("CASEFILE_TEST_DSN") or "")
    if not target_dsn:
        raise SystemExit("defina CASEFILE_REBUILD_DSN (ou CASEFILE_TEST_DSN) "
                         "para o banco onde o índice é reconstruído")
    if same_database(live_dsn, target_dsn):
        raise SystemExit("rebuild_target_is_the_live_database: reconstrua em "
                         "outro banco")
    schema = f"indice_u{int(unit_id)}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    target = connect(target_dsn)
    try:
        target.execute(f'CREATE SCHEMA "{schema}"')
        target.execute(f'SET search_path TO "{schema}"')
        rebuilt = rebuild(unit_id, target)
        with connect(live_dsn) as live:
            live.execute("SET default_transaction_read_only = on")
            report = compare(live, unit_id, target)
        return {**report, "rebuilt": rebuilt, "schema": schema if keep else None}
    finally:
        if not keep:
            target.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        target.close()


def _not_file_backed(live: Any, unit_id: int) -> dict[str, int]:
    """Live rows that Case files do not cover yet, by kind (left out)."""
    one = lambda sql: live.execute(sql, (unit_id,)).fetchone()["n"]  # noqa: E731
    return {
        "tasks": one("SELECT count(*) AS n FROM tasks t WHERE t.unit_id=%s AND NOT "
                     "EXISTS (SELECT 1 FROM function_files f WHERE f.task_id=t.id)"),
        "runs": one("SELECT count(*) AS n FROM task_runs r JOIN tasks t ON "
                    "t.id=r.task_id WHERE t.unit_id=%s AND NOT EXISTS (SELECT 1 "
                    "FROM function_files f WHERE f.run_id=r.id)"),
        "claims": one("SELECT count(*) AS n FROM claims WHERE unit_id=%s AND "
                      "case_file IS NULL AND output_sha256 IS NULL"),
        "reviews": one("SELECT count(*) AS n FROM verifications v JOIN claims c "
                       "ON c.id=v.claim_id WHERE c.unit_id=%s AND v.case_file "
                       "IS NULL AND v.output_sha256 IS NULL"),
    }
