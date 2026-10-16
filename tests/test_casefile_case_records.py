"""Corrections as superseding files (issue 05) — plumbing on isolated schemas.

Synthetic Claims and reviews only; no test asserts a title conclusion.
"""
from __future__ import annotations

import json

from src.casefile import case_file_store, case_records
from tests.helpers_casefile import Use
from tests.test_casefile_function_files import BLIND_OUTPUT, _outputs, _run
from tests.test_casefile_operational_flow import source
from tests.test_casefile_operations import approve, operation_case, task  # noqa: F401

REASON = "Synthetic correction reason."


def _claim(artifact, value):
    return {"tipo": "fact", "entidade": "Synthetic field",
            "valor": {"tipo_resultado": "fato_documental", "field": value},
            "documento": "sha256:" + artifact["sha256"], "pagina": "1",
            "trecho": "Synthetic fixture only.", "confianca": "alta",
            "materialidade": "baixa"}


def _files(unit_id):
    """Every byte under the Case folder, by path."""
    root = case_file_store.casefile_root(unit_id)
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def _body(unit_id, relative):
    return json.loads(case_file_store.read_bytes(unit_id, relative))


def _examined(repo, unit, tmp_path, *values):
    artifact = source(repo, unit, tmp_path / "synthetic.pdf")
    item = task(repo, unit, "examinador", "claims", mode="obrigatoria")
    result = _run(repo, unit, [[Use("entregar_saida", {"saida": {
        "claims": [_claim(artifact, v) for v in values]}})]])
    assert result["erros"] == []
    return artifact, item, result


def test_each_claim_of_an_applied_output_gets_its_own_file(operation_case,
                                                            tmp_path):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _, item, result = _examined(repo, unit, tmp_path, "first", "second")
    [output] = _outputs(repo, result["run_id"])
    claims = repo.claims_da_unit(unit["id"])
    stage = repo.estado_da_unit(unit["id"]).lower()
    assert [c["case_file"] for c in claims] == [
        f"{stage}/examinador/{item['id']}/claim_run{result['run_id']}"
        f"_attempt01_0{i}.json" for i in (1, 2)]
    for index, claim in enumerate(claims, start=1):
        body = _body(unit["id"], claim["case_file"])
        assert body["kind"] == "claim" and body["output_index"] == index
        assert body["output_file"] == {"relative": output["relative"],
                                       "sha256": output["sha256"]}
        assert body["claim"]["value"] == claim["value"]
    artifacts = [a for a in repo.operation_artifacts(unit["id"])
                 if a["kind"] == "case_record"]
    assert {a["metadata"]["relative"] for a in artifacts} == \
        {c["case_file"] for c in claims}
    assert {a["output_sha256"] for a in artifacts} == {output["sha256"]}


def test_a_repeated_apply_rewrites_the_same_claim_file_and_nothing_else(
        operation_case, tmp_path):
    import pytest
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _, item, result = _examined(repo, unit, tmp_path, "first")
    [output] = _outputs(repo, result["run_id"])
    [claim] = repo.claims_da_unit(unit["id"])
    written = claim["case_file"]
    # the index as a rolled-back apply leaves it: the file stays, the link not
    repo.conn.execute("UPDATE claims SET case_file=NULL WHERE id=%s",
                      (claim["id"],))
    current = repo.tarefa(item["id"])
    assert case_records.write_claim_files(repo, current, [claim["id"]],
                                          output) == [written]
    assert repo.claim(claim["id"])["case_file"] == written
    # different bytes for the same Claim file are refused, never replaced
    repo.conn.execute("UPDATE claims SET case_file=NULL, limitations=%s "
                      "WHERE id=%s", ("Synthetic change.", claim["id"]))
    with pytest.raises(case_file_store.CaseFileAlreadyWritten):
        case_records.write_claim_files(repo, current, [claim["id"]], output)


