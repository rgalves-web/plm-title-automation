"""Orchestrator: tool selection, invocation, artifact association, resumption,
failure recovery — all with a STUB tool so no real pipeline / API is touched."""
from __future__ import annotations

import pytest

from src.agent.orchestrator import Orchestrator
from src.agent.registry import Tool, ToolRegistry
from src.agent.workspace import STATUS_DONE, STATUS_FAILED, WorkspaceStore


def _registry(run_fn, name="dd_pipeline"):
    reg = ToolRegistry()
    reg.register(Tool(name=name, description="stub", run=run_fn))
    return reg


def _dd_folder(tmp_path):
    d = tmp_path / "BOWEN A UNIT"
    (d).mkdir()
    (d / "DDR - Template.xlsx").write_bytes(b"x")
    (d / "T0141486.pdf").write_bytes(b"x")
    (d / "Lease to Well XREF.xlsx").write_bytes(b"x")
    return d


def test_plan_selects_dd_tool_and_persists_task(tmp_path):
    store = WorkspaceStore(tmp_path / "a.db")
    calls = {}

    def stub(params, progress):
        calls["params"] = params
        return {"status": "done", "summary": "made DDR", "artifacts": [str(tmp_path / "DDR.xlsx")]}

    orch = Orchestrator(store, registry=_registry(stub))
    d = _dd_folder(tmp_path)
    ws = orch.start_workspace(d)
    plan = orch.plan(ws, d, "run DD for BOWEN A UNIT")

    assert plan.tool_name == "dd_pipeline"
    assert not plan.needs_confirmation
    assert store.get_task(plan.task_id).status == "pending"  # not run until confirmed


def test_run_task_invokes_tool_and_records_artifact(tmp_path):
    store = WorkspaceStore(tmp_path / "a.db")
    art = str(tmp_path / "DDR.xlsx")

    def stub(params, progress):
        progress("ok", "parsed TO")
        return {"status": "done", "summary": "made DDR", "artifacts": [art]}

    orch = Orchestrator(store, registry=_registry(stub))
    d = _dd_folder(tmp_path)
    ws = orch.start_workspace(d)
    plan = orch.plan(ws, d, "run DD for BOWEN A UNIT")
    task = orch.run_task(plan.task_id)

    assert task.status == STATUS_DONE
    assert orch.artifacts_for(plan.task_id) == [art]


def test_folder_without_signals_is_unrouted_and_not_run(tmp_path):
    store = WorkspaceStore(tmp_path / "a.db")
    orch = Orchestrator(store, registry=_registry(lambda p, pr: {"status": "done"}))
    empty = tmp_path / "empty"; empty.mkdir()
    ws = orch.start_workspace(empty)
    plan = orch.plan(ws, empty, "do something")
    assert plan.tool_name is None
    task = orch.run_task(plan.task_id)  # must not raise
    assert task.status == STATUS_FAILED


def test_failure_recovery_tool_crash_is_recorded_not_raised(tmp_path):
    store = WorkspaceStore(tmp_path / "a.db")

    def boom(params, progress):
        raise RuntimeError("pipeline exploded")

    orch = Orchestrator(store, registry=_registry(boom))
    d = _dd_folder(tmp_path)
    ws = orch.start_workspace(d)
    plan = orch.plan(ws, d, "run DD")
    task = orch.run_task(plan.task_id)  # does not raise
    assert task.status == STATUS_FAILED
    assert "pipeline exploded" in task.error


def test_task_resumption_after_restart_reruns_and_succeeds(tmp_path):
    db = tmp_path / "a.db"
    d = _dd_folder(tmp_path)
    attempts = {"n": 0}

    def flaky(params, progress):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return {"status": "done", "summary": "ok", "artifacts": [str(tmp_path / "DDR.xlsx")]}

    # Session 1: plan + fail.
    store = WorkspaceStore(db)
    orch = Orchestrator(store, registry=_registry(flaky))
    ws = orch.start_workspace(d)
    plan = orch.plan(ws, d, "run DD")
    assert orch.run_task(plan.task_id).status == STATUS_FAILED
    store.close()

    # Session 2 (fresh store = "restart"): the failed task is resumable and succeeds.
    store2 = WorkspaceStore(db)
    orch2 = Orchestrator(store2, registry=_registry(flaky))
    resumable = orch2.resumable()
    assert plan.task_id in {t.id for t in resumable}
    done = orch2.resume_task(plan.task_id)
    assert done.status == STATUS_DONE
    assert orch2.artifacts_for(plan.task_id)


def test_registry_selection_and_missing_tool(tmp_path):
    reg = ToolRegistry()
    reg.register(Tool("dd_pipeline", "d", lambda p, pr: {"status": "done"}))
    assert reg.has("dd_pipeline")
    assert reg.names() == ["dd_pipeline"]
    with pytest.raises(KeyError):
        reg.get("mor_pipeline")
