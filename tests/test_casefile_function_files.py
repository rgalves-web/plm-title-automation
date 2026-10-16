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


# --- issue 02: input files before every terminal call ------------------------

def _terminal(repo, unit):
    case = repo.operation_case(unit["id"])
    repo.operation_update(unit["id"], profile={**case["profile"],
                                               "execution_backend": "terminal"})


class _CheckedTerminal(ClientRoteirizado):
    """Scripted terminal that proves, at the moment the process would start,
    that this call's input file is already written."""

    def __init__(self, repo, steps):
        super().__init__(steps)
        self.repo = repo
        self.seen = []

    def create(self, **kwargs):
        calls = self.repo.conn.execute(
            "SELECT * FROM operation_terminal_calls ORDER BY id").fetchall()
        current = calls[-1]
        assert current["input_sha256"] and current["input_file_id"]
        self.seen.append(current["ordinal"])
        result = super().create(**kwargs)
        result.terminal_receipt = {"billing_mode": "subscription",
                                   "api_charge_usd": 0,
                                   "subscription_charge_usd": None}
        return result


def test_every_terminal_call_has_one_input_file_written_first(operation_case):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _terminal(repo, unit)
    item = task(repo, unit)
    client = _CheckedTerminal(repo, [
        [Use("entregar_saida", {"saida": BAD_RESEARCH})],
        [Use("entregar_saida", {"saida": RESEARCH})]])
    result = worker.executar_uma(repo, unit["id"], "terminal-fixture",
                                 teto=50, operation=True, client=client)
    assert result["erros"] == [] and client.seen == [1, 2]
    inputs = repo.function_files(run_id=result["run_id"], direction="input")
    assert [f["ordinal"] for f in inputs] == [1, 2]
    calls = repo.conn.execute(
        "SELECT * FROM operation_terminal_calls ORDER BY ordinal").fetchall()
    assert [c["input_sha256"] for c in calls] == [f["sha256"] for f in inputs]
    run = repo.run(result["run_id"])
    assert run["input_sha256"] == inputs[-1]["sha256"]       # on the task run
    stage = repo.estado_da_unit(unit["id"]).lower()
    assert inputs[0]["relative"] == (f"{stage}/pesquisador/{item['id']}/"
                                     f"input_run{run['id']}_call01.json")
    body = json.loads(case_file_store.read(unit["id"], inputs[0]["relative"])
                      .path.read_text("utf-8"))
    assert body["kind"] == "function_input"
    assert body["output_schema"] == "resultado_pesquisa"
    assert body["sent"]["stdin"] and body["sent"]["output_schema"]
    assert "publication" in body
    artifact = repo.operation_artifact(inputs[0]["artifact_id"])
    assert artifact["kind"] == "function_input"                # artifact index
    assert artifact["sha256"] == inputs[0]["sha256"]


def test_task_view_shows_the_input_file_and_hash(operation_case):
    from src.casefile import operations
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _terminal(repo, unit)
    task(repo, unit)
    result = worker.executar_uma(
        repo, unit["id"], "terminal-fixture", teto=50, operation=True,
        client=_CheckedTerminal(repo, [[Use("entregar_saida",
                                            {"saida": RESEARCH})]]))
    detail = operations.task_detail(repo, result["tarefa"]["id"])
    [call] = detail["terminal_calls"]
    [entry] = [f for f in detail["function_files"]
               if f["id"] == call["input_file_id"]]
    assert entry["direction"] == "input"
    assert call["input_sha256"] == entry["sha256"]
    assert any(a["id"] == entry["artifact_id"] for a in detail["artifacts"])


def test_call_whose_input_file_cannot_be_written_never_starts(operation_case,
                                                              monkeypatch):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _terminal(repo, unit)
    task(repo, unit)

    def refuse(*a, **k):
        raise case_file_store.CaseFileOutsideCase("synthetic refusal")

    monkeypatch.setattr(function_files, "write_input", refuse)

    class NeverCalled:
        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            pytest.fail("the process must not start without its input file")

    result = worker.executar_uma(repo, unit["id"], "terminal-fixture",
                                 teto=50, operation=True, client=NeverCalled())
    assert result["tarefa"]["status"] == "bloqueada"
    assert "terminal_input_file_not_written" in result["parada"]
    call = repo.conn.execute(
        "SELECT * FROM operation_terminal_calls").fetchone()
    assert call["status"] == "interrupted" and call["input_sha256"] is None
    assert "case_file_outside_case" in call["failure"]
    assert repo.run(result["run_id"])["usage_state"] == "not_called"
    escalation = [e for e in repo.escalonamentos(unit["id"], abertos=True)
                  if "terminal_input_file_not_written" in e["pergunta"]]
    assert escalation


