"""PR-10 — the tabs that were never written, from proved data only.

One rule governs everything here: only what the round proves with a citation is
written; everything else stays blank with a vocabulary reason AND an owner (a
brief item or a verdict). Correct-and-fewer beats plausible-and-wrong.
"""
from __future__ import annotations

import re
from typing import Any

from src.knowledge.kit_builder import CellWrite

EXHIBIT_C_CITE = 'unit designation, Exhibit "C" p.6 (tract schedule)'


def _label_row(ws, label: str, max_row: int = 40) -> int | None:
    for row in ws.iter_rows(min_row=1, max_row=max_row):
        for cell in row:
            text = " ".join(str(cell.value or "").split()).lower()
            if text.startswith(label.lower()):
                return cell.row
    return None


def write_summary(wb, writes: list[CellWrite], *, engagement: dict[str, Any],
                  unit_authority: str, defects_text: str, defects_cite: str,
                  curative_text: str, curative_cite: str) -> None:
    """Summary: engagement facts with their sources; defects and curative
    DERIVED from the gap-hunter. The supervisor's literal instruction was
    "note all this in your ddr" — this is the cell he meant."""
    ws = wb["Summary"]
    fields = engagement.get("fields", {})
    label_to_field = {"Client:": "client", "Acquisition:": "acquisition",
                      "Operator(s):": "operator", "State:": "state",
                      "Counties:": "counties"}
    for label, key in label_to_field.items():
        row = _label_row(ws, label)
        if row is None:
            continue
        spec = fields.get(key) or {}
        value = spec.get("value") if isinstance(spec, dict) else None
        if value:
            cite = " ".join(str(spec.get("source", "")).split())[:200]
            if key in ("state", "counties", "operator"):
                cite += f" | this unit: {unit_authority}"
            ws.cell(row=row, column=2).value = value
            writes.append(CellWrite("Summary", row, "B", f"summary_{key}",
                                    value, cite))
        else:
            writes.append(CellWrite("Summary", row, "B", f"summary_{key}", "",
                                    "", "doc_nao_localizado"))
    row = _label_row(ws, "DSU STR:")
    if row is not None:
        writes.append(CellWrite("Summary", row, "B", "summary_dsu_str", "",
                                "", "doc_nao_localizado"))

    for label, text, cite, term in (
            ("Potential Defect(s):", defects_text, defects_cite,
             "summary_potential_defects"),
            ("Outstanding Curative Requirements:", curative_text,
             curative_cite, "summary_outstanding_curative")):
        row = _label_row(ws, label)
        if row is None:
            continue
        if text:
            ws.cell(row=row, column=2).value = text
            writes.append(CellWrite("Summary", row, "B", term, text, cite))
        else:
            writes.append(CellWrite("Summary", row, "B", term, "",
                                    "", "doc_nao_localizado"))


