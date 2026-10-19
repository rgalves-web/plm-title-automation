"""Autonomous operation (issue 13) — plumbing on isolated PostgreSQL schemas.

Every Function's reply is scripted and synthetic; no test asserts a title
conclusion. The Lot runs through the terminal path, as real Cases do.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.casefile import autonomy, case_file_store, operations, rounds
from src.casefile.storage import digest_file
from tests.helpers_casefile import Msg, Use, unit_de_teste
from tests.test_casefile_function_files import BLIND_OUTPUT
from tests.test_casefile_operational_flow import source
from tests.test_casefile_operations import operation_case, request  # noqa: F401

QA_OUTPUT = {"lifecycle": "draft", "pronto": False, "itens": [
    {"checagem": "estrutura_formatacao", "estado": "pendente",
     "detalhe": "Synthetic QA observation only."}]}


class RoleScript:
    """A scripted Function per role: each new task of a role takes the next
    script of that role; a script is a list of turns, a turn a list of tool
    calls or a callable returning one."""

    def __init__(self, scripts):
        self.scripts = {role: list(items) for role, items in scripts.items()}
        self.current = []
        self.messages = self
        self.seen = []

    def create(self, **kwargs):
        system = kwargs["system"]
        text = system if isinstance(system, str) else " ".join(
            block.get("text", "") for block in system)
        role = re.search(r"Ficha da funcao `(\w+)`", text).group(1)
        if len(kwargs["messages"]) == 1:
            self.current = list(self.scripts[role].pop(0))
            self.seen.append(role)
        turn = self.current.pop(0)
        reply = Msg(content=turn() if callable(turn) else turn)
        reply.terminal_receipt = {"billing_mode": "subscription", "api_charge_usd": 0,
                                  "subscription_charge_usd": None}
        return reply


def _case(repo, tmp_path, name, scope=None):
    """A registered operation Case with a source page, a template and the
    terminal backend, like the Cibola profile."""
    unit = unit_de_teste(repo, tmp_path / name / "UNIT", name)
    root = Path(unit["folder_path"]).parent
    root.mkdir(parents=True, exist_ok=True)
    scope_md = root / "scope.md"
    scope_md.write_text("Synthetic scope only.", encoding="utf-8")
    repo.registrar_politica(unit["id"], "project_profile", json.dumps({
        "schema": 1, "work_type": "surface_title", "name": "synthetic",
        "project_root": str(root), "planning_system": "synthetic",
        "planning_task": "synthetic",
        "sources": [{"path": str(scope_md), "sha256": digest_file(scope_md)}]}))
    repo.operation_register(unit["id"], scope or {
        "work_type": "surface_title", "pid": "test", "county": "Terrell",
        "start_date": "1966-01-01", "through_date": "2026-10-11", "sources": ["local"]})
    return _prepare(repo, unit, tmp_path / name)


def _prepare(repo, unit, folder):
    import openpyxl
    folder.mkdir(parents=True, exist_ok=True)
    artifact = source(repo, unit, folder / "synthetic.pdf")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Surface"
    sheet["A1"] = "Example"
    sheet["B1"] = "=1+1"
    template = folder / "template.xlsx"
    workbook.save(template)
    entry = repo.operation_add_artifact(unit["id"], "template", template,
                                        digest_file(template), template.stat().st_size)
    case = repo.operation_case(unit["id"])
    repo.operation_update(unit["id"], profile={
        **case["profile"], "execution_backend": "terminal",
        "template_artifact_id": entry["id"], "lead_example_artifact_id": entry["id"],
        "sample_data_clearance": "clear_declared_cells",
        "sample_cells": [{"sheet": "Surface", "cell_ref": "A1"}]})
    return unit, artifact


def _claim(artifact):
    return {"tipo": "fact", "entidade": "Synthetic field",
            "valor": {"tipo_resultado": "fato_documental", "field": "sample"},
            "documento": "sha256:" + artifact["sha256"], "pagina": "1",
            "trecho": "Synthetic fixture only.", "confianca": "alta",
            "materialidade": "alta"}


def _plan(artifact):
    return {"tarefas": [{"ref": "exam-1", "role": "examinador",
                         "title": "Synthetic examination",
                         "input_json": {"documento": "sha256:" + artifact["sha256"]},
                         "acceptance": "Synthetic Claims with page and quote.",
                         "depends_on": [], "budget_usd": 1, "priority": 1,
                         "justificativa": "Synthetic plumbing only."}]}


def _comparison(repo, unit, artifact, verdict="concordancia"):
    [claim] = repo.claims_da_unit(unit["id"])
    return [Use("entregar_saida", {"saida": {
        "claim_id": claim["id"], "verdict": verdict,
        "source_sha256": artifact["sha256"], "page": "1",
        "quote": "Synthetic fixture only.", "reason": "Synthetic plumbing only.",
        "material_divergence": False}})]


def _writer(repo, unit):
    [claim] = repo.claims_da_unit(unit["id"])
    return [Use("entregar_saida", {"saida": {"celulas": [
        {"sheet": "Surface", "cell_ref": "A1", "value": "Synthetic report value",
         "claim_ids": [claim["id"]]}], "brancos": []}})]


def _script(repo, unit, artifact, verdict="concordancia"):
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    return RoleScript({
        "coordenador": [[[Use("entregar_saida", {"saida": _plan(artifact)})]]],
        "examinador": [[[Use("entregar_saida", {"saida": {"claims": [_claim(artifact)]}})]]],
        "verificador": [[[Use("ler_pagina_confirmada", page)],
                         [Use("entregar_saida", {"saida": BLIND_OUTPUT})]]] * 3,
        "arbitro": [[[Use("read_page", page)],
                     lambda: _comparison(repo, unit, artifact, verdict)]] * 3,
        "redator": [[lambda: _writer(repo, unit)]],
        "qa_pacote": [[[Use("entregar_saida", {"saida": QA_OUTPUT})]]],
    })


def _lot(repo, units, turns=40, routine="cibola_surface", **envelope):
    first = units[0]
    operations.command(repo, request(
        repo, first, "create_lot", job={"plm_job_id": "SYNTH-JOB-1", "routine": routine},
        unit_ids=[u["id"] for u in units],
        envelope={"sources": ["local"], "turn_cap_per_case": turns, **envelope}))
    return repo.conn.execute("SELECT * FROM operation_lots ORDER BY id DESC").fetchone()


def _drive(repo, cases, until=("deliverable", "stopped", "awaiting_exceptions"),
           limit=60):
    """Step each Case until it reaches one of `until` (or stops moving)."""
    final = {}
    for _ in range(limit):
        moved = False
        for unit, client in cases:
            if unit["id"] in final:
                continue
            action = autonomy.step(repo, unit["id"], client)
            if action in until:
                final[unit["id"]] = action
            elif action in ("ran", "writer", "qa"):
                moved = True
            elif action == "idle":
                final[unit["id"]] = autonomy.open_lot_case(repo, unit["id"])["status"]
        if len(final) == len(cases) or not moved and all(
                autonomy.coordinate(repo, u["id"]) != "working" for u, _ in cases
                if u["id"] not in final):
            break
    return final


def _human_commands(repo):
    return [e["kind"] for e in repo.conn.execute(
        "SELECT kind FROM operation_events WHERE actor LIKE 'human:%%' "
        "AND kind LIKE 'operator.%%' ORDER BY id").fetchall()]


def test_a_two_case_lot_runs_to_release_with_no_operator_action_but_release(
        operation_case, tmp_path):
    repo, _, _ = operation_case
    first, art1 = _case(repo, tmp_path, "CASE-A")
    second, art2 = _case(repo, tmp_path, "CASE-B")
    lot = _lot(repo, [first, second])
    final = _drive(repo, [(first, _script(repo, first, art1)),
                          (second, _script(repo, second, art2))])
    assert final == {first["id"]: "deliverable", second["id"]: "deliverable"}
    assert _human_commands(repo) == ["operator.create_lot"]
    for unit in (first, second):
        lc = autonomy.open_lot_case(repo, unit["id"])
        assert lc["status"] == "deliverable_ready"
        assert repo.estado_da_unit(unit["id"]) == "AGUARDANDO_RENATO"
        accepted = repo.conn.execute(
            "SELECT * FROM operation_acceptances WHERE unit_id=%s ORDER BY id",
            (unit["id"],)).fetchall()
        roles = [repo.tarefa(a["task_id"])["role"] for a in accepted]
        assert roles == ["examinador", "redator", "qa_pacote"]
        for row in accepted:
            body = json.loads(case_file_store.read_bytes(unit["id"], row["relative"]))
            assert body["accepted_by"] == "coordinator" and body["rule"] == autonomy.RULE
            assert body["reason"] and body["open_items"] == []
            for claim in body["dispositions"]:
                assert claim["arbiter"]["keep"] is True
                assert claim["verifier"]["concurs"] is True
                assert claim["verifier"]["blind_extraction"] is True
                assert claim["citation"]["matches"] is True
        package = repo.operation_artifact(lc["deliverable_artifact_id"])
        root = Path(package["metadata"]["package_root"])
        assert (root / "1. Landman Submitted" / "Title Documents" / "Surface").is_dir()
        assert Path(package["path"]).parent.name == "1. Landman Submitted"
        manifest = json.loads(Path(package["metadata"]["manifest"]).read_text("utf-8"))
        assert manifest["status"] == "WORKING DRAFT" and manifest["documents_copied"] is False
        assert manifest["cited_documents"][0]["sha256"]
        kinds = [d["kind"] for d in repo.conn.execute(
            "SELECT kind FROM operation_coordinator_decisions WHERE unit_id=%s ORDER BY id",
            (unit["id"],))]
        for kind in ("open_round", "advance_stage", "writer_ready", "qa_ready",
                     "deliverable_ready"):
            assert kind in kinds
        ready = repo.conn.execute(
            "SELECT relative FROM operation_coordinator_decisions WHERE unit_id=%s "
            "AND kind='deliverable_ready'", (unit["id"],)).fetchone()
        turns = json.loads(case_file_store.read_bytes(unit["id"], ready["relative"])
                           )["detail"]["turns_by_function"]
        assert turns == autonomy.turns_by_function(repo, unit["id"])
        assert set(turns) <= {"coordenador", "examinador", "verificador", "comparacao",
                              "arbitro", "redator", "qa_pacote"} and turns["examinador"] >= 1
        assert turns["comparacao"] >= 1 and "arbitro" not in turns
        assert sum(turns.values()) == autonomy.overview(repo, unit["id"])["turns_used"]
        for d in repo.conn.execute("SELECT relative FROM operation_coordinator_decisions "
                                   "WHERE unit_id=%s", (unit["id"],)):
            assert json.loads(case_file_store.read_bytes(unit["id"], d["relative"]))["reason"]
        assert [e["kind"] for e in autonomy.open_exceptions(repo, unit["id"])] == \
            ["protocol_pending"]
    for unit in (first, second):
        operations.command(repo, request(repo, unit, "release_case"))
        assert repo.estado_da_unit(unit["id"]) == "LIBERADA"
    assert _human_commands(repo) == ["operator.create_lot", "operator.release_case",
                                     "operator.release_case"]
    assert repo.conn.execute("SELECT closed_at FROM operation_lots WHERE id=%s",
                             (lot["id"],)).fetchone()["closed_at"]


def test_a_divergence_lands_in_the_queue_and_a_re_read_resolves_it(
        operation_case, tmp_path):
    import fitz
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-D")
    path = Path(artifact["path"])
    with fitz.open(path) as single, fitz.open() as double:
        double.insert_pdf(single)
        double.new_page().insert_text((30, 60), "Synthetic second page.")
        double.save(tmp_path / "two-pages.pdf")
    two = tmp_path / "two-pages.pdf"
    repo.registrar_source_file(digest_file(two), two.stat().st_size)
    artifact = repo.operation_add_artifact(unit["id"], "source", two, digest_file(two),
                                           two.stat().st_size)
    _lot(repo, [unit])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    script = _script(repo, unit, artifact, verdict="divergencia")
    second = {"documento": artifact["sha256"], "pagina": 2, "modo": "texto"}
    script.scripts["verificador"] = [
        [[Use("ler_pagina_confirmada", page)], [Use("entregar_saida", {"saida": BLIND_OUTPUT})]],
        [[Use("ler_pagina_confirmada", page, id="a"), Use("ler_pagina_confirmada", second, id="b")],
         [Use("entregar_saida", {"saida": BLIND_OUTPUT})]]]
    script.scripts["arbitro"] = [
        [[Use("read_page", page)], lambda: _comparison(repo, unit, artifact, "divergencia")],
        [[Use("ler_pagina", page)], lambda: [Use("entregar_saida", {"saida": {
            "claim_id": repo.claims_da_unit(unit["id"])[0]["id"],
            "verificacao_id": repo.verificacoes_do_claim(
                repo.claims_da_unit(unit["id"])[0]["id"])[-1]["id"],
            "desfecho": "mantido", "material_conclusao_titulo": False,
            "justificativa": "Synthetic plumbing only.",
            "documento": "sha256:" + artifact["sha256"], "pagina": "1",
            "trecho": "Synthetic fixture only."}})]],
        [[Use("read_page", page)], lambda: _comparison(repo, unit, artifact)]]
    assert _drive(repo, [(unit, script)]) == {unit["id"]: "awaiting_exceptions"}
    [entry] = [e for e in autonomy.open_exceptions(repo, unit["id"])
               if e["kind"] == "divergence"]
    adjudication = repo.tarefa(entry["task_id"])
    assert adjudication["output_schema"] == "adjudicacao"
    assert adjudication["status"] == "aguardando_operador"
    assert "re_read" in entry["options"] and "accept" in entry["options"]
    assert _lot_task_count(repo, unit, "redator") == 0     # Writer waits
    operations.command(repo, request(repo, unit, "resolve_exception",
                                     exception_id=entry["id"], option="re_read"))
    reread = [t for t in repo.tarefas(unit["id"]) if "-r1" in t["ref"]]
    assert reread and reread[0]["parent_task_id"] == adjudication["id"]
    assert reread[0]["input_json"]["pagina"] == "1-2"
    final = _drive(repo, [(unit, script)])
    assert repo.tarefa(adjudication["id"])["status"] == "aceita"
    accepted = repo.conn.execute("SELECT * FROM operation_acceptances WHERE task_id=%s",
                                 (adjudication["id"],)).fetchone()
    assert accepted is not None
    assert final[unit["id"]] in ("deliverable", "awaiting_exceptions")


def _lot_task_count(repo, unit, kind):
    return sum(t["ref"].startswith("lote-") and f"-{kind}-" in t["ref"]
               for t in repo.tarefas(unit["id"]))


def test_one_click_accept_and_preset_reject_from_the_queue(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-C")
    _lot(repo, [unit])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    script = _script(repo, unit, artifact, verdict="divergencia")
    adjudication = lambda: [Use("entregar_saida", {"saida": {  # noqa: E731
        "claim_id": repo.claims_da_unit(unit["id"])[0]["id"],
        "verificacao_id": repo.verificacoes_do_claim(
            repo.claims_da_unit(unit["id"])[0]["id"])[-1]["id"],
        "desfecho": "mantido", "material_conclusao_titulo": False,
        "justificativa": "Synthetic plumbing only.",
        "documento": "sha256:" + artifact["sha256"], "pagina": "1",
        "trecho": "Synthetic fixture only."}})]
    script.scripts["arbitro"] = [
        [[Use("read_page", page)], lambda: _comparison(repo, unit, artifact, "divergencia")],
        [[Use("ler_pagina", page)], adjudication]]
    _drive(repo, [(unit, script)])
    [entry] = [e for e in autonomy.open_exceptions(repo, unit["id"])
               if e["kind"] == "divergence"]
    with pytest.raises(ValueError, match="option_not_available"):
        operations.command(repo, request(repo, unit, "resolve_exception",
                                         exception_id=entry["id"], option="raise_cap"))
    operations.command(repo, request(repo, unit, "resolve_exception",
                                     exception_id=entry["id"], option="accept"))
    task = repo.tarefa(entry["task_id"])
    assert task["status"] == "aceita"
    note = repo.transicoes_da_tarefa(task["id"])[-1]["note"]
    assert note.startswith("Aceito por Renato com um clique; motivo gerado a partir do cartão")
    assert "output_run" in note
    closed = repo.conn.execute("SELECT * FROM escalations WHERE id=%s",
                               (entry["id"],)).fetchone()
    assert closed["respondido_em"] and closed["resolution"]["option"] == "accept"


def test_envelope_exhaustion_stops_the_case_and_never_continues(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-E")
    _lot(repo, [unit], turns=2)
    script = _script(repo, unit, artifact)
    assert _drive(repo, [(unit, script)]) == {unit["id"]: "stopped"}
    lc = autonomy.open_lot_case(repo, unit["id"])
    assert (lc["status"], lc["stop_reason"]) == ("stopped", "envelope_turns")
    assert repo.operation_case(unit["id"])["execution_state"] == "waiting"
    [entry] = [e for e in autonomy.open_exceptions(repo, unit["id"])
               if e["kind"] == "envelope_exhausted"]
    calls = repo.conn.execute("SELECT count(*) AS n FROM operation_terminal_calls").fetchone()["n"]
    for _ in range(3):
        assert autonomy.step(repo, unit["id"], script) == "idle"
    assert repo.conn.execute("SELECT count(*) AS n FROM operation_terminal_calls"
                             ).fetchone()["n"] == calls == 2
    with pytest.raises(ValueError, match="lot_case_stopped_resume_from_exceptions_queue"):
        operations.command(repo, request(repo, unit, "resume"))
    operations.command(repo, request(repo, unit, "resolve_exception",
                                     exception_id=entry["id"], option="raise_cap",
                                     params={"turns": 20}))
    assert autonomy.open_lot_case(repo, unit["id"])["status"] == "running"
    assert rounds.state(repo, unit["id"])["turns_remaining"] == 20
    assert autonomy.step(repo, unit["id"], script) == "ran"


def test_a_blocked_task_reaches_the_queue_and_retry_works(operation_case, tmp_path):
    from src.casefile import orquestracao
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-F")
    _lot(repo, [unit])
    coordinator = [t for t in repo.tarefas(unit["id"]) if t["role"] == "coordenador"][0]
    got = orquestracao.pegar(repo, unit["id"], "synthetic", teto=50, max_active_per_unit=1,
                             rodada=True)
    repo.fechar_run(got[1]["id"], "synthetic", output_json=None, output_valid=None,
                    validation_errors=["synthetic"], stop_reason="synthetic_block",
                    para="bloqueada")
    assert autonomy.coordinate(repo, unit["id"]) == "awaiting_exceptions"
    [entry] = [e for e in autonomy.open_exceptions(repo, unit["id"])
               if e["kind"] == "case_blocked"]
    assert entry["task_id"] == coordinator["id"] and "synthetic_block" in entry["pergunta"]
    operations.command(repo, request(repo, unit, "resolve_exception",
                                     exception_id=entry["id"], option="retry"))
    assert repo.tarefa(coordinator["id"])["status"] == "pronta"
    assert autonomy.open_lot_case(repo, unit["id"])["status"] == "running"
    assert autonomy.step(repo, unit["id"], _script(repo, unit, artifact)) == "ran"


def test_a_case_the_worker_parks_goes_back_to_the_coordinator(operation_case, tmp_path):
    from src.casefile import orquestracao
    from tests.test_casefile_operations import task as ready_task
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-P")
    _lot(repo, [unit])
    uid = unit["id"]

    def park(task_id):
        got = orquestracao.pegar(repo, uid, "synthetic", teto=50, max_active_per_unit=1,
                                 rodada=True)
        assert got[0]["id"] == task_id
        repo.fechar_run(got[1]["id"], "synthetic", output_json=None, output_valid=None,
                        validation_errors=["synthetic"],
                        stop_reason="terminal_interrupted_no_automatic_retry", para="bloqueada")
        repo.operation_update(uid, execution_state="waiting")

    coordinator = [t for t in repo.tarefas(uid) if t["role"] == "coordenador"][0]
    park(coordinator["id"])
    extra = ready_task(repo, unit)
    assert autonomy.parked_lot_cases(repo) == [uid]
    assert autonomy.wake(repo, uid) == "working"
    assert repo.operation_case(uid)["execution_state"] == "running"
    assert autonomy.open_lot_case(repo, uid)["status"] == "running"
    assert [e["task_id"] for e in autonomy.open_exceptions(repo, uid)
            if e["kind"] == "case_blocked"] == [coordinator["id"]]
    assert repo.conn.execute(
        "SELECT count(*) AS n FROM operation_coordinator_decisions WHERE unit_id=%s "
        "AND kind='resume'", (uid,)).fetchone()["n"] == 1
    repo.operation_update(uid, execution_state="paused")
    assert autonomy.parked_lot_cases(repo) == []
    assert autonomy.wake(repo, uid) == "idle"
    assert repo.operation_case(uid)["execution_state"] == "paused"
    repo.operation_update(uid, execution_state="running")
    park(extra["id"])
    assert autonomy.wake(repo, uid) == "awaiting_exceptions"
    lc = autonomy.open_lot_case(repo, uid)
    assert (lc["status"], lc["stop_reason"]) == ("stopped", "awaiting_exceptions")
    assert autonomy.wake(repo, uid) == "idle"
    assert len([e for e in autonomy.open_exceptions(repo, uid)
                if e["kind"] == "case_blocked"]) == 2


def test_in_a_lot_a_verified_result_waits_for_the_coordinator(operation_case, tmp_path):
    from src.casefile import orquestracao
    from tests.test_casefile_operations import task as ready_task
    from tests.test_casefile_orquestracao import _claim
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-V")
    _lot(repo, [unit])
    exam = ready_task(repo, unit, role="examinador", mode="obrigatoria")
    repo.transicionar_tarefa(exam["id"], ("pronta",), "aguardando_verificacao",
                             "process:test", "Synthetic plumbing only.")
    claim = _claim(repo, unit)
    repo.vincular_claims(exam["id"], [claim])
    repo.registrar_verificacao(claim, "q", "concordancia", "b", {}, {}, 0.0)
    got = orquestracao.aceitar_por_verificacao(repo, exam["id"])
    assert not got["aceita"] and got["tarefa"]["status"] == "aguardando_operador"


class FailingCall:
    """A terminal whose call fails with the given reason and CLI text."""

    def __init__(self, reason, text=""):
        self.reason, self.text, self.messages = reason, text, self

    def create(self, **kwargs):
        from src.infra.terminal import TerminalError
        raise TerminalError(self.reason, self.text)


@pytest.mark.parametrize("reason,text,expected", [
    ("terminal_failed_requires_review:A", '{"result": "Claude AI usage limit reached (synthetic)"}',
     "limit"),
    ("terminal_failed_requires_review:A", "synthetic crash: exit status 3", "crash"),
    ("terminal_output_invalid", "", "invalid_output"),
    ("terminal_subscription_login_required:A", "", "login"),
])
def test_the_coordinator_acts_on_the_failure_class_with_one_queue_entry(
        operation_case, tmp_path, reason, text, expected):
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-T")
    _lot(repo, [unit])
    uid = unit["id"]
    [coordinator] = [t for t in repo.tarefas(uid) if t["role"] == "coordenador"]
    assert autonomy.step(repo, uid, FailingCall(reason, text)) == "ran"
    assert repo.tarefa(coordinator["id"])["status"] == "bloqueada"
    assert repo.operation_case(uid)["execution_state"] == "waiting"
    [call] = repo.conn.execute("SELECT * FROM operation_terminal_calls").fetchall()
    assert call["failure_class"] == expected and call["failure_relative"]
    action = autonomy.wake(repo, uid)
    lc = autonomy.open_lot_case(repo, uid)
    entries = [e for e in autonomy.open_exceptions(repo, uid)
               if e["task_id"] == coordinator["id"] or e["kind"] == "envelope_exhausted"]
    if expected == "limit":
        assert action == "waiting_limit"
        assert (lc["status"], lc["stop_reason"]) == ("running", "waiting_limit")
        assert lc["resume_at"] and entries == [] and repo.task_attempts(coordinator["id"]) == 0
        assert repo.tarefa(coordinator["id"])["status"] == "pronta"
        assert autonomy.wake(repo, uid) == "waiting_limit"
        assert repo.operation_case(uid)["execution_state"] == "waiting"
        repo.conn.execute("UPDATE operation_lot_cases SET resume_at=now()-interval '1 minute' "
                          "WHERE unit_id=%s", (uid,))
        assert autonomy.wake(repo, uid) == "working"
        assert repo.operation_case(uid)["execution_state"] == "running"
    elif expected == "invalid_output":
        assert action == "working" and entries == []
        assert repo.tarefa(coordinator["id"])["status"] == "pronta"
        assert repo.task_attempts(coordinator["id"]) == 1
    else:
        assert action == "stopped" and len(entries) == 1
        assert entries[0]["detail"]["adopted_worker_entry"] is True
        assert lc["stop_reason"] == {"crash": "cli_crash", "login": "envelope_cli"}[expected]
    assert not [e for e in autonomy.open_exceptions(repo, uid)
                if e["kind"] == "escalation" and e["task_id"] == coordinator["id"]]


def test_the_arbiter_escalation_and_the_divergence_are_one_queue_item_per_claim(
        operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-M")
    _lot(repo, [unit])
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    script = _script(repo, unit, artifact, verdict="divergencia")
    script.scripts["arbitro"] = [
        [[Use("read_page", page)], lambda: _comparison(repo, unit, artifact, "divergencia")],
        [[Use("ler_pagina", page)], lambda: [Use("entregar_saida", {"saida": {
            "claim_id": repo.claims_da_unit(unit["id"])[0]["id"],
            "verificacao_id": repo.verificacoes_do_claim(
                repo.claims_da_unit(unit["id"])[0]["id"])[-1]["id"],
            "desfecho": "escalado", "material_conclusao_titulo": True,
            "justificativa": "Synthetic plumbing only.",
            "documento": "sha256:" + artifact["sha256"], "pagina": "1",
            "trecho": "Synthetic fixture only.",
            "escalonamento": {"motivo": "material_title",
                              "pergunta": "Synthetic arbiter question.",
                              "opcoes": ["consultar SME", "fornecer evidência"],
                              "evidencias": [{"documento": "sha256:" + artifact["sha256"],
                                              "pagina": "1",
                                              "trecho": "Synthetic fixture only."}]}}})]]]
    assert _drive(repo, [(unit, script)]) == {unit["id"]: "awaiting_exceptions"}
    [claim] = repo.claims_da_unit(unit["id"])
    about_claim = [e for e in autonomy.open_exceptions(repo, unit["id"])
                   if e["kind"] in autonomy.RESULT_KINDS or e["motivo"] == "material_title"]
    assert len(about_claim) == 1 and about_claim[0]["kind"] == "divergence"
    assert "Synthetic arbiter question." in about_claim[0]["pergunta"]
    [merged] = about_claim[0]["detail"]["merged_escalations"]
    closed = repo.conn.execute("SELECT * FROM escalations WHERE id=%s", (merged["id"],)).fetchone()
    assert closed["respondido_em"] and closed["resolution"]["merged_into"] == about_claim[0]["id"]
    assert repo.conn.execute(
        "SELECT count(*) AS n FROM operation_coordinator_decisions WHERE unit_id=%s "
        "AND kind='merge'", (unit["id"],)).fetchone()["n"] == 1


def test_the_job_routine_sets_the_pack_and_never_falls_back_to_the_default(
        operation_case, tmp_path):
    from src.casefile.operations import seed_coordinator
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-R")
    with pytest.raises(ValueError, match="job_routine_required"):
        operations.command(repo, request(
            repo, unit, "create_lot", job={"plm_job_id": "SYNTH-JOB-1"},
            unit_ids=[unit["id"]], envelope={"sources": ["local"]}))
    stale = seed_coordinator(repo, unit["id"], 5)
    assert stale["pack"] == "title-texas-surface"
    _lot(repo, [unit], routine="emirates_minerals")
    assert repo.tarefa(stale["id"])["status"] == "cancelada"
    [live] = [t for t in repo.tarefas(unit["id"])
              if t["role"] == "coordenador" and t["status"] == "pronta"]
    assert live["pack"] == "title-texas-oil-gas-dd"
    assert live["input_json"]["routine"]["id"] == "emirates_minerals"
    assert repo.operation_case(unit["id"])["scope"]["work_type"] == "oil_gas_dd"
    assert repo.operation_pack(unit["id"]) == "title-texas-oil-gas-dd"
    writer = autonomy._create_phase_task(repo, autonomy.open_lot_case(repo, unit["id"]),
                                         "redator")
    assert writer["pack"] == "title-texas-oil-gas-dd"


def test_an_open_item_blocks_auto_accept_until_dismissed(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-H")
    _lot(repo, [unit])
    script = _script(repo, unit, artifact)
    item = None
    for _ in range(20):
        autonomy.step(repo, unit["id"], script)
        waiting = [t for t in repo.tarefas(unit["id"], "aguardando_operador")
                   if t["role"] == "examinador"]
        if waiting:
            session = repo.abrir_sessao(unit["id"], "synthetic", "synthetic-model")
            item = repo.inserir_claim(
                unit_id=unit["id"], claim_type="fact", entity="Synthetic",
                value={"tipo_resultado": "item_aberto", "observacao": "Synthetic open item."},
                source_sha256=artifact["sha256"], page="1", evidence="Synthetic open item.",
                confidence="media", materiality="media", session_id=session)
            break
    assert item is not None
    examiner = waiting[0]
    assert autonomy.coordinate(repo, unit["id"]) == "awaiting_exceptions"
    [entry] = [e for e in autonomy.open_exceptions(repo, unit["id"])
               if e["kind"] == "open_item"]
    assert entry["task_id"] == examiner["id"]
    assert repo.tarefa(examiner["id"])["status"] == "aguardando_operador"
    operations.command(repo, request(repo, unit, "resolve_exception",
                                     exception_id=entry["id"], option="dismiss"))
    assert repo.claim(item)["status"] == "retirado"
    autonomy.coordinate(repo, unit["id"])
    assert repo.tarefa(examiner["id"])["status"] == "aceita"


def test_sample_audit_suspends_a_claim_type_until_turned_back_on(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-G")
    _lot(repo, [unit], audit_rate=1.0, audit_wrong_limit=2)
    _drive(repo, [(unit, _script(repo, unit, artifact))])
    accepted = repo.conn.execute("SELECT * FROM operation_acceptances WHERE unit_id=%s "
                                 "ORDER BY id", (unit["id"],)).fetchall()
    assert len(accepted) == 3 and all(a["sampled"] for a in accepted)
    for row in accepted:
        operations.command(repo, request(repo, unit, "audit_acceptance",
                                         acceptance_id=row["id"], mark="wrong"))
    assert autonomy.overview(repo, unit["id"])["suspended_claim_types"] == ["fact"]
    operations.command(repo, request(repo, unit, "resume_autoaccept", claim_type="fact"))
    assert autonomy.overview(repo, unit["id"])["suspended_claim_types"] == []
