"""Flow layer — the workflow spine above the DD engine.

The engine modules under ``src/dd`` know HOW to compute WI/NRI, validate cells,
and package a submission. The flow layer knows WHAT happens next: it owns the
per-unit case file (state), the evidence ledger, the gather checklist, and a
single config. It sequences and feeds the engine; it never relaxes it.

Phase 1 (this package): backend spine only, no UI. See docs/WORKBENCH_BLUEPRINT.md.
"""