def test_replacing_a_claim_writes_a_superseding_file_and_history_reads_from_files(
        operation_case, tmp_path):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    artifact, _, _ = _examined(repo, unit, tmp_path, "first reading")
    [old] = repo.claims_da_unit(unit["id"])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    # blind extraction, then an independent comparison that diverges
    _run(repo, unit, [[Use("ler_pagina_confirmada", page)],
                      [Use("entregar_saida", {"saida": BLIND_OUTPUT})]])
    _run(repo, unit, [[Use("read_page", page)], [Use("entregar_saida", {"saida": {
        "claim_id": old["id"], "verdict": "divergencia",
        "source_sha256": artifact["sha256"], "page": "1",
        "quote": "Synthetic fixture only.", "reason": "Synthetic plumbing only.",
        "material_divergence": False}})]])
    blind, compared = repo.verificacoes_do_claim(old["id"])
    before = _files(unit["id"])
    # the Arbiter replaces the Claim
    result = _run(repo, unit, [[Use("ler_pagina", page)], [Use("entregar_saida", {"saida": {
        "claim_id": old["id"], "verificacao_id": compared["id"],
        "desfecho": "corrigido", "material_conclusao_titulo": False,
        "justificativa": REASON, "documento": "sha256:" + artifact["sha256"],
        "pagina": "1", "trecho": "Synthetic fixture only.",
        "novo_claim": _claim(artifact, "second reading")}})]])
    after = _files(unit["id"])
    assert {p: after[p] for p in before} == before     # nothing rewritten
    replaced = repo.claim(old["id"])
    new = repo.claim(replaced["superseded_by"])
    assert replaced["status"] == "substituido"
    record = case_file_store.read(unit["id"], new["case_file"])
    assert record.supersedes == old["case_file"] and record.reason == REASON
    assert record.relative.startswith(
        f"{record.stage}/arbitro/{result['tarefa']['id']}/claim_run")
    body = _body(unit["id"], new["case_file"])
    old_record = case_file_store.read(unit["id"], old["case_file"])
    assert body["supersedes"] == {"relative": old_record.relative,
                                  "sha256": old_record.sha256}
    assert body["reason"] == REASON
    # the history of the Claim, from the Case folder alone
    history = case_records.history(unit["id"], old["case_file"])
    assert [v["relative"] for v in history["versions"]] == \
        [old["case_file"], new["case_file"]]
    assert history["versions"][1]["reason"] == REASON
    assert history["current"] == new["case_file"]
    reviews = {r["relative"]: r for r in history["reviews"]}
    assert set(reviews) == {blind["case_file"], compared["case_file"]}
    assert reviews[blind["case_file"]]["reason"] == \
        "blind_extraction_awaiting_ai_comparison"
    assert reviews[compared["case_file"]]["invalidated_by"] is None
    assert case_records.history(unit["id"], new["case_file"]) == history


def test_invalidating_a_review_writes_a_file_naming_it_and_the_reason(
        operation_case, tmp_path):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    artifact, item, result = _examined(repo, unit, tmp_path, "first reading")
    [claim] = repo.claims_da_unit(unit["id"])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    blind_run = _run(repo, unit, [[Use("ler_pagina_confirmada", page)],
                                  [Use("entregar_saida", {"saida": BLIND_OUTPUT})]])
    [review] = repo.verificacoes_do_claim(claim["id"])
    assert review["status"] == "invalidada"
    review_record = case_file_store.read(unit["id"], review["case_file"])
    [later] = case_file_store.superseded_by(unit["id"], review["case_file"])
    body = _body(unit["id"], later.relative)
    assert body["kind"] == "review_invalidation"
    assert body["invalidated_file"] == {"relative": review_record.relative,
                                        "sha256": review_record.sha256}
    assert body["reason"] == later.reason == review["invalidation_reason"]
    assert later.relative.endswith("/invalidation_" + review_record.name)
    review_body = _body(unit["id"], review["case_file"])
    assert review_body["claim_file"]["relative"] == claim["case_file"]
    [output] = _outputs(repo, blind_run["run_id"])
    assert review_body["output_file"]["sha256"] == output["sha256"]


def test_a_claim_and_review_from_before_files_are_backfilled_then_superseded(
        operation_case, tmp_path):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    artifact, item, result = _examined(repo, unit, tmp_path, "first reading")
    [output] = _outputs(repo, result["run_id"])
    [examined] = repo.claims_da_unit(unit["id"])
    legacy = repo.inserir_claim(unit["id"], "fact", "Synthetic legacy field",
                                {"field": "legacy"}, artifact["sha256"], "1",
                                "Synthetic fixture only.", "alta", "baixa",
                                examined["session_id"])
    vid = repo.registrar_verificacao(legacy, "Synthetic question?",
                                     "concordancia", "synthetic-model",
                                     {"field": "legacy"}, {}, 0)
    before = _files(unit["id"])
    current = repo.tarefa(item["id"])
    relative = case_records.invalidate_review(repo, current, vid, REASON, output)
    after = _files(unit["id"])
    assert {p: after[p] for p in before} == before
    verification = repo.conn.execute(
        "SELECT * FROM verifications WHERE id=%s", (vid,)).fetchone()
    assert verification["status"] == "invalidada"
    backfilled = case_file_store.read(unit["id"], verification["case_file"])
    assert backfilled.name == f"review_index_{vid}.json"
    assert _body(unit["id"], backfilled.relative)["origin"] == "index_backfill"
    invalidation = case_file_store.read(unit["id"], relative)
    assert invalidation.supersedes == backfilled.relative
    assert invalidation.reason == REASON
    claim_record = case_file_store.read(unit["id"],
                                        repo.claim(legacy)["case_file"])
    assert claim_record.name == f"claim_index_{legacy}.json"
    # outside an applied output nothing is written; the index still changes
    other = repo.registrar_verificacao(legacy, "Synthetic question?",
                                       "concordancia", "synthetic-model",
                                       {"field": "legacy"}, {}, 0)
    assert case_records.invalidate_review(repo, current, other, REASON,
                                          None) is None
    assert _files(unit["id"]) == after