@pytest.mark.parametrize("family", ["A", "B"])
def test_input_file_holds_exactly_what_the_process_receives(monkeypatch,
                                                            tmp_path, family):
    from src.infra import terminal
    from tests.test_casefile_terminal import events
    monkeypatch.setenv("PLM_OPERATION_ROOT", str(tmp_path))
    monkeypatch.setattr(terminal, "auth_status", lambda _: {"ok": True})
    monkeypatch.setattr(terminal, "executable", lambda _: "official-cli")
    seen = {}

    def process(args, *, stdin="", cwd=None, timeout=600):
        seen["stdin"] = stdin
        if family == "A":
            data = {"type": "result", "subtype": "success", "is_error": False,
                    "structured_output": {"text": "ok", "calls": []},
                    "usage": {"input_tokens": 3, "output_tokens": 2}}
            return 0, json.dumps(data), ""
        return 0, "\n".join(map(json.dumps, events("ok"))), ""

    monkeypatch.setattr(terminal, "run_process", process)
    kwargs = {"model": "terminal/claude/sonnet" if family == "A"
              else "terminal/codex/default",
              "system": "synthetic-system",
              "messages": [{"role": "user", "content": "synthetic data"}],
              "tools": []}
    sent = terminal.build_input(family, **kwargs)
    message = terminal.TerminalAdapter(family).create(max_tokens=50, **kwargs)
    assert seen["stdin"] == sent["stdin"]
    import hashlib
    assert message.terminal_receipt["input_sha256"] == \
        hashlib.sha256(sent["stdin"].encode("utf-8")).hexdigest()


# --- issue 04: the process receives only its own input file -------------------

SENTINEL = "producer-sentinel-7731"       # synthetic value, never on the page
BLIND_OUTPUT = {"valor": {"field": "independent reading"},
                "trecho": "Synthetic fixture only.", "evidencia_suficiente": True}


def _claim_under_review(repo, unit, tmp_path):
    """An examiner delivers one synthetic Claim through the terminal path;
    the blind extraction of that Claim is then queued."""
    artifact = source(repo, unit, tmp_path / "synthetic.pdf")
    task(repo, unit, "examinador", "claims", mode="obrigatoria")
    _terminal(repo, unit)
    claim = {"tipo": "fact", "entidade": "Synthetic field",
             "valor": {"tipo_resultado": "fato_documental", "field": SENTINEL},
             "documento": "sha256:" + artifact["sha256"], "pagina": "1",
             "trecho": "Synthetic fixture only.", "confianca": "alta",
             "materialidade": "baixa"}
    result = worker.executar_uma(
        repo, unit["id"], "terminal-fixture", teto=50, operation=True,
        client=_CheckedTerminal(repo, [[Use("entregar_saida",
                                            {"saida": {"claims": [claim]}})]]))
    assert result["erros"] == []
    [produced] = _outputs(repo, result["run_id"])
    blind = next(t for t in repo.tarefas(unit["id"])
                 if t["role"] == "verificador")
    return artifact, produced, blind


def _official_cli(monkeypatch, replies):
    """The real adapter, with only the process itself replaced: what it is
    given on stdin is recorded."""
    from src.infra import terminal
    from tests.test_casefile_terminal import events
    monkeypatch.setattr(terminal, "auth_status", lambda _: {"ok": True})
    monkeypatch.setattr(terminal, "executable", lambda _: "official-cli")
    stdins = []

    def process(args, *, stdin="", cwd=None, timeout=600):
        stdins.append(stdin)
        calls = replies[len(stdins) - 1]
        return 0, "\n".join(map(json.dumps, events(calls=calls))), ""

    monkeypatch.setattr(terminal, "run_process", process)
    return terminal.TerminalAdapter("B"), stdins


def _call(name, arguments):
    return {"name": name, "arguments": json.dumps(arguments)}


