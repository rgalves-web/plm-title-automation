"""Decision card for Renato (issue 11) — plumbing on isolated schemas.

Synthetic Claims and outputs only; no test asserts a title conclusion.
"""
from __future__ import annotations

import json

import pytest

from src.casefile import case_file_store, decision_card, operations, worker
from tests.helpers_casefile import ClientRoteirizado, Use
from tests.test_casefile_case_records import _claim
from tests.test_casefile_index_rebuild import target  # noqa: F401
from tests.test_casefile_operational_flow import source
from tests.test_casefile_operations import (approve, operation_case,  # noqa: F401
                                            request, task)

SUMMARY = ["O trecho corresponde literalmente à página.",
           "Desfecho: afirmação mantida.",
           "É um fato documental, por isso não foi escalado."]
NOTES = ["Observação para o Examinador: a tabela soma 10 unidades (sete de 1 e "
         "uma de 3, Block D-9 T.C. Ry. Co.) e o texto declara 12; conferir.",
         "Limite: a página 2 não foi lida. A conclusão vale só para a página 1."]
JUSTIFICATION = " ".join(["O Árbitro leu a página 1 da fonte sintética."]
                         + SUMMARY + NOTES)


def _run(repo, unit, steps):
    result = worker.executar_uma(repo, unit["id"], "synthetic-worker", teto=50,
                                 operation=True, client=ClientRoteirizado(steps))
    assert result["erros"] == [], result
    return result


def _awaiting_adjudication(repo, unit, scope, tmp_path, **extra):
    """A Claim with its own file, then an Arbiter adjudication that keeps it
    and waits for Renato."""
    approve(repo, unit, scope)
    artifact = source(repo, unit, tmp_path / "synthetic.pdf")
    examiner = task(repo, unit, "examinador", "claims", mode="obrigatoria")
    _run(repo, unit, [[Use("entregar_saida", {"saida": {
        "claims": [_claim(artifact, "first reading")]}})]])
    [cid] = repo.claims_da_tarefa(examiner["id"])
    for other in repo.tarefas(unit["id"], "pronta"):     # only the Arbiter runs
        repo.transicionar_tarefa(other["id"], ("pronta",), "cancelada",
                                 "human:test", "Only run the tested role.")
    arbiter = task(repo, unit, "arbitro", "adjudicacao", mode="operador",
                   data={"claim": {"id": cid, "page": "1"},
                         "verification": {"id": 999}})
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    output = {"claim_id": cid, "verificacao_id": 999, "desfecho": "mantido",
              "material_conclusao_titulo": False, "justificativa": JUSTIFICATION,
              "documento": "sha256:" + artifact["sha256"], "pagina": "1",
              "trecho": "Synthetic fixture only.", **extra}
    _run(repo, unit, [[Use("ler_pagina", page)],
                      [Use("entregar_saida", {"saida": output})]])
    assert repo.tarefa(arbiter["id"])["status"] == "aguardando_operador"
    return arbiter, cid, artifact


def test_the_card_states_the_decision_from_the_output_and_claim_files(
        operation_case, tmp_path):
    repo, unit, scope = operation_case
    arbiter, cid, artifact = _awaiting_adjudication(repo, unit, scope, tmp_path)
    card = decision_card.card(repo, arbiter["id"])
    assert card["available"] is True
    assert f"afirmação {cid}" in card["pergunta"]
    [claim] = card["afirmacoes"]
    assert (claim["id"], claim["documento"], claim["pagina"], claim["trecho"],
            claim["origem"]) == (cid, "synthetic.pdf", "1",
                                 "Synthetic fixture only.", "arquivo")
    assert claim["arquivo"] == repo.claim(cid)["case_file"]
    assert card["conclusao"]["decisao"] == f"Manteve a afirmação {cid}"
    assert card["conclusao"]["resumo"] == SUMMARY
    assert [o["texto"] for o in card["observacoes"]] == NOTES
    assert "passa a aceita" in card["efeitos"]["aceitar"]
    assert f"afirmação {cid} continua ativa" in card["efeitos"]["recusar"]
    [output] = [f for f in repo.function_files(task_id=arbiter["id"],
                                               direction="output")]
    assert card["fonte"] == {"saida": output["relative"],
                             "sha256": output["sha256"], "run_id": output["run_id"]}
    assert operations.task_detail(repo, arbiter["id"])["decision_card"] == \
        json.loads(json.dumps(card, default=str))


