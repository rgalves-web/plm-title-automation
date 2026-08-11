"""S4 DROP — decide what a document IS by reading it.

Flow spec §2: "AI decides what a thing is and what it says. Deterministic code
guarantees that nothing is lost, nothing is invented, and the math closes."

This module is the classifier that replaces the filename algorithms. Three
disciplines are structural here, not advisory:

  1. Content first. A filename is a prior with a hard confidence ceiling
     (`FILENAME_ONLY_CEILING`). A file whose bytes could not be read is never
     classified above that ceiling, no matter how well the name reads — the name
     "T-O ORIG A-811 ... 50AC.PDF" is a claim, and claims get verified.
  2. Vision is mandatory for scans (§2 rule 1). A PDF page with no extractable
     text is a scan; OCR may confirm cheaply, but a scan classified with no
     vision read carries `read_method: ocr` and cannot clear the floor for a
     high-risk category on its own.
  3. The category vocabulary is closed and comes from L1
     (`knowledge/taxonomy/categories.yaml`). The model chooses among the
     categories that exist; it cannot invent a fifteenth. Its `looks_like` prose
     is the instruction — the taxonomy teaches the reader, the code does not
     re-encode the taxonomy in regexes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.knowledge.vision import PageImage, VisionUnavailable, read_page, render_pages

# A name alone can never carry a document past a human. This is the ceiling that
# makes "the filename said so" incapable of clearing any risk floor.
FILENAME_ONLY_CEILING = 0.35
# Below this many characters a PDF page is a scan, not born-digital text.
TEXT_PAGE_MIN_CHARS = 60
SCANNED_METHODS = ("ocr", "vision")


@dataclass
class Classification:
    """One ledger record, in the flow spec §2 shape."""
    file: str
    read_method: str = "unread"          # text | ocr | vision | filename_only
    classified_as: str = "unplaced"
    matched_item: str = "unplaced"
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)     # {page, quote}
    of_record: dict[str, Any] = field(default_factory=dict)    # {status, reason|vol,page}
    extracted: dict[str, Any] = field(default_factory=dict)
    filename_prior: str = ""
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "read_method": self.read_method,
                "classified_as": self.classified_as, "matched_item": self.matched_item,
                "confidence": round(float(self.confidence), 3),
                "evidence": dict(self.evidence), "of_record": dict(self.of_record),
                "extracted": dict(self.extracted), "filename_prior": self.filename_prior,
                "conflicts": list(self.conflicts), "notes": list(self.notes)}


# ---------------------------------------------------------------------------
# Reading — the part that decides how much the classification is worth
# ---------------------------------------------------------------------------

IMAGE_SUFFIXES = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}


def read_front_pages(path: str | Path, pages: int = 2,
                     ocr_fn: Callable[[Any], str] | None = None
                     ) -> tuple[list[str], str, list[int]]:
    """Return (texts, read_method, scanned_page_numbers) for the first pages.

    Never reads the whole document: classification is a first-pages question,
    and paying to OCR page 40 of a lease to learn it is a lease is how a round
    stops being affordable."""
    path = Path(path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return [], "vision_required", [1]
    if path.suffix.lower() != ".pdf":
        return [], "filename_only", []

    import fitz
    try:
        doc = fitz.open(str(path))
    except Exception:
        return [], "filename_only", []
    texts: list[str] = []
    scanned: list[int] = []
    try:
        for i in range(min(pages, doc.page_count)):
            text = doc[i].get_text().strip()
            if len(text) >= TEXT_PAGE_MIN_CHARS:
                texts.append(text)
            else:
                scanned.append(i + 1)
                texts.append("")
    finally:
        doc.close()

    if not scanned:
        return texts, "text", []
    if ocr_fn is not None:
        import io

        import fitz
        from PIL import Image
        doc = fitz.open(str(path))
        try:
            for page_no in scanned:
                pix = doc[page_no - 1].get_pixmap(dpi=220)
                texts[page_no - 1] = ocr_fn(Image.open(io.BytesIO(pix.tobytes("png"))))
        finally:
            doc.close()
        return texts, "ocr", scanned
    return texts, "vision_required", scanned


def default_ocr():
    import pytesseract

    from src.flow.config import configure_tesseract, load_config
    configure_tesseract(load_config())
    return pytesseract.image_to_string


# ---------------------------------------------------------------------------
# The instruction — built FROM the taxonomy, never duplicating it
# ---------------------------------------------------------------------------

def build_instruction(knowledge: Any, checklist_items: list[str] | None = None) -> str:
    lines = ["You are classifying ONE document from a Texas oil-and-gas title",
             "due-diligence corpus. Decide what it IS by what it SAYS.",
             "", "The categories are closed. Choose exactly one:"]
    for name, cat in knowledge.taxonomy.categories.items():
        looks = " ".join(str(getattr(cat, "looks_like", "") or "").split())
        label = getattr(cat, "label", name)
        lines.append(f"- {name} ({label}){': ' + looks if looks else ''}")
    if checklist_items:
        lines += ["", "Expected checklist items (matched_item), or \"unplaced\":"]
        lines += [f"- {item}" for item in checklist_items]
    lines += [
        "",
        "Return ONLY a JSON object:",
        "{",
        '  "classified_as": "<one category name above>",',
        '  "matched_item": "<checklist item or unplaced>",',
        '  "confidence": <0.0-1.0>,',
        '  "evidence": {"page": <int>, "quote": "<verbatim words from the page>"},',
        '  "of_record": {"status": "recorded|not_recorded|unknown",',
        '                "vol": "", "page": "", "reason": ""},',
        '  "extracted": {"eog_lease_number": "", "lessor": "", "lessee": "",',
        '                "instrument_date": "", "recording": "", "abstract": "",',
        '                "survey": "", "blocks": "", "gross_acres": "", "cert_date": "",',
        '                "legal_description": "", "royalty": "", "term": ""}',
        "}",
        "",
        "Rules:",
        "- The quote must be words that literally appear on the page. Never paraphrase.",
        "- Leave a field \"\" when the document does not state it. Never infer it.",
        "- of_record.status is \"recorded\" ONLY with a volume/page, clerk file",
        "  stamp or instrument number visible; otherwise say why it is internal.",
        "- A short-form instrument that memorialises a lease without its full",
        "  clause set is lease_memorandum, not lease_ogl.",
        "- \"blocks\": the BLOCK numbers named with the survey, if any. The same",
        "  abstract in another block is a different place, so never omit them",
        "  when the document prints them.",
        "- If the page does not let you decide, use \"unplaced\" and low confidence.",
    ]
    return "\n".join(lines)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(raw: str) -> dict[str, Any]:
    m = _JSON_RE.search(raw or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


# A cover page is not the document — FOR EVERY TYPE, not just opinions.
#
# The rule was learned on a title opinion mailed under "Dear Mr. X: Enclosed
# please find our Original Title Opinion", and it was fixed there and nowhere
# else. That is a fix, not a rule. An assignment, a lease, a probate and a
# release all arrive under transmittal letters, so the arbitration below is
# type-agnostic by construction, runs on the text path as well as the vision
# path, and — this is the half that was missing — keeps LOOKING when the pages
# it has read are all transmittal. A two-page window plus "prefer the
# substantive page" still files a lease as correspondence when the cover letter
# is three pages long.
_TRANSMITTAL = {"correspondence", "unplaced"}
# How deep to keep looking when every page read so far is a cover page. Bounded,
# because an unbounded scan of a 54-page opinion is how a round stops being
# affordable — but 2 was never enough.
TRANSMITTAL_SCAN_PAGES = 6


def _best_answer(answers: list[str]) -> dict[str, Any]:
    """One answer per page — take the page that names the instrument."""
    parsed = [p for p in (_parse_json(a) for a in answers) if p]
    if not parsed:
        return {}
    substantive = [p for p in parsed
                   if str(p.get("classified_as")) not in _TRANSMITTAL]
    pool = substantive or parsed

    def score(d: dict[str, Any]) -> float:
        try:
            return float(d.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    best = max(pool, key=score)
    if substantive and len(parsed) > len(substantive):
        best.setdefault("_notes", []).append(
            "a front page reads as a transmittal letter; classified by the "
            "instrument page instead")
    return best


# ---------------------------------------------------------------------------
# The filename prior — a hint, with its ceiling
# ---------------------------------------------------------------------------

_PRIOR_HINTS: tuple[tuple[str, str], ...] = (
    (r"\bT-?O\b|TITLE OPINION", "title_opinion"),
    (r"\bMEMO(RANDUM)?\b", "lease_memorandum"),
    (r"OIL & GAS|OGL|\bLEASE\b", "lease_ogl"),
    (r"ASSIGN", "assignment"),
    (r"\bDEED\b|RELEASE|LIEN", "deed_release_lien"),
    (r"PROBATE|HEIRSHIP", "probate_heirship"),
    (r"POOLED UNIT|\bDPU\b|DESIGNATION OF UNIT", "dpu"),
    (r"\bW-?1\b|\bP-?12\b|COMPLETION|PLUGGING", "well_file"),
)


def filename_prior(path: str | Path) -> str:
    """The weak prior. Seed hints demoted from rules (flow spec §2 rule 4)."""
    name = Path(path).name.upper()
    for pattern, category in _PRIOR_HINTS:
        if re.search(pattern, name):
            return category
    return ""


# ---------------------------------------------------------------------------
# Classify
# ---------------------------------------------------------------------------

def classify_document(path: str | Path, knowledge: Any, *, cache_dir: str | Path,
                      checklist_items: list[str] | None = None,
                      ocr_fn: Callable[[Any], str] | None = None,
                      vision: bool = True,
                      instruction: str | None = None) -> Classification:
    """Read the document's front pages and say what it is, with its evidence."""
    path = Path(path)
    c = Classification(file=str(path), filename_prior=filename_prior(path))
    texts, method, scanned = read_front_pages(path, ocr_fn=ocr_fn)
    instruction = instruction or build_instruction(knowledge, checklist_items)

    payload: list[Any] = []
    if method == "text":
        payload = [t for t in texts if t.strip()]
        c.read_method = "text"
    elif method == "ocr":
        payload = [t for t in texts if t.strip()]
        c.read_method = "ocr"

    # A scan with no usable text MUST go to vision (§2 rule 1); an OCR read of a
    # scan is a cheap confirmation, not a licence to skip the look.
    needs_vision = method == "vision_required" or (
        method == "ocr" and not any(t.strip() for t in texts))

    if needs_vision and vision:
        try:
            answers = _scan_until_substantive(
                path, scanned or [1], instruction, cache_dir,
                lambda img: read_page(img, instruction, cache_dir=cache_dir))
            c.read_method = "vision"
            return _apply(c, _best_answer(answers), knowledge)
        except VisionUnavailable as exc:
            c.notes.append(f"vision unavailable: {exc}")
        except Exception as exc:                       # noqa: BLE001 - reported
            c.notes.append(f"vision failed: {type(exc).__name__}: {exc}")

    if not payload:
        # Nothing was read. The name is all there is, and the name does not
        # get to decide — it proposes, capped, and a human arbitrates.
        c.read_method = "filename_only"
        c.classified_as = c.filename_prior or "unplaced"
        c.confidence = FILENAME_ONLY_CEILING if c.filename_prior else 0.0
        c.notes.append("classified from filename only — content was not read")
        return c

    # The text path gets the same arbitration: one read per page, then the page
    # that names the instrument wins. Sending both pages in one prompt made a
    # cover letter and its instrument indistinguishable to the reader.
    answers = [_ask_text([page], instruction, cache_dir) for page in payload]
    if all(str(_parse_json(a).get("classified_as", "unplaced")) in _TRANSMITTAL
           for a in answers):
        answers += _deeper_text_pages(path, len(payload), instruction, cache_dir,
                                      ocr_fn)
    return _apply(c, _best_answer(answers), knowledge)


