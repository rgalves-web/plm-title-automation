"""Issue 17: the Job's sources are the envelope. Plumbing only: the HTTP
sources are stubbed, nothing leaves the machine, and no test asserts a title
conclusion."""
from __future__ import annotations

import json

import httpx
import pytest

from src.casefile import autonomy, routines, runtime, source_adapters
from tests.test_casefile_autonomy import _case, _lot
from tests.test_casefile_operations import operation_case, task as ready_task  # noqa: F401


def _stub(monkeypatch, handler):
    monkeypatch.setattr(source_adapters, "_http", lambda: httpx.Client(
        transport=httpx.MockTransport(handler), headers=source_adapters.UA,
        follow_redirects=True))


GLO_PAGE = ('<script type="application/json" data-drupal-selector="drupal-settings-json">'
            + json.dumps({"antibot": {"forms": {"glo-custom-land-grant-search": {"key": "abcd"}}}})
            + '</script><input name="form_build_id" value="form-synthetic" />')
GLO_RESULT = ('<p>Showing 1 to 1 out of 1 results</p><table><tr><th>County</th></tr>'
              '<tr><td>Synthetic</td><td><a href="/land-grant/1">1</a></td><td>School</td>'
              '<td>000001</td><td>Synthetic Grantee</td><td>Synthetic Patentee</td>'
              '<td><a href="https://cdn.glo.texas.gov/synthetic/1.pdf">View PDF</a></td></tr></table>')


