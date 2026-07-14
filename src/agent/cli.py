"""Phase-1 conversational shell — a minimal CLI over the orchestrator.

Point it at a local folder, describe the assignment in one sentence, confirm
the resolved plan, and it runs the correct existing pipeline and returns the
artifact. On start it offers to resume any task left unfinished by a prior run.
The orchestrator core is UI-agnostic; a Streamlit chat page could wrap it later.

    python -m src.agent.cli --folder "C:/path/to/UNIT" --assignment "run DD for BOWEN A UNIT"
    python -m src.agent.cli            # interactive
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:  # load .env so pipeline tools that call the LLM find ANTHROPIC_API_KEY
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

from src.agent.orchestrator import Orchestrator
from src.agent.workspace import WorkspaceStore


def _echo(icon: str, message: str) -> None:
    mark = {"ok": "[ok]", "working": "[..]", "warn": "[!]", "err": "[x]"}.get(icon, "[.]")
    print(f"  {mark} {message}".encode("ascii", "replace").decode("ascii"))


def _run_one(orch: Orchestrator, workspace_id: int, folder: str, assignment: str, assume_yes: bool) -> None:
    plan = orch.plan(workspace_id, folder, assignment)
    print(plan.describe())
    if plan.needs_confirmation and plan.tool_name is None:
        print("  -> No pipeline chosen; nothing run. Refine the folder or assignment.")
        return
    if not assume_yes:
        ans = input("Proceed? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("  -> Held (task saved as pending; resumable later).")
            return
    task = orch.run_task(plan.task_id, progress_sink=_echo)
    print(f"Task #{task.id}: {task.status.upper()}")
    for a in orch.artifacts_for(task.id):
        print(f"  artifact: {a}")
    if task.error:
        print(f"  error: {task.error}")


def main() -> int:
    ap = argparse.ArgumentParser(description="PLM conversational shell (Phase 1)")
    ap.add_argument("--db", default="data/agent/agent.db")
    ap.add_argument("--folder", help="local unit/project folder")
    ap.add_argument("--assignment", help="one-sentence assignment")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    store = WorkspaceStore(args.db)
    orch = Orchestrator(store)

    pending = orch.resumable()
    if pending:
        print(f"{len(pending)} resumable task(s) from a previous session:")
        for t in pending:
            print(f"  #{t.id} [{t.status}] {t.tool_name} — {t.params.get('folder_path', '')}")
        if input("Resume them now? [y/N] ").strip().lower() in ("y", "yes"):
            for t in pending:
                print(f"Resuming task #{t.id} …")
                done = orch.resume_task(t.id, progress_sink=_echo)
                print(f"  -> {done.status.upper()}")
                for a in orch.artifacts_for(t.id):
                    print(f"     artifact: {a}")

    if args.folder and args.assignment:
        ws = orch.start_workspace(args.folder)
        _run_one(orch, ws, args.folder, args.assignment, args.yes)
        store.close()
        return 0

    print("Interactive shell. Blank folder to quit.")
    while True:
        folder = input("\nFolder> ").strip().strip('"')
        if not folder:
            break
        if not Path(folder).exists():
            print("  (folder not found)")
            continue
        assignment = input("Assignment> ").strip()
        ws = orch.start_workspace(folder)
        _run_one(orch, ws, folder, assignment, args.yes)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