def _scan_until_substantive(path: Path, first: list[int], instruction: str,
                            cache_dir: str | Path,
                            ask: Callable[[PageImage], str]) -> list[str]:
    """Read the front pages; if they are all cover pages, keep going.

    Bounded by TRANSMITTAL_SCAN_PAGES. Stops the moment a page names an
    instrument, so the common case still costs two reads."""
    answers = [ask(img) for img in _front_images(path, first)]
    if not _all_transmittal(answers):
        return answers

    seen = set(first[:2]) | {1, 2}
    total = _page_count(path)
    for page_no in range(1, min(total, TRANSMITTAL_SCAN_PAGES) + 1):
        if page_no in seen:
            continue
        seen.add(page_no)
        try:
            more = [ask(img) for img in _front_images(path, [page_no])]
        except Exception:                       # noqa: BLE001 — partial is honest
            break
        answers += more
        if not _all_transmittal(more):
            break
    return answers


def _deeper_text_pages(path: Path, already: int, instruction: str,
                       cache_dir: str | Path,
                       ocr_fn: Callable[[Any], str] | None) -> list[str]:
    import fitz
    out: list[str] = []
    try:
        doc = fitz.open(str(path))
    except Exception:                           # noqa: BLE001
        return out
    try:
        for i in range(already, min(doc.page_count, TRANSMITTAL_SCAN_PAGES)):
            text = doc[i].get_text().strip()
            if len(text) < TEXT_PAGE_MIN_CHARS:
                continue
            answer = _ask_text([text], instruction, cache_dir)
            out.append(answer)
            if str(_parse_json(answer).get("classified_as", "unplaced")) \
                    not in _TRANSMITTAL:
                break
    finally:
        doc.close()
    return out