def write_worksheet(wb, writes: list[CellWrite], *, schedules: dict[str, Any],
                    tract_map: dict[str, dict[str, Any]],
                    exhibit_c: dict[str, dict[str, str]],
                    dispositions: list[dict[str, Any]],
                    to_schedule_by_lease: dict[str, dict[str, Any]],
                    county: str) -> None:
    """Ownership - Worksheet at the deliverable's own grain: one row per lease.

    PLM's Phase I instruction asks for columns A (Unit Tract No.) through Q
    (Tract Depth: To) — the lease's identity. Every value comes from the
    round's dispositions (already cited per term) or from the opinions'
    arithmetic, aggregated exactly in Fraction. A lease whose tract we have not
    proved carries a blank tract cell with its reason, not a guess."""
    from src.knowledge.unit_ownership import lease_interests

    ws = wb["Ownership - Worksheet"]
    # lease number in the opinion -> its aggregated MI, per opinion
    agg: dict[str, dict[tuple[str, str], Any]] = {
        tag: lease_interests(sched) for tag, sched in schedules.items()}

    row_no = 8
    for d in sorted(dispositions, key=lambda x: x["lease"]):
        if d["status"] == "outside_perimeter":
            continue
        lease = d["lease"]
        proved = d.get("proved_terms") or {}
        sched_entry = to_schedule_by_lease.get(lease) or {}
        opinion_lease_no = str(sched_entry.get("lease_no") or "")
        opinion_tag = sched_entry.get("tag", "")
        opinion_tract = sched_entry.get("tract", "")

        def term(name: str) -> tuple[str, str]:
            spec = proved.get(name) or {}
            return str(spec.get("value") or ""), str(spec.get("cited_to") or "")

        unit_tract = (tract_map.get(opinion_tag, {})
                      .get(opinion_tract or "All Tracts") or {})
        mi = (agg.get(opinion_tag) or {}).get(opinion_lease_no)

        lessor, lessor_cite = term("lessor")
        lessee, lessee_cite = term("lessee")
        royalty, royalty_cite = term("royalty")
        recording, recording_cite = term("recording")
        legal, legal_cite = term("legal_description")
        primary, primary_cite = term("term")
        # Exhibit "A" is the AUTHORITY on a lease's recording (categories.yaml
        # dpu.authority). An extraction that scraped a volume/page off the page
        # is not allowed to overrule it — five Lease Review rows once carried
        # the land description's own deed reference as the lease's recording.
        book = page = ""
        authority_recording = str(d.get("recording") or "")
        if authority_recording:
            digits = re.findall(r"\d+", authority_recording)
            if len(digits) >= 2:
                book, page = digits[0], digits[1]
            recording_cite = ('unit designation, Exhibit "A"'
                              + (f" (extraction read {recording[:36]!r} — not "
                                 f"adopted)" if recording
                                 and re.findall(r"\d+", recording)[:2]
                                 != digits[:2] else ""))

        cells: list[tuple[str, str, str, str, str]] = [
            # column, value, citation, term name, reason when blank
            ("A", unit_tract.get("unit_tract", ""),
             unit_tract.get("evidence", ""), "unit_tract", "confirmar_no_cartorio"),
            ("B", lease, 'unit designation, Exhibit "A"', "lease_no", ""),
            ("C", "WI", "the Seller's interest through this lease "
                        "(template column C: Interest Type)", "interest_type", ""),
            ("D", "EOG Resources, Inc." if lessee else "",
             lessee_cite, "wi_owner", "doc_nao_localizado"),
            ("E", lessor, lessor_cite, "lessor", "doc_nao_localizado"),
            ("F", lessee, lessee_cite, "lessee", "doc_nao_localizado"),
            ("G", royalty, royalty_cite, "royalty", "doc_nao_localizado"),
            ("H", primary, primary_cite, "primary_term", "doc_nao_localizado"),
            ("K", book, recording_cite, "record_book", "doc_nao_localizado"),
            ("L", page, recording_cite, "record_page", "doc_nao_localizado"),
            ("M", "Fee" if lessor else "",
             "fee lease: the lessor is a private mineral owner named in "
             'Exhibit "A"', "lease_type", "doc_nao_localizado"),
            ("N", county, 'unit designation p.1 ("COUNTY OF MONTAGUE")',
             "county", ""),
            ("O", legal, legal_cite, "legal_description", "doc_nao_localizado"),
        ]
        if mi is not None:
            note = (f"{schedules[opinion_tag].opinion} p.{mi.page}"
                    + (f" ({', '.join(mi.tracts)})" if mi.tracts else "")
                    + f": exact Fraction sum of {len(mi.owners)} owner "
                    f"interest(s) naming Lease {mi.lease_no} = {mi.total} "
                    f"({'all VERIFIED' if mi.all_verified else 'contains a MISMATCH — human verdict required'})")
            cells.append(("S", mi.decimal, note, "mi_value", ""))
        else:
            cells.append(("S", "", "", "mi_value", "nao_computavel"))

        for col, value, cite, term_name, reason in cells:
            if value:
                ws[f"{col}{row_no}"] = value
                writes.append(CellWrite("Ownership - Worksheet", row_no, col,
                                        term_name, value, cite))
            else:
                writes.append(CellWrite("Ownership - Worksheet", row_no, col,
                                        term_name, "", "", reason))
        row_no += 1

    # The unit's own tract schedule, from Exhibit "C": owner and gross acres.
    for tract_no, spec in sorted(exhibit_c.items()):
        for col, value, term_name in (("A", tract_no, "unit_tract"),
                                      ("E", spec["owner"], "tract_owner"),
                                      ("R", spec["acres"], "tract_gross_acres")):
            ws[f"{col}{row_no}"] = value
            writes.append(CellWrite("Ownership - Worksheet", row_no, col,
                                    term_name, value, EXHIBIT_C_CITE))
        row_no += 1

    # The opinions' own WORKING INTEREST recaps, verbatim with their pages.
    for tag, sched in schedules.items():
        for w in sched.wi_rows:
            unit_tract = (tract_map.get(tag, {})
                          .get(w.tract or "All Tracts") or {})
            cite = f"{sched.opinion} p.{w.page}"
            if w.zone:
                cite += f" ({w.zone})"
            for col, value, term_name in (
                    ("A", unit_tract.get("unit_tract", ""), "unit_tract"),
                    ("C", "WI", "interest_type"),
                    ("D", w.name, "wi_owner"),
                    ("T", w.operating, "wi_value"),
                    ("V", w.revenue, "nri_value")):
                if not value:
                    continue
                note = unit_tract.get("evidence", cite) if col == "A" else cite
                ws[f"{col}{row_no}"] = value
                writes.append(CellWrite("Ownership - Worksheet", row_no, col,
                                        term_name, value, note))
            row_no += 1


