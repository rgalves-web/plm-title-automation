"""The conversational orchestrator (Phase 1).

Turns a local folder path + a one-sentence assignment into a persisted task,
selects the correct existing pipeline via the deterministic router + tool
registry, runs it behind a confirmation gate, records artifacts, and keeps the
conversation resumable across restarts. It owns no pipeline logic and no
interest math — it only routes, persists, and invokes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.agent.progress import ProgressLog
from src.agent.registry import ToolRegistry, default_registry
from src.agent.router import Route, route
from src.agent.workspace import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    Task,
    WorkspaceStore,
)


@dataclass
class Plan:
    """What the agent proposes to do; shown to the user before it runs."""
    workspace_id: int
    task_id: int
    route: Route
    tool_name: str | None
    params: dict[str, Any]

    @property
    def needs_confirmation(self) -> bool:
        return self.route.needs_confirmation or self.tool_name is None

    def describe(self) -> str:
        r = self.route
        if self.tool_name is None:
            return f"Could not choose a pipeline: {r.reason}"
        return (
            f"Plan: run '{self.tool_name}'"
            + (f" for unit '{r.unit_name}'" if r.unit_name else "")
            + f".\n  Task: {r.task}\n  Why: {r.reason}"
        )


class Orchestrator:
    def __init__(
        self,
        store: WorkspaceStore,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.store = store
        self.registry = registry or default_registry()

    # -- conversation entry ------------------------------------------------
    def start_workspace(self, folder_path: str | Path, name: str | None = None) -> int:
        folder = Path(folder_path)
        return self.store.create_workspace(name or folder.name, folder)

    def plan(self, workspace_id: int, folder_path: str | Path, instruction: str) -> Plan:
        """Route the assignment and create a PENDING task. No pipeline runs yet."""
        self.store.add_message(workspace_id, "user", f"[{folder_path}] {instruction}")
        r = route(folder_path, instruction)
        params: dict[str, Any] = {
            "folder_path": str(folder_path),
            "instructions_text": instruction,
        }
        if r.unit_name:
            params["unit_name"] = r.unit_name
        tool_name = r.tool_name if (r.tool_name and self.registry.has(r.tool_name)) else None
        task_id = self.store.create_task(workspace_id, tool_name or "unrouted", params)
        self.store.add_message(
            workspace_id, "agent",
            f"Routed task #{task_id}: {tool_name or 'UNROUTED'} — {r.reason}",
        )
        return Plan(workspace_id, task_id, r, tool_name, params)

    # -- execution (behind the confirm gate) -------------------------------
    def run_task(
        self,
        task_id: int,
        progress_sink: Callable[[str, str], None] | None = None,
    ) -> Task:
        """Invoke the task's tool. Records RUNNING before invoking (so a crash
        leaves a resumable RUNNING row), then DONE/FAILED. Never raises out of a
        tool failure — the shell stays alive and the task stays resumable."""
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(f"No such task: {task_id}")
        if task.tool_name == "unrouted" or not self.registry.has(task.tool_name):
            self.store.update_task(task_id, STATUS_FAILED, error="No pipeline selected for this task.")
            return self.store.get_task(task_id)

        self.store.update_task(task_id, STATUS_RUNNING)
        progress = ProgressLog(sink=progress_sink)
        tool = self.registry.get(task.tool_name)
        try:
            result = tool.run(task.params, progress)
        except Exception as exc:  # tool crashed hard — record, don't propagate
            self.store.update_task(task_id, STATUS_FAILED, error=f"{type(exc).__name__}: {exc}")
            self.store.add_message(task.workspace_id, "agent", f"Task #{task_id} failed: {exc}")
            return self.store.get_task(task_id)

        status = STATUS_DONE if result.get("status") == "done" else STATUS_FAILED
        self.store.update_task(task_id, status, result=result, error=result.get("error"))
        for path in result.get("artifacts", []) or []:
            self.store.add_artifact(task_id, task.workspace_id, kind="output", path=path)
        self.store.add_message(
            task.workspace_id, "agent",
            f"Task #{task_id} {status}: {result.get('summary', '')}"
            + (f" | artifact: {result['artifacts'][0]}" if result.get("artifacts") else ""),
        )
        return self.store.get_task(task_id)

    # -- resumption --------------------------------------------------------
    def resumable(self, workspace_id: int | None = None) -> list[Task]:
        return self.store.resumable_tasks(workspace_id)

    def resume_task(
        self, task_id: int, progress_sink: Callable[[str, str], None] | None = None
    ) -> Task:
        """Re-run a task that was left pending / running / failed."""
        return self.run_task(task_id, progress_sink=progress_sink)

    def artifacts_for(self, task_id: int) -> list[str]:
        return [a.path for a in self.store.list_artifacts(task_id=task_id)]
