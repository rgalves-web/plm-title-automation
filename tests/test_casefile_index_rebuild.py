"""Rebuild the index from files (issue 06) — plumbing on isolated schemas.

Synthetic Claims and reviews only; no test asserts a title conclusion.
"""
from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

from src.casefile import case_file_store, index_rebuild, worker
from tests.helpers_casefile import Use, conectar_pg_ou_skip
from tests.test_casefile_case_records import REASON, _claim
from tests.test_casefile_function_files import (BLIND_OUTPUT, _CheckedTerminal,
                                                _terminal)
from tests.test_casefile_operational_flow import source
from tests.test_casefile_operations import approve, operation_case, task  # noqa: F401


@pytest.fixture
def target():
    """An empty schema of another connection: the rebuild's only output."""
    conn, schema = conectar_pg_ou_skip()
    try:
        yield conn
    finally:
        conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        conn.close()


def _terminal_run(repo, unit, steps):
    result = worker.executar_uma(repo, unit["id"], "terminal-fixture", teto=50,
                                 operation=True,
                                 client=_CheckedTerminal(repo, steps))
    assert result["erros"] == [], result
    return result


def _case_after_tickets_02_to_05(repo, unit, scope, tmp_path):
    """Through the terminal path: an Examiner with one rejected delivery then
    an accepted one, the blind extraction, a diverging comparison and the
    Arbiter's correction."""
    approve(repo, unit, scope)
    _terminal(repo, unit)
    artifact = source(repo, unit, tmp_path / "synthetic.pdf")
    task(repo, unit, "examinador", "claims", mode="obrigatoria")
    _terminal_run(repo, unit, [
        [Use("entregar_saida", {"saida": {"claims": [{"tipo": "fact"}]}})],
        [Use("entregar_saida", {"saida": {"claims": [
            _claim(artifact, "first reading")]}})]])
    [old] = repo.claims_da_unit(unit["id"])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    _terminal_run(repo, unit, [[Use("ler_pagina_confirmada", page)],
                               [Use("entregar_saida", {"saida": BLIND_OUTPUT})]])
    _terminal_run(repo, unit, [[Use("read_page", page)], [Use("entregar_saida", {"saida": {
        "claim_id": old["id"], "verdict": "divergencia",
        "source_sha256": artifact["sha256"], "page": "1",
        "quote": "Synthetic fixture only.", "reason": "Synthetic plumbing only.",
        "material_divergence": False}})]])
    compared = repo.verificacoes_do_claim(old["id"])[-1]
    _terminal_run(repo, unit, [[Use("ler_pagina", page)], [Use("entregar_saida", {"saida": {
        "claim_id": old["id"], "verificacao_id": compared["id"],
        "desfecho": "corrigido", "material_conclusao_titulo": False,
        "justificativa": REASON, "documento": "sha256:" + artifact["sha256"],
        "pagina": "1", "trecho": "Synthetic fixture only.",
        "novo_claim": _claim(artifact, "second reading")}})]])
    return repo.claim(old["id"])


def test_case_after_tickets_02_to_05_rebuilds_with_zero_differences(
        operation_case, tmp_path, target, monkeypatch):
    import psycopg
    repo, unit, scope = operation_case
    old = _case_after_tickets_02_to_05(repo, unit, scope, tmp_path)

    def no_database(*args, **kwargs):
        raise AssertionError("the rebuild must not open any database")

    with monkeypatch.context() as m:
        m.setattr(psycopg, "connect", no_database)
        m.setattr("src.casefile.db.connect", no_database)
        rebuilt = index_rebuild.rebuild(unit["id"], target)
    assert rebuilt == {"tasks": 4, "runs": 4, "function_files": 13,
                       "claims": 2, "reviews": 2, "supersessions": 2,
                       "problems": 0}
    report = index_rebuild.compare(repo.conn, unit["id"], target)
    assert report["differences"] == [] and report["file_problems"] == []
    assert report["ok"] is True
    replaced = target.execute("SELECT * FROM index_claims WHERE relative=%s",
                              (old["case_file"],)).fetchone()
    assert replaced["status"] == "substituido"
    assert replaced["superseded_by"] == repo.claim(old["superseded_by"])["case_file"]
    reasons = {r["reason"] for r in target.execute(
        "SELECT reason FROM index_supersessions")}
    assert reasons == {REASON, "blind_extraction_awaiting_ai_comparison"}


def test_comparison_lists_each_difference_with_the_file_and_the_row(
        operation_case, tmp_path, target):
    repo, unit, scope = operation_case
    old = _case_after_tickets_02_to_05(repo, unit, scope, tmp_path)
    # drift in the database that no file records
    repo.conn.execute("UPDATE claims SET value=%s WHERE id=%s",
                      (Jsonb({"field": "edited in the database"}), old["id"]))
    blind = repo.verificacoes_do_claim(old["id"])[0]
    repo.conn.execute("UPDATE verifications SET status='valida', "
                      "invalidation_reason='' WHERE id=%s", (blind["id"],))
    outputs = repo.function_files(direction="output", unit_id=unit["id"])
    lost_row, damaged = outputs[0], outputs[-1]
    repo.conn.execute("DELETE FROM function_files WHERE id=%s", (lost_row["id"],))
    case_file_store.read(unit["id"], damaged["relative"]).path.write_bytes(
        b"damaged after receipt")

    index_rebuild.rebuild(unit["id"], target)
    report = index_rebuild.compare(repo.conn, unit["id"], target)
    assert report["ok"] is False
    found = {(d["entity"], d["difference"], d.get("column")): d
             for d in report["differences"]}
    value = found[("claims", "value", "value")]
    assert (value["file"], value["row"]) == (old["case_file"], f"claims:{old['id']}")
    assert value["database"] == {"field": "edited in the database"}
    status = found[("reviews", "value", "status")]
    assert (status["file"], status["row"]) == (blind["case_file"],
                                               f"verifications:{blind['id']}")
    no_row = found[("function_files", "file_without_row", None)]
    assert (no_row["file"], no_row["row"]) == (lost_row["relative"], None)
    no_file = found[("function_files", "row_without_file", None)]
    assert (no_file["file"], no_file["row"]) == (
        damaged["relative"], f"function_files:{damaged['id']}")
    assert report["file_problems"] == [{"file": damaged["relative"],
                                        "problem": "case_file_tampered"}]


def test_rebuild_writes_only_into_an_empty_schema(operation_case, tmp_path,
                                                  target):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    index_rebuild.rebuild(unit["id"], target)
    with pytest.raises(index_rebuild.RebuildTargetNotEmpty):
        index_rebuild.rebuild(unit["id"], target)


def test_command_refuses_to_rebuild_into_the_live_database(monkeypatch):
    live = "postgresql://plm:synthetic@localhost:5432/plm_casefile"
    assert index_rebuild.same_database(
        live, "postgresql://other@127.0.0.1/plm_casefile")
    assert not index_rebuild.same_database(
        live, "postgresql://plm:synthetic@localhost:5432/plm_casefile_test")
    monkeypatch.setenv("CASEFILE_DSN", live)
    monkeypatch.setenv("CASEFILE_REBUILD_DSN", live)
    with pytest.raises(SystemExit, match="rebuild_target_is_the_live_database"):
        index_rebuild.run(1)