def test_the_card_reads_the_files_not_the_index(operation_case, tmp_path):
    repo, unit, scope = operation_case
    arbiter, cid, _ = _awaiting_adjudication(repo, unit, scope, tmp_path)
    repo.conn.execute("UPDATE claims SET evidence='edited in the index only' "
                      "WHERE id=%s", (cid,))
    assert decision_card.card(repo, arbiter["id"])["afirmacoes"][0]["trecho"] == \
        "Synthetic fixture only."
    [output] = repo.function_files(task_id=arbiter["id"], direction="output")
    case_file_store.read(unit["id"], output["relative"]).path.write_bytes(b"{}")
    damaged = decision_card.card(repo, arbiter["id"])
    assert damaged["available"] is False
    assert "case_file_tampered" in damaged["reason"]


def test_a_summary_and_observations_written_by_the_function_come_first(
        operation_case, tmp_path):
    repo, unit, scope = operation_case
    arbiter, _, _ = _awaiting_adjudication(
        repo, unit, scope, tmp_path, resumo="Mantida. A página confere.",
        observacoes=["Conferir a soma da tabela.", "Página 2 não lida."])
    card = decision_card.card(repo, arbiter["id"])
    assert card["conclusao"]["resumo"] == ["Mantida.", "A página confere."]
    assert [o["texto"] for o in card["observacoes"]] == \
        ["Conferir a soma da tabela.", "Página 2 não lida."]
    assert card["conclusao"]["justificativa"] == JUSTIFICATION


def test_an_observation_becomes_an_open_item_with_one_click(operation_case,
                                                            tmp_path):
    repo, unit, scope = operation_case
    arbiter, cid, artifact = _awaiting_adjudication(repo, unit, scope, tmp_path)
    operations.command(repo, request(repo, unit, "record_open_item",
                                     task_id=arbiter["id"], observation=1))
    card = decision_card.card(repo, arbiter["id"])
    item = card["observacoes"][0]["item_aberto"]
    assert item and card["observacoes"][1]["item_aberto"] is None
    claim = repo.claim(item)
    assert claim["value"]["tipo_resultado"] == decision_card.OPEN_ITEM
    assert claim["evidence"] == NOTES[0]
    assert claim["value"]["afirmacao_relacionada"] == cid
    assert claim["source_sha256"] == artifact["sha256"]
    body = json.loads(case_file_store.read_bytes(unit["id"], claim["case_file"]))
    assert body["kind"] == "claim" and body["origin"] == "observation"
    assert body["observation_index"] == 1
    assert body["output_file"]["relative"] == card["fonte"]["saida"]
    assert repo.tarefa(arbiter["id"])["status"] == "aguardando_operador"
    with pytest.raises(ValueError, match="open_item_already_recorded"):
        operations.command(repo, request(repo, unit, "record_open_item",
                                         task_id=arbiter["id"], observation=1))


def test_an_open_item_rebuilds_from_files_with_no_difference(
        operation_case, tmp_path, target):
    from src.casefile import index_rebuild
    repo, unit, scope = operation_case
    arbiter, _, _ = _awaiting_adjudication(repo, unit, scope, tmp_path)
    operations.command(repo, request(repo, unit, "record_open_item",
                                     task_id=arbiter["id"], observation=2))
    index_rebuild.rebuild(unit["id"], target)
    report = index_rebuild.compare(repo.conn, unit["id"], target)
    assert report["differences"] == [] and report["ok"] is True


def test_tasks_not_waiting_or_without_files_get_no_file_card(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    ready = task(repo, unit)
    assert decision_card.card(repo, ready["id"]) is None
    legacy = task(repo, unit, "arbitro", "adjudicacao", mode="operador")
    repo.transicionar_tarefa(legacy["id"], ("pronta",), "aguardando_operador",
                             "human:test", "A task from before output files.")
    card = decision_card.card(repo, legacy["id"])
    assert card["available"] is False and "anterior aos arquivos" in card["reason"]


def test_sentences_keep_abbreviations_and_brackets_together():
    text = ("Lido o Block D-9 (T.C. Ry. Co.) e o A-2. Soma 4.840 acres, texto "
            "4.800. Observação: conferir. Limite: página 2. Vale até a página 1.")
    assert decision_card.sentences(text) == [
        "Lido o Block D-9 (T.C. Ry. Co.) e o A-2.",
        "Soma 4.840 acres, texto 4.800.", "Observação: conferir.",
        "Limite: página 2.", "Vale até a página 1."]
    summary, notes = decision_card.split_justification(text)
    assert summary == ["Lido o Block D-9 (T.C. Ry. Co.) e o A-2.",
                       "Soma 4.840 acres, texto 4.800."]
    assert notes == ["Observação: conferir.",
                     "Limite: página 2. Vale até a página 1."]