def test_producer_output_is_absent_from_the_verifier_input_and_prompt(
        operation_case, tmp_path, monkeypatch):
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    artifact, produced, blind = _claim_under_review(repo, unit, tmp_path)
    produced_bytes = case_file_store.read_bytes(unit["id"], produced["relative"])
    assert SENTINEL.encode() in produced_bytes        # the producer did say it
    page = {"documento": artifact["sha256"], "pagina": 1, "modo": "texto"}
    adapter, stdins = _official_cli(monkeypatch, [
        [_call("ler_pagina_confirmada", page)],
        [_call("entregar_saida", {"saida": BLIND_OUTPUT})]])
    result = worker.executar_uma(repo, unit["id"], "terminal-fixture",
                                 teto=50, operation=True, client=adapter)
    assert result["erros"] == [] and result["tarefa"]["id"] == blind["id"]
    inputs = repo.function_files(run_id=result["run_id"], direction="input")
    assert len(inputs) == len(stdins) == 2
    for row, stdin in zip(inputs, stdins):
        document = function_files.read_input(repo, row)
        assert stdin == document["sent"]["stdin"]       # the prompt IS the file
        raw = case_file_store.read_bytes(unit["id"], row["relative"])
        assert SENTINEL.encode() not in raw and SENTINEL not in stdin
        assert produced["sha256"].encode() not in raw
        assert produced["relative"].encode() not in raw
    # the second call carried the page the Verifier read, from the source
    assert "Synthetic fixture only" in stdins[1]


def test_scripted_client_receives_the_call_rebuilt_from_the_input_file(
        operation_case):
    from src.infra import terminal
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _terminal(repo, unit)
    task(repo, unit)
    client = _CheckedTerminal(repo, [[Use("entregar_saida",
                                          {"saida": RESEARCH})]])
    received = []
    original = client.create

    def record(**kwargs):
        received.append(kwargs)
        return original(**kwargs)

    client.create = record
    result = worker.executar_uma(repo, unit["id"], "terminal-fixture",
                                 teto=50, operation=True, client=client)
    [row] = repo.function_files(run_id=result["run_id"], direction="input")
    sent = function_files.read_input(repo, row)["sent"]
    [kwargs] = received
    assert {k: kwargs[k] for k in ("model", "system", "messages", "tools")} \
        == terminal.call_from_input(sent)
    rebuilt = terminal.build_input("A", **terminal.call_from_input(sent))
    assert rebuilt == sent                               # nothing lost or added


@pytest.mark.parametrize("leak", ["context", "tool"])
def test_verifier_call_that_breaks_quarantine_never_starts(
        operation_case, tmp_path, monkeypatch, leak):
    from src.casefile import runtime
    repo, unit, scope = operation_case
    approve(repo, unit, scope)
    _claim_under_review(repo, unit, tmp_path)
    if leak == "context":
        original = runtime.context
        monkeypatch.setattr(runtime, "context", lambda repo_, task_: (
            original(repo_, task_) + "\nfield: " + SENTINEL))
    else:
        # a tool the role card declares but the blind extraction must not get
        original_tools = runtime.tools
        monkeypatch.setattr(runtime, "tools", lambda repo_, task_: {
            **original_tools(repo_, task_),
            "registrar_verificacao": (runtime.tool(
                "registrar_verificacao", "Synthetic.", {}, []), lambda **_: {})})

    class NeverCalled:
        def __init__(self):
            self.messages = self

        def run_input(self, sent):
            pytest.fail("the process must not start when quarantine fails")

    result = worker.executar_uma(repo, unit["id"], "terminal-fixture",
                                 teto=50, operation=True, client=NeverCalled())
    assert result["tarefa"]["status"] == "bloqueada"
    assert "terminal_input_quarantine_violated" in result["parada"]
    call = repo.conn.execute(
        "SELECT * FROM operation_terminal_calls ORDER BY id DESC").fetchone()
    assert call["status"] == "interrupted" and call["input_sha256"]
    expected = ("arquivo_de_entrada_contem_resposta" if leak == "context"
                else "ferramenta_fora_da_quarentena")
    assert expected in call["failure"]
    # the refused input file stays as the evidence of what would have gone
    [row] = repo.function_files(run_id=result["run_id"], direction="input")
    assert SENTINEL.encode() in case_file_store.read_bytes(
        unit["id"], row["relative"]) or leak == "tool"


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
