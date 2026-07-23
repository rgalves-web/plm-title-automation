"""Service layer — everything the web routes call, expressed over the flow spine.

Holds no HTTP concerns: each method takes plain data and returns plain dicts, so
it is unit-testable without a server. The DD engine (validators, source-truth,
packager) is called through the flow layer and never modified.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.flow.checklist_builder import build_checklist
from src.flow.config import Config
from src.flow.evidence_ledger import (
    KIND_CONTRACT,
    KIND_LEASE,
    KIND_TITLE_OPINION,
    EvidenceLedger,
)
from src.flow.review import review_items_from_report, review_summary, trace_for_cell
from src.flow.runner import build_allowlist, revalidate_from_state
from src.flow.unit_state import (
    STAGES,
    UnitState,
    load_state,
    save_state,
    state_dir,
    state_exists,
)
from src.webapp.jobs import Job, JobRegistry

_TO_NUMBER_RE = re.compile(r"\bT0?\d{5,6}\b")


class WorkbenchService:
    def __init__(self, config: Config, jobs: JobRegistry | None = None) -> None:
        self.config = config
        self.jobs = jobs or JobRegistry()

    # ---- board -----------------------------------------------------------
    def list_units(self) -> list[dict[str, Any]]:
        units_root = self.config.units_path()
        cards: list[dict[str, Any]] = []
        if units_root.exists():
            for d in sorted(units_root.iterdir()):
                if (d / "state.yaml").exists():
                    cards.append(self._card(load_state(d.name, units_root)))
        return cards

    def openable_units(self) -> list[str]:
        """Units that have a manifest but no case file yet — candidates for OPEN."""
        root = Path(self.config.manifests_dir)
        have = {c["unit_name"] for c in self.list_units()}
        out = []
        if root.exists():
            for d in sorted(root.iterdir()):
                if (d / "manifest.yaml").exists() and d.name not in have:
                    out.append(d.name)
        return out

    def _card(self, st: UnitState) -> dict[str, Any]:
        gr = st.gate_results or {}
        structural = gr.get("structural", {})
        truth = gr.get("source_truth", {})
        return {
            "unit_name": st.unit_name,
            "stage": st.stage,
            "stage_index": STAGES.index(st.stage) if st.stage in STAGES else 0,
            "geo": self._geo(st),
            "next_step": self._next_step(st),
            "gates": {
                "fail": structural.get("fail"),
                "mismatch": truth.get("mismatch"),
                "structural_summary": structural.get("summary", ""),
            },
        }

    def _geo(self, st: UnitState) -> str:
        m = st.manifest_snapshot or {}
        bits = []
        if st.unit_dpu_contract:
            bits.append(f"DPU {st.unit_dpu_contract}")
        if m.get("dsu_description"):
            bits.append(str(m["dsu_description"])[:60])
        return " · ".join(bits)

    def _next_step(self, st: UnitState) -> str:
        return {
            "OPEN": "Build the evidence checklist.",
            "GATHER": "Fetch the blocking checklist items, then drop them in.",
            "DROP": "Confirm the dropped evidence, then run the gates.",
            "RUN": "Run the structural and source-truth gates.",
            "REVIEW": "Record a verdict on each cell that needs eyes.",
            "SHIP": "Package assembled — ready to submit.",
        }.get(st.stage, "")

    # ---- open / get ------------------------------------------------------
    def open_unit(self, unit_name: str) -> dict[str, Any]:
        manifest = self._load_manifest(unit_name)
        unit_folder = self._unit_folder(unit_name)
        ddr_path = self._find_ddr(unit_folder)
        st = UnitState(
            unit_name=unit_name, stage="OPEN",
            manifest_snapshot=manifest,
            checklist=[i.to_dict() for i in build_checklist(manifest)],
            ledger=EvidenceLedger(),
            unit_dpu_contract=self._dpu_contract(manifest),
            ddr_path=str(ddr_path) if ddr_path else None,
        )
        save_state(st, self.config.units_dir)
        return self.get_unit(unit_name)

    def get_unit(self, unit_name: str) -> dict[str, Any]:
        st = load_state(unit_name, self.config.units_dir)
        allow = st.derive_allowlist()
        gr = st.gate_results or {}
        return {
            "unit_name": st.unit_name,
            "stage": st.stage,
            "stages": list(STAGES),
            "stage_index": STAGES.index(st.stage) if st.stage in STAGES else 0,
            "facts": self._facts(st),
            "checklist": st.checklist,
            "evidence": [e.to_dict() for e in st.ledger.entries],
            "derived_allowlist": {
                "title_opinions": sorted(allow["title_opinions"]),
                "contracts": sorted(allow["contracts"]),
                "leases": len(allow["leases"]),
                "identity_tokens": sorted(allow["identity_tokens"]),
            },
            "gate_results": gr,
            "review_queue": gr.get("review_queue", []),
            "review_summary": gr.get("review_summary", {}),
            "verdicts": st.verdicts,
            "packaging_summary": st.packaging_summary,
            "ddr_path": st.ddr_path,
            "has_ddr": bool(st.ddr_path and Path(st.ddr_path).exists()),
        }

    def _facts(self, st: UnitState) -> list[dict[str, str]]:
        m = st.manifest_snapshot or {}
        wells = m.get("wells") or []
        well = wells[0] if wells else {}
        ri = m.get("represented_interest") or {}
        return [
            {"label": "Well", "value": str(well.get("well_name") or "—")
             + (f" · API {well['well_api']}" if well.get("well_api") else "")},
            {"label": "Target WI / NRI",
             "value": f"{well.get('current_wi','—')} / {well.get('current_nri','—')}"},
            {"label": "Unit designation",
             "value": (st.unit_dpu_contract or "—")},
            {"label": "Leases", "value": str(len(m.get("leases") or []))},
        ]

    # ---- stage -----------------------------------------------------------
    def set_stage(self, unit_name: str, to_stage: str, note: str = "") -> dict[str, Any]:
        st = load_state(unit_name, self.config.units_dir)
        cur = STAGES.index(st.stage) if st.stage in STAGES else 0
        tgt = STAGES.index(to_stage)
        if tgt < cur:
            st.regress(to_stage, note or "manual")
        else:
            st.advance(to_stage, note)
        save_state(st, self.config.units_dir)
        return self.get_unit(unit_name)

    # ---- drop: seed evidence from the record ----------------------------
    def seed_from_record(self, unit_name: str) -> dict[str, Any]:
        """Confirm the unit's expected evidence into the ledger from what the
        record already declares: the title-opinion chain named in the finished
        DDR, and the contracts/leases in the manifest. This is the Phase-2 stand-in
        for the Phase-3 content-first classifier; the analyst confirms with a click.
        """
        st = load_state(unit_name, self.config.units_dir)
        led = st.ledger
        seen = {(e.kind, e.identifier) for e in led.entries}

        def add(kind: str, identifier: str, file: str, quote: str = "") -> None:
            if identifier and (kind, identifier) not in seen:
                led.record(file, kind, identifier, evidence_quote=quote)
                seen.add((kind, identifier))

        # Title opinions: the chain the deliverable declares (DDR XREF numbers).
        for t in sorted(self._declared_title_opinions(st)):
            add(KIND_TITLE_OPINION, t, t, "declared in the DDR (PLM Title Review / XREF)")
        m = st.manifest_snapshot or {}
        for c in m.get("reference_contracts", []):
            add(KIND_CONTRACT, str(c.get("file_number") or ""), str(c.get("file_number") or ""))
        for lease in m.get("leases", []):
            add(KIND_LEASE, str(lease.get("lease_no") or ""), str(lease.get("lease_no") or ""))

        # Close matching checklist rows.
        confirmed_ids = {e.identifier for e in led.entries}
        for item in st.checklist:
            ref = item.get("id", "").split("_", 1)[-1]
            if any(ref and ref in cid for cid in confirmed_ids if cid):
                item["status"] = "in"
        if st.stage in ("OPEN", "GATHER"):
            st.advance("DROP", "evidence confirmed from the record")
        save_state(st, self.config.units_dir)
        return self.get_unit(unit_name)

    def add_evidence(self, unit_name: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        from src.flow.evidence_ledger import EvidenceEntry
        st = load_state(unit_name, self.config.units_dir)
        for e in entries:
            st.ledger.add(EvidenceEntry.from_dict(e))
        save_state(st, self.config.units_dir)
        return self.get_unit(unit_name)

    def _declared_title_opinions(self, st: UnitState) -> set[str]:
        if not (st.ddr_path and Path(st.ddr_path).exists()):
            return set()
        import openpyxl
        wb = openpyxl.load_workbook(st.ddr_path, data_only=True, read_only=True)
        found: set[str] = set()
        try:
            for name in wb.sheetnames:
                for row in wb[name].iter_rows(values_only=True):
                    for c in row:
                        if c is not None:
                            found.update(_TO_NUMBER_RE.findall(str(c)))
        finally:
            wb.close()
        return found

    # ---- run: gates ------------------------------------------------------
    def run_structural(self, unit_name: str) -> dict[str, Any]:
        st = load_state(unit_name, self.config.units_dir)
        if st.stage in ("OPEN", "GATHER", "DROP"):
            st.advance("RUN", "gates started")
            save_state(st, self.config.units_dir)
        st = load_state(unit_name, self.config.units_dir)
        revalidate_from_state(st, self.config, run_source_truth=False, persist=True,
                              units_dir=self.config.units_dir)
        return self.get_unit(unit_name)

    def start_source_truth(self, unit_name: str) -> dict[str, Any]:
        """Kick off the slow source-truth gate as a background job. The route
        returns immediately; the UI polls run_status."""
        def work(job: Job) -> dict[str, Any]:
            job.progress = "re-reading cited documents (OCR)…"
            st = load_state(unit_name, self.config.units_dir)
            report = revalidate_from_state(
                st, self.config, run_source_truth=True, persist=False,
                units_dir=self.config.units_dir)
            queue = review_items_from_report(report)
            traces = {f"{it['tab']}!{it['cell']}": trace_for_cell(
                report, it["tab"], it["cell"], st.verdicts) for it in queue}
            st.gate_results["review_queue"] = queue
            st.gate_results["review_summary"] = review_summary(report)
            st.gate_results["traces"] = traces
            save_state(st, self.config.units_dir)
            return {
                "source_truth": st.gate_results.get("source_truth", {}),
                "review_summary": st.gate_results.get("review_summary", {}),
                "review_count": len(queue),
            }

        job = self.jobs.submit("source_truth", unit_name, work)
        return {"job_id": job.id, "status": job.status}

    def run_status(self, unit_name: str) -> dict[str, Any]:
        job = self.jobs.latest_for(unit_name, "source_truth")
        return job.to_dict() if job else {"status": "none"}

    # ---- review ----------------------------------------------------------
    def review(self, unit_name: str) -> dict[str, Any]:
        st = load_state(unit_name, self.config.units_dir)
        gr = st.gate_results or {}
        return {
            "queue": gr.get("review_queue", []),
            "summary": gr.get("review_summary", {}),
            "verdicts": st.verdicts,
        }

    def trace(self, unit_name: str, tab: str, cell: str) -> dict[str, Any] | None:
        st = load_state(unit_name, self.config.units_dir)
        traces = (st.gate_results or {}).get("traces", {})
        tr = traces.get(f"{tab}!{cell}")
        if tr is not None:
            tr = dict(tr)
            tr["recorded_verdict"] = st.verdicts.get(f"{tab}!{cell}")
        return tr

    def record_verdict(self, unit_name: str, tab: str, cell: str,
                       verdict: str, reason: str = "") -> dict[str, Any]:
        from datetime import datetime, timezone
        st = load_state(unit_name, self.config.units_dir)
        st.verdicts[f"{tab}!{cell}"] = {
            "verdict": verdict, "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        # A queue with every item verdicted lets the UI offer SHIP.
        queue = (st.gate_results or {}).get("review_queue", [])
        need = {f"{it['tab']}!{it['cell']}" for it in queue
                if it.get("label") in ("NEEDS EYES", "MISMATCH")}
        if need and need <= set(st.verdicts):
            if st.stage == "REVIEW":
                pass  # ready to ship; UI advances explicitly
        save_state(st, self.config.units_dir)
        return {"verdicts": st.verdicts}

    # ---- ship ------------------------------------------------------------
    def ship(self, unit_name: str) -> dict[str, Any]:
        from src.dd.submission_packager import SUBFOLDERS, package_unit_submission
        st = load_state(unit_name, self.config.units_dir)
        unit_folder = self._unit_folder(unit_name)
        if unit_folder is None or not (unit_folder / "FILES").exists():
            raise FileNotFoundError(
                f"no FILES folder for {unit_name}; set project_root in config")
        root, plan = package_unit_submission(
            unit_folder, unit_name=unit_name, unit_dpu_contract=st.unit_dpu_contract)
        tree = [{"folder": sub, "count": len(plan.for_subfolder(sub))} for sub in SUBFOLDERS]
        decisions = list(plan.decisions)
        missing = [{"subfolder": m.subfolder, "what": m.what, "reason": m.reason}
                   for m in plan.missing]
        summary = {
            "root": str(root.resolve()), "tree": tree,
            "placed": len(plan.placed), "missing": missing,
            "decisions_count": len(decisions),
        }
        st.packaging_summary = summary
        if st.stage != "SHIP":
            st.advance("SHIP", "package assembled")
        save_state(st, self.config.units_dir)
        return {**summary, "decisions": decisions}

    # ---- helpers ---------------------------------------------------------
    def _load_manifest(self, unit_name: str) -> dict[str, Any]:
        import yaml
        p = Path(self.config.manifests_dir) / unit_name / "manifest.yaml"
        if not p.exists():
            raise FileNotFoundError(f"no manifest for {unit_name} at {p}")
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    def _unit_folder(self, unit_name: str) -> Path | None:
        if self.config.project_root:
            folder = Path(self.config.project_root) / unit_name
            if folder.exists():
                return folder
        # Fall back to the folder of a recorded DDR path.
        if state_exists(unit_name, self.config.units_dir):
            st = load_state(unit_name, self.config.units_dir)
            if st.ddr_path:
                return Path(st.ddr_path).parent
        return None

    def _find_ddr(self, unit_folder: Path | None):
        if unit_folder is None:
            return None
        from src.dd.submission_packager import _find_latest_ddr
        return _find_latest_ddr(unit_folder)

    def _dpu_contract(self, manifest: dict[str, Any]) -> str | None:
        for c in manifest.get("reference_contracts", []):
            if re.search(r"pooled unit|designation", str(c.get("record_type") or ""), re.I):
                return str(c.get("file_number"))
        return None