def test_the_envelope_is_every_job_source_and_never_rrc(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-S1")
    case = repo.operation_case(unit["id"])
    env = autonomy._envelope({}, case, 0, "cibola_surface")
    assert env["sources"] == routines.job_sources("cibola_surface") and "rrc" not in env["sources"]
    with pytest.raises(ValueError, match="rrc"):
        autonomy._envelope({"sources": ["local", "rrc"]}, case, 0, "cibola_surface")
    with pytest.raises(ValueError, match="envelope_sources_unknown"):
        autonomy._envelope({"sources": ["terrell_cad"]}, case, 0, "emirates_minerals")


def test_a_new_lot_declaration_supersedes_a_stopped_lot_case(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-S2")
    uid = unit["id"]
    first = _lot(repo, [unit])
    with pytest.raises(ValueError, match="case_already_in_an_open_lot"):
        _lot(repo, [unit])
    repo.conn.execute("UPDATE operation_lot_cases SET status='stopped',stop_reason='envelope_turns' "
                      "WHERE unit_id=%s", (uid,))
    second = _lot(repo, [unit], sources=routines.job_sources("cibola_surface"))
    rows = repo.conn.execute("SELECT lot_id, status FROM operation_lot_cases WHERE unit_id=%s "
                             "ORDER BY lot_id", (uid,)).fetchall()
    assert [(r["lot_id"], r["status"]) for r in rows] == [(first["id"], "superseded"),
                                                          (second["id"], "running")]
    assert autonomy.open_lot_case(repo, uid)["lot_id"] == second["id"]
    assert repo.operation_case(uid)["scope"]["sources"] == routines.job_sources("cibola_surface")


def test_glo_search_reads_the_antibot_key_and_maps_the_columns(monkeypatch):
    seen = {}

    def handler(request):
        if request.url.path.endswith("landgrant-ajax"):
            seen.update(dict(request.url.params))
            return httpx.Response(200, text=GLO_RESULT)
        return httpx.Response(200, text=GLO_PAGE)
    _stub(monkeypatch, handler)
    receipt = source_adapters.glo_search({"scope": {"county": "Synthetic"}},
                                         {"terms": ["Synthetic Grantee"], "index": "grantee"})
    assert seen["antibot_key"] == "cdab" and seen["originalgrantee"] == "Synthetic Grantee"
    assert seen["county"] == "SYNTHETIC" and receipt["reported_total"] == receipt["saved_total"] == 1
    [row] = receipt["results"]
    assert (row["file_number"], row["grantee"], row["pdf"]) == (
        "000001", "Synthetic Grantee", "https://cdn.glo.texas.gov/synthetic/1.pdf")


def test_topics_search_and_a_network_block_are_named(monkeypatch):
    def handler(request):
        if request.url.host == "topics.txcourts.gov":
            return httpx.Response(200, json={"data": [["Synthetic style", "C-1", "Synthetic Court",
                                                       "Active", "9"]]})
        raise httpx.ConnectTimeout("synthetic", request=request)
    _stub(monkeypatch, handler)
    receipt = source_adapters.topics_search({"terms": ["Synthetic"]})
    assert receipt["results"] == [{"style": "Synthetic style", "cause": "C-1",
                                   "court": "Synthetic Court", "status": "Active", "id": "9"}]
    with pytest.raises(source_adapters.SourceUnavailable, match="network_unreachable:terrell_cad"):
        source_adapters.cad_view({"scope": {"pid": "123"}}, {"terms": []})
    assert source_adapters.blocked_access("terrell_cad", "network_unreachable:terrell_cad:x") == "network"
    assert source_adapters.blocked_access("pacer", "paid_source:pacer") == "paid"


def test_a_paid_source_is_never_searched_and_a_glo_pdf_becomes_a_source(operation_case, tmp_path,
                                                                        monkeypatch):
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-S3")
    _lot(repo, [unit], sources=routines.job_sources("cibola_surface"))
    researcher = ready_task(repo, unit)
    blocked = source_adapters.execute(repo, researcher, "pacer", {"terms": ["Synthetic"]})
    assert blocked["blocked"] and blocked["access"] == "paid" and blocked["reason"] == "paid_source:pacer"
    _stub(monkeypatch, lambda request: httpx.Response(200, content=b"%PDF-1.4 synthetic"))
    receipt = source_adapters.capture(repo, researcher, "glo", "https://cdn.glo.texas.gov/synthetic/1.pdf")
    artifact = repo.operation_artifact(receipt["artifact_id"])
    assert artifact["kind"] == "source" and artifact["task_id"] == researcher["id"]
    assert artifact["metadata"]["public_document"] is True
    with pytest.raises(ValueError, match="capture_locator_outside_approved_source"):
        source_adapters.capture(repo, researcher, "glo", "https://example.com/1.pdf")


def test_research_every_reachable_source_then_declare_the_gap_and_queue_only_access(
        operation_case, tmp_path, monkeypatch):
    repo, _, _ = operation_case
    unit, artifact = _case(repo, tmp_path, "CASE-S4")
    uid = unit["id"]
    lot = _lot(repo, [unit], sources=["local", "glo", "terrell_cad", "countyrecords", "pacer"])
    monkeypatch.setattr(source_adapters, "cad_view", lambda case, request: (_ for _ in ()).throw(
        source_adapters.SourceUnavailable("network_unreachable:terrell_cad:ConnectTimeout")))
    session = repo.abrir_sessao(uid, "synthetic", "synthetic-model")
    cid = repo.inserir_claim(
        unit_id=uid, claim_type="fact", entity="Synthetic", value={"tipo_resultado": "item_aberto"},
        source_sha256=artifact["sha256"], page="1", evidence="Synthetic open item.",
        confidence="media", materiality="media", session_id=session)
    lc = autonomy.open_lot_case(repo, uid)
    assert autonomy._research_or_gap(repo, lc, {cid: "item aberto"}) == "researching"
    research = {t["input_json"]["fonte"]: t for t in repo.tarefas(uid) if "-pesquisa-" in t["ref"]}
    assert sorted(research) == ["glo", "local"]
    queue = {e["detail"]["source"]: e for e in autonomy.open_exceptions(repo, uid)
             if e.get("lot_id") == lot["id"]}
    assert {s: e["kind"] for s, e in queue.items()} == {
        "terrell_cad": "source_access", "countyrecords": "source_access", "pacer": "paid_document"}
    assert queue["terrell_cad"]["detail"]["access"] == "network"
    assert "retry_source" in queue["countyrecords"]["options"]
    assert autonomy._research_or_gap(repo, lc, {cid: "item aberto"}) == "researching"
    assert len([t for t in repo.tarefas(uid) if "-pesquisa-" in t["ref"]]) == 2
    for t in research.values():
        repo.transicionar_tarefa(t["id"], (t["status"],), "aceita", "process:test", "Synthetic.")
    assert autonomy._research_or_gap(repo, lc, {cid: "item aberto"}) == "gaps_declared"
    assert repo.claim(cid)["status"] == "retirado"
    [gap] = autonomy.declared_gaps(repo, uid, lot["id"])
    for name in ("Acervo local", "Texas GLO", "Terrell CAD", "CountyRecords", "PACER"):
        assert name in gap["reason"]
    assert not [e for e in autonomy.open_exceptions(repo, uid)
                if e.get("lot_id") == lot["id"] and e["kind"] not in autonomy.LOT_QUEUE_KINDS]


def test_inside_a_lot_a_function_asks_only_for_the_four_kinds(operation_case, tmp_path):
    repo, _, _ = operation_case
    unit, _ = _case(repo, tmp_path, "CASE-S5")
    _lot(repo, [unit])
    coordinator = [t for t in repo.tarefas(unit["id"]) if t["role"] == "coordenador"][0]
    escalate = runtime.tools(repo, {**coordinator, "_operation_run_id": 1})["abrir_escalonamento"][1]
    with pytest.raises(ValueError, match="lot_queue_only_credencial_documento_pago_comunicacao_externa"):
        escalate("tract", "Synthetic tract question?", ["a", "b"])
    escalate("sme", "Synthetic SME consultation.", ["consultar"], tipo="comunicacao_externa")
    [entry] = [e for e in autonomy.open_exceptions(repo, unit["id"])
               if e["kind"] == "external_communication"]
    assert entry["options"] == ["acknowledge", "dismiss"]
    before = len(autonomy.open_exceptions(repo, unit["id"]))
    runtime.persist_plan(repo, coordinator, {"tarefas": [], "parada": {
        "declarada": True, "dependencias_externas": ["Synthetic external dependency"],
        "decisoes_do_operador": ["Synthetic operator decision"]}}, None)
    assert len(autonomy.open_exceptions(repo, unit["id"])) == before
