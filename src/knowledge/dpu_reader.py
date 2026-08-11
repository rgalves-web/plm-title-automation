"""Read a recorded Declaration of Pooled Unit — the authority on the perimeter.

The DPU is a scan, so this reads it: page images through OCR, then structure out
of the exhibits. Everything returned carries the PAGE it came from, because a
perimeter without proof is an opinion.

What the exhibits are for:
  Exhibit "A"  the lease list — EOG number, lessor, date, recording. THE list.
  Exhibit "B"  the metes and bounds — the surveys the unit sits in, and the
               adjoining tracts named only as corners. The difference between
               "inside" and "next to" lives here, and it is the difference that
               decides whether a whole lease series is in the unit.
  Exhibit "C"  the plat — neighbouring surveys, which are NOT the unit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# "0220604/007" in the exhibit; "0220604-007" everywhere else in the project.
_LEASE_RE = re.compile(r"\b(0\d{6})\s*[/-]\s*(\d{3})\b")
_ABSTRACT_RE = re.compile(r"\bA-\s?(\d{2,4})\b")
# "recorded as Tract 1 in Volume 217, Page 491"
_TRACT_IN_DEED_RE = re.compile(
    r"recorded as Tract\s+(\d+)\s+in\s+Volume\s+(\d{2,4}),?\s+Page\s+(\d{1,4})",
    re.IGNORECASE)
_UNIT_ACRES_RE = re.compile(r"([\d,]+\.?\d*)\s*acre", re.IGNORECASE)
_EFFECTIVE_RE = re.compile(r"effective\s+([A-Z][a-z]+ \d{1,2}, \d{4})")


@dataclass
class DPUReading:
    """What the DPU says, with the page that says it."""
    recording: str = ""
    effective_date: str = ""
    unit_name: str = ""
    gross_acres: str = ""
    surveys: list[tuple[str, int]] = field(default_factory=list)      # (abstract, page)
    leases: dict[str, dict[str, Any]] = field(default_factory=dict)   # lease -> {recording,page}
    inside_tracts: list[dict[str, Any]] = field(default_factory=list)
    adjoining_tracts: list[dict[str, Any]] = field(default_factory=list)
    exhibit_pages: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def proof(self, exhibit: str = "A") -> str:
        page = self.exhibit_pages.get(exhibit)
        return (f"{self.recording} Exhibit \"{exhibit}\" p.{page}" if page
                else self.recording)


def ocr_pdf(path: str | Path, dpi: int = 220,
            ocr_fn: Callable[[Any], str] | None = None) -> list[str]:
    """Every page of a scanned PDF as text. Deterministic OCR, no LLM."""
    import fitz
    from PIL import Image
    import io

    if ocr_fn is None:
        import pytesseract

        from src.flow.config import configure_tesseract, load_config
        configure_tesseract(load_config())
        ocr_fn = pytesseract.image_to_string

    doc = fitz.open(str(path))
    out: list[str] = []
    try:
        for page in doc:
            embedded = page.get_text().strip()
            if embedded:
                out.append(embedded)            # born-digital: no OCR needed
                continue
            pix = page.get_pixmap(dpi=dpi)
            out.append(ocr_fn(Image.open(io.BytesIO(pix.tobytes("png")))))
    finally:
        doc.close()
    return out


def read_dpu(pages: list[str]) -> DPUReading:
    """Structure a DPU from its OCR'd pages. Every field keeps its page."""
    r = DPUReading()
    joined = "\n".join(pages)

    m = re.search(r"VOL\s*(\d{2,4})\s*PAGE\s*(\d{1,4})", joined, re.IGNORECASE)
    if m:
        r.recording = f"Vol. {m.group(1)}, Pg. {m.group(2)}"
    m = re.search(r"DECLARATION OF POOLED UNIT\s*[-—]\s*([A-Z0-9 .]+)", joined)
    if m:
        r.unit_name = m.group(1).strip()
    m = _EFFECTIVE_RE.search(joined)
    if m:
        r.effective_date = m.group(1)

    for i, text in enumerate(pages, start=1):
        head = text[:400]
        for letter in ("A", "B", "C"):
            if re.search(rf'EXHIBIT\s*[“"\']?{letter}', head, re.IGNORECASE):
                r.exhibit_pages.setdefault(letter, i)

    # --- Exhibit A: the lease list ---------------------------------------
    a_page = r.exhibit_pages.get("A")
    if a_page:
        for i in range(a_page - 1, len(pages)):
            if i + 1 != a_page and re.search(r'EXHIBIT\s*[“"\']?[BC]', pages[i][:400],
                                             re.IGNORECASE):
                break
            for line in pages[i].splitlines():
                lm = _LEASE_RE.search(line)
                if not lm:
                    continue
                lease = f"{lm.group(1)}-{lm.group(2)}"
                nums = re.findall(r"\b(\d{2,4})\b", line[lm.end():])
                recording = ""
                # The exhibit's trailing columns are VOLUME then PAGE.
                vols = [n for n in nums if len(n) in (3, 4)]
                if len(vols) >= 2:
                    recording = f"Vol. {vols[-2]}, Pg. {vols[-1]}"
                r.leases.setdefault(lease, {"recording": recording, "page": i + 1})

    # --- Exhibit B: what the unit IS, and what merely touches it ---------
    b_page = r.exhibit_pages.get("B")
    if b_page:
        text = pages[b_page - 1]
        for am in _ABSTRACT_RE.finditer(text[:800]):     # the opening description
            entry = (am.group(1), b_page)
            if entry not in r.surveys:
                r.surveys.append(entry)
        am = _UNIT_ACRES_RE.search(text)
        if am:
            r.gross_acres = am.group(1)
        # The BEGINNING point sits INSIDE the unit; every other tract named in
        # the calls is a boundary marker — a neighbour, not a member. Getting
        # this backwards puts a whole lease series inside a unit it never joined.
        for tm in _TRACT_IN_DEED_RE.finditer(text):
            tract, vol, page = tm.group(1), tm.group(2), tm.group(3)
            before = text[max(0, tm.start() - 160):tm.start()].lower()
            record = {"tract": tract, "deed": f"Vol. {vol}, Pg. {page}",
                      "page": b_page, "context": before[-90:].strip()}
            if "beginning at a point within" in before or "point within" in before:
                if record not in r.inside_tracts:
                    r.inside_tracts.append(record)
            else:
                if record not in r.adjoining_tracts:
                    r.adjoining_tracts.append(record)
    return r


def split_deed_tracts(reading: DPUReading) -> list[dict[str, Any]]:
    """Deeds that convey MORE THAN ONE tract, where the unit took only some.

    This is the shape that silently inflates a unit: one deed conveys two
    tracts, the DPU pools the first, and every lease over the second looks like
    it belongs because it shares the deed. The proof that it does not is the
    DPU's own calls — one tract is where the unit begins, the other is only a
    corner it passes."""
    inside = {t["deed"]: t for t in reading.inside_tracts}
    findings = []
    for adj in reading.adjoining_tracts:
        twin = inside.get(adj["deed"])
        if twin and twin["tract"] != adj["tract"]:
            findings.append({
                "deed": adj["deed"],
                "in_unit_tract": twin["tract"],
                "outside_tract": adj["tract"],
                "proof": f"{reading.proof('B')}: the unit BEGINS within Tract "
                         f"{twin['tract']} of {adj['deed']}; Tract {adj['tract']} "
                         f"of the same deed is named only as an adjoining corner",
            })
    return findings
