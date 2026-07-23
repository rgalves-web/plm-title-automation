"""Minorh Title Workbench — local FastAPI server over the flow spine (Phase 2).

`minorh serve` starts a local server and opens the browser. The UI is the
prototype in docs/minorh-workbench-prototype.html made real: it drives the flow
layer (unit_state / evidence_ledger / checklist_builder / runner) and the DD
engine underneath, never modifying the engine.
"""
