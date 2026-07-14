"""Workspace persistence + resumption (Phase-1 conversational shell)."""
from __future__ import annotations

from src.agent.workspace import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    WorkspaceStore,
)


def test_workspace_message_task_artifact_roundtrip(tmp_path):
    db = tmp_path / "a.db"
    store = WorkspaceStore(db)
    ws = store.create_workspace("BOWEN A UNIT", tmp_path / "folder")
    store.add_message(ws, "user", "run DD")
    tid = store.create_task(ws, "dd_pipeline", {"folder_path": str(tmp_path), "unit_name": "BOWEN A UNIT"})
    store.update_task(tid, STATUS_DONE, result={"summary": "ok"})
    store.add_artifact(tid, ws, "output", tmp_path / "DDR.xlsx")
    store.close()

    # Reopen — everything survived the "restart".
    store2 = WorkspaceStore(db)
    assert store2.get_workspace(ws)["name"] == "BOWEN A UNIT"
    assert [m.content for m in store2.list_messages(ws)] == ["run DD"]
    task = store2.get_task(tid)
    assert task.status == STATUS_DONE
    assert task.params["unit_name"] == "BOWEN A UNIT"
    arts = store2.list_artifacts(task_id=tid)
    assert len(arts) == 1 and arts[0].path.endswith("DDR.xlsx")


def test_resumable_tasks_filters_by_status(tmp_path):
    store = WorkspaceStore(tmp_path / "a.db")
    ws = store.create_workspace("w")
    t_done = store.create_task(ws, "dd_pipeline", {})
    store.update_task(t_done, STATUS_DONE)
    t_pending = store.create_task(ws, "dd_pipeline", {})
    t_running = store.create_task(ws, "dd_pipeline", {})
    store.update_task(t_running, STATUS_RUNNING)
    t_failed = store.create_task(ws, "dd_pipeline", {})
    store.update_task(t_failed, STATUS_FAILED)

    ids = {t.id for t in store.resumable_tasks(ws)}
    assert ids == {t_pending, t_running, t_failed}
    assert t_done not in ids