def write_wells(wb, writes: list[CellWrite], *, wellbore: dict[str, Any],
                gaps_text: str, gaps_cite: str, unit_size: str,
                unit_cite: str) -> None:
    """Ownership - Wells: what the RRC CSVs in the corpus and the DPU prove.
    Spud/completion/status come only from RRC documents not in the corpus —
    those cells stay blank with the reason, owned by the RRC brief item."""
    ws = wb["Ownership - Wells"]
    header = {" ".join(str(c.value or "").split()).upper(): c.column_letter
              for c in next(ws.iter_rows(min_row=2, max_row=2)) if c.value}

    def col_for(label: str) -> str | None:
        return next((letter for text, letter in header.items()
                     if text.startswith(label)), None)

    row = 3
    csv_cite = wellbore["cite"]
    filled = (
        ("API #", wellbore["api"], csv_cite),
        ("WELL NAME", wellbore["lease_name"], csv_cite),
        ("OPERATOR", wellbore["operator"], csv_cite),
        ("WELL TYPE", wellbore.get("well_type", ""),
         wellbore.get("type_cite", csv_cite)),
        ("TOTAL DEPTH DRILLED", wellbore["api_depth"],
         csv_cite + " (API Depth)"),
        ("TARGET ZONE", wellbore["field"],
         f"{csv_cite}; {unit_cite} (Barnett Shale only)"),
        ("UNIT SIZE", unit_size, unit_cite),
        ("GAPS IN PRODUCTION", gaps_text, gaps_cite),
    )
    for label, value, cite in filled:
        col = col_for(label)
        if col and value:
            ws[f"{col}{row}"] = value
            writes.append(CellWrite("Ownership - Wells", row, col,
                                    label.lower().replace(" ", "_"), value,
                                    cite))
    for label in ("WELL STATUS", "DRILL TYPE", "SPUD DATE", "COMPLETION DATE"):
        col = col_for(label)
        if col:
            writes.append(CellWrite("Ownership - Wells", row, col,
                                    label.lower().replace(" ", "_"), "",
                                    "", "doc_nao_localizado"))


def write_plm_title_review(wb, writes: list[CellWrite], *, cert_basis: str,
                           legal_description: str, legal_cite: str,
                           scope_text: str, scope_cite: str,
                           landman: str, landman_cite: str,
                           submitted: str) -> None:
    """PLM Title Review: the Runsheet-A3 discipline for the certification
    dates — a declared provisional basis requiring a human verdict, never a
    quietly adopted date."""
    ws = wb["PLM Title Review"]
    entries = (
        ("Title Certification Dates:", cert_basis,
         "provisional basis, declared — requires human verdict "
         "(see Runsheet A3)", "cert_dates"),
        ("Legal Description:", legal_description, legal_cite,
         "legal_description"),
        ("Scope of Title Work:", scope_text, scope_cite, "scope"),
        ("Landman:", landman, landman_cite, "landman"),
        ("Date:", submitted, "ship-time field, filled at packaging", "date"),
    )
    for label, value, cite, term in entries:
        row = _label_row(ws, label)
        if row is None:
            continue
        if value:
            ws.cell(row=row, column=2).value = value
            writes.append(CellWrite("PLM Title Review", row, "B",
                                    f"ptr_{term}", value, cite))
        else:
            writes.append(CellWrite(
                "PLM Title Review", row, "B", f"ptr_{term}", "", "",
                "pendente_de_terceiro" if term == "landman"
                else "doc_nao_localizado"))


def production_gaps(csv_text: str) -> tuple[str, str]:
    """Months with zero gas production, straight from the production CSV."""
    import re

    months = []
    for line in csv_text.splitlines():
        m = re.match(r'^"?\s*([A-Z][a-z]{2} \d{4})"?,"?([\d,]+|0)"?,', line)
        if m:
            months.append((m.group(1), m.group(2).replace(",", "")))
    zeros = [name for name, value in months if value == "0"]
    if not months:
        return "", ""
    if not zeros:
        return (f"None ({months[0][0]} - {months[-1][0]}, per RRC production "
                f"query)", "SpecificLeaseQuery_prodAndTotalDisp_ReportCsv.csv")
    return (f"Zero gas production reported: {', '.join(zeros[:12])}"
            + (f" (+{len(zeros) - 12} more)" if len(zeros) > 12 else ""),
            "SpecificLeaseQuery_prodAndTotalDisp_ReportCsv.csv")