def _all_transmittal(answers: list[str]) -> bool:
    parsed = [_parse_json(a) for a in answers]
    return all(str(p.get("classified_as", "unplaced")) in _TRANSMITTAL
               for p in parsed)


def _page_count(path: Path) -> int:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            return getattr(Image.open(path), "n_frames", 1)
        except Exception:                       # noqa: BLE001
            return 1
    try:
        import fitz
        doc = fitz.open(str(path))
        try:
            return doc.page_count
        finally:
            doc.close()
    except Exception:                           # noqa: BLE001
        return 1


def _front_images(path: Path, pages: list[int]) -> list[PageImage]:
    """The requested pages as PNG. TIFs are the corpus's native scan format and
    are not a wire format the API accepts, so they are converted here — and
    multi-page TIFs are seeked, because a cover page happens on TIFs too."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        import io

        from PIL import Image

        from src.knowledge.vision import _fit
        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(path)
        frames = getattr(img, "n_frames", 1)
        out: list[PageImage] = []
        for page_no in pages[:2]:
            if page_no > frames:
                continue
            img.seek(page_no - 1)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            out.append(PageImage(png=_fit(buf.getvalue()), page_no=page_no,
                                 source=path.name))
        return out
    return render_pages(path, pages[:2], dpi=200)


def _ask_text(pages: list[str], instruction: str, cache_dir: str | Path) -> str:
    """Text pages go through the same cached path as images, keyed by content."""
    import hashlib

    from src.knowledge.vision import CACHE_DIRNAME, _client, DEFAULT_MODEL
    body = "\n\n--- page break ---\n\n".join(p[:6000] for p in pages[:2])
    cache = Path(cache_dir) / CACHE_DIRNAME
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((body + instruction).encode("utf-8")).hexdigest()[:32]
    hit = cache / f"{key}.json"
    if hit.exists():
        return json.loads(hit.read_text(encoding="utf-8"))["text"]
    client = _client()
    msg = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": f"{instruction}\n\n=== DOCUMENT ===\n{body}"}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    hit.write_text(json.dumps({"text": text}), encoding="utf-8")
    return text


def _apply(c: Classification, data: dict[str, Any], knowledge: Any) -> Classification:
    if not data:
        c.notes.append("model returned no parseable JSON")
        c.classified_as = "unplaced"
        c.confidence = 0.0
        return c
    category = str(data.get("classified_as") or "unplaced")
    if category not in knowledge.taxonomy.categories:
        c.notes.append(f"model proposed a category outside L1: {category!r}")
        category = "unplaced"
    c.classified_as = category
    c.matched_item = str(data.get("matched_item") or "unplaced")
    try:
        c.confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        c.confidence = 0.0
    c.evidence = dict(data.get("evidence") or {})
    c.of_record = dict(data.get("of_record") or {})
    c.extracted = {k: v for k, v in (data.get("extracted") or {}).items() if v}
    c.notes.extend(data.get("_notes") or [])

    if not str(c.evidence.get("quote") or "").strip():
        # No quote is no evidence. Invariant 5 makes this a cap, not a note.
        c.confidence = min(c.confidence, FILENAME_ONLY_CEILING)
        c.notes.append("no evidence quote returned — confidence capped")
    if c.filename_prior and c.filename_prior != c.classified_as:
        c.conflicts.append(
            f"filename suggested {c.filename_prior}; content says {c.classified_as}")
    return c


# ---------------------------------------------------------------------------
# D5 — who has to look at this
# ---------------------------------------------------------------------------

def verdict_queue(classifications: list[Classification], knowledge: Any,
                  floor: float = 0.85) -> dict[str, list[Classification]]:
    """Split by risk tier. `auto` is only for low-risk AND above the floor AND
    read from content — a filename-only read never auto-confirms."""
    out: dict[str, list[Classification]] = {"human": [], "auto": []}
    for c in classifications:
        needs = knowledge.needs_human_verdict(c.classified_as, c.confidence, floor)
        if needs or c.read_method == "filename_only" or c.conflicts:
            out["human"].append(c)
        else:
            out["auto"].append(c)
    return out
