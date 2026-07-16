from __future__ import annotations

import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.lease_engine import infer_lease_status
from src.schemas import ClassificationStatus, LeaseStatus, SourceDocument
from src.utils import clean_cell, enum_value, get_logger, normalize_text, parse_date


logger = get_logger(__name__)

TEXT_EXTRACTED = "TEXT_EXTRACTED"
LOW_CONFIDENCE_TEXT = "LOW_CONFIDENCE_TEXT"
OCR_REQUIRED = "OCR_REQUIRED"
EXTRACTION_ERROR = "EXTRACTION_ERROR"

LOW_CONFIDENCE_THRESHOLD = 0.55
OCR_CONFIDENCE_PENALTY = 0.85
PREVIEW_CHAR_LIMIT = 1200
SNIPPET_CHAR_LIMIT = 280

# Windows default Tesseract install path (UB Mannheim installer)
_TESSERACT_WIN_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


DOCUMENT_TYPE_KEYWORDS = [
    "Patent",
    "Mineral Deed",
    "Warranty Deed",
    "Special Warranty Deed",
    "Quit Claim Deed",
    "Quitclaim Deed",
    "Oil and Gas Lease",
    "Oil & Gas Lease",
    "O&G Lease",
    "Release of Oil and Gas Lease",
    "Assignment of Oil and Gas Lease",
    "Bill of Sale",
    "Probate",
    "Affidavit of Heirship",
    "Distribution Deed",
    "Correction Deed",
    "Scrivener's Affidavit",
    "Public Trustee's Deed",
    "Foreclosure Deed",
    "Easement",
    "Right of Way",
    "Deed of Trust",
    "Mortgage",
    "Lien",
    "UCC",
    "Financing Statement",
]

LEGAL_DESCRIPTION_PATTERNS = [
    re.compile(
        r"(?:section|sec\.?)\s+\d{1,2}[^.\n]{0,180}?"
        r"(?:township|twp\.?|t)\s*\d{1,3}\s*[ns][^.\n]{0,100}?"
        r"(?:range|rng\.?|r)\s*\d{1,3}\s*[ew]",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:township|twp\.?)\s*\d{1,3}\s*[ns][^.\n]{0,140}?"
        r"(?:range|rng\.?)\s*\d{1,3}\s*[ew]",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:lot|lots)\s+[\w, -]+[^.\n]{0,80}?(?:block|blk)\s+[\w-]+",
        re.IGNORECASE,
    ),
    re.compile(r"(?:tract)\s+[\w-]+[^.\n]{0,160}", re.IGNORECASE),
    re.compile(
        r"(?:legal description|described as|described property|lands described)"
        r"[^.\n]{0,240}",
        re.IGNORECASE,
    ),
]

LEASE_PRIMARY_TERM_PATTERNS = [
    re.compile(
        r"(?:primary term)\s+(?:of\s+)?(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+years?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+year\s+primary\s+term",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:for a term of)\s+(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s+years?",
        re.IGNORECASE,
    ),
]


class TextExtractionError(RuntimeError):
    pass


@dataclass
class PDFExtractionResult:
    file_path: str
    page_count: int
    extraction_status: str
    extraction_confidence: float
    text_preview: str = ""
    possible_document_type_keywords: list[str] = field(default_factory=list)
    possible_legal_description_snippets: list[str] = field(default_factory=list)
    possible_lease_primary_term_snippets: list[str] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    full_text: str = ""
    extraction_engine: str = "PyMuPDF"
    review_required: bool = False
    review_reason: str | None = None
    error: str | None = None

    def as_dict(self, include_full_text: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        payload["extracted_fields"] = {
            key: enum_value(value) for key, value in self.extracted_fields.items()
        }
        if not include_full_text:
            payload.pop("full_text", None)
        return payload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_document(
    path: str | Path,
    text_cache_dir: str | Path | None = None,
) -> PDFExtractionResult:
    """Extract text from a PDF or image file, falling back to OCR when needed."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path, text_cache_dir=text_cache_dir)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return _extract_image_ocr(path, text_cache_dir=text_cache_dir)
    raise TextExtractionError(f"Unsupported document file type: {suffix}")


def extract_pdf(
    path: str | Path,
    text_cache_dir: str | Path | None = None,
) -> PDFExtractionResult:
    """Extract text from a PDF, using OCR when native text is absent."""
    path = Path(path)
    try:
        text, page_count, engine = _extract_pdf_text_pymupdf(path)
    except ImportError:
        logger.info("PyMuPDF not available; falling back to pdfplumber.")
        text, page_count, engine = _extract_pdf_text_pdfplumber(path)
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed for %s: %s", path, exc)
        try:
            text, page_count, engine = _extract_pdf_text_pdfplumber(path)
        except Exception as fallback_exc:
            return PDFExtractionResult(
                file_path=str(path),
                page_count=0,
                extraction_status=EXTRACTION_ERROR,
                extraction_confidence=0.0,
                extraction_engine="PyMuPDF/pdfplumber",
                review_required=True,
                review_reason=(
                    "PDF text extraction failed; human review and OCR are required."
                ),
                error=str(fallback_exc),
            )

    if not _has_useful_text(text):
        return _extract_with_ocr(path, page_count, text_cache_dir=text_cache_dir)

    return _build_result_from_text(path, page_count, text, engine=engine)


def apply_extraction_to_record(
    record: SourceDocument,
    extraction: PDFExtractionResult,
    extracted_text_dir: str | Path | None = None,
) -> SourceDocument:
    record.pdf_extraction_status = extraction.extraction_status
    record.pdf_extraction_confidence = extraction.extraction_confidence
    record.pdf_page_count = extraction.page_count
    record.pdf_text_preview = extraction.text_preview
    record.possible_document_type_keywords = extraction.possible_document_type_keywords
    record.possible_legal_description_snippets = (
        extraction.possible_legal_description_snippets
    )
    record.possible_lease_primary_term_snippets = (
        extraction.possible_lease_primary_term_snippets
    )
    record.source_trace["pdf_extraction"] = extraction.as_dict()

    if extracted_text_dir and extraction.full_text:
        text_path = _write_extracted_text(record, extraction, extracted_text_dir)
        record.extracted_text_path = str(text_path)

    if _can_apply_extracted_fields(extraction):
        _apply_extracted_fields_to_record(record, extraction.extracted_fields)

    # Apply template-grade conveyance/comments using doc-type-aware rules.
    # Runs after the generic extractor so canonical prefixes always win.
    if extraction.full_text and _has_useful_text(extraction.full_text):
        _apply_title_extractor_fields(record, extraction.full_text)

    if extraction.review_required:
        if record.status != ClassificationStatus.DUPLICATE:
            record.status = ClassificationStatus.REVIEW
        record.classification_confidence = min(
            record.classification_confidence or extraction.extraction_confidence,
            extraction.extraction_confidence,
        )
        record.review_question = _append_review_question(
            record.review_question,
            extraction.review_reason or "PDF extraction requires human review.",
        )
    return record


def extract_text(path: str | Path) -> str:
    return extract_document(path).full_text


def extract_pdf_text(path: str | Path) -> str:
    return extract_pdf(path).full_text


# ---------------------------------------------------------------------------
# Field extraction helpers (public — used by pipeline directly)
# ---------------------------------------------------------------------------

def find_possible_document_type_keywords(text: str) -> list[str]:
    normalized_text = _normalized_for_matching(text)
    found: list[str] = []
    for keyword in DOCUMENT_TYPE_KEYWORDS:
        if _normalized_for_matching(keyword) in normalized_text:
            if keyword not in found:
                found.append(keyword)
    return found


def find_possible_legal_description_snippets(text: str) -> list[str]:
    snippets: list[str] = []
    for pattern in LEGAL_DESCRIPTION_PATTERNS:
        snippets.extend(_snippets_for_pattern(text, pattern))
    return _unique_limited(snippets)


def find_possible_lease_primary_term_snippets(text: str) -> list[str]:
    snippets: list[str] = []
    for pattern in LEASE_PRIMARY_TERM_PATTERNS:
        snippets.extend(_snippets_for_pattern(text, pattern))
    return _unique_limited(snippets)


def extract_possible_fields(
    text: str,
    legal_snippets: list[str] | None = None,
    lease_term_snippets: list[str] | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    legal_snippets = legal_snippets or find_possible_legal_description_snippets(text)
    lease_term_snippets = lease_term_snippets or find_possible_lease_primary_term_snippets(text)

    parties = _extract_parties(text)
    fields.update(parties)

    effective_date = _extract_effective_date(text)
    if effective_date:
        fields["effective_date"] = effective_date

    acreage = _extract_acreage(text)
    if acreage:
        fields["acreage"] = acreage

    if legal_snippets:
        fields["legal_description"] = legal_snippets[0]

    conveyance = _extract_conveyance(text, legal_snippets)
    if conveyance:
        fields["conveyance"] = conveyance

    normalized_text = normalize_text(text)
    lease_status = infer_lease_status(
        SourceDocument(
            source_document_id="PDF-EXTRACTION",
            source_row_number=0,
            document_type=(
                "Oil and Gas Lease"
                if "oil and gas lease" in normalized_text
                or "oil & gas lease" in normalized_text
                or "o&g lease" in normalized_text
                else None
            ),
        ),
        extracted_text=text,
    )
    if lease_status:
        fields["lease_status"] = lease_status

    return fields


def calculate_extraction_confidence(
    text: str,
    page_count: int,
    possible_keywords: list[str] | None = None,
    legal_snippets: list[str] | None = None,
    lease_term_snippets: list[str] | None = None,
) -> float:
    possible_keywords = possible_keywords or []
    legal_snippets = legal_snippets or []
    lease_term_snippets = lease_term_snippets or []
    alnum_count = sum(1 for character in text if character.isalnum())
    unique_words = len(set(re.findall(r"[A-Za-z]{3,}", text.lower())))
    pages_with_text = _pages_with_useful_text(text)
    page_score = (
        min(pages_with_text / max(page_count, 1), 1.0) * 0.20
        if page_count
        else 0.0
    )
    char_score = min(alnum_count / 1000, 1.0) * 0.35
    word_score = min(unique_words / 120, 1.0) * 0.25
    keyword_score = 0.15 if possible_keywords else 0.0
    snippet_score = 0.05 if legal_snippets or lease_term_snippets else 0.0
    confidence = char_score + word_score + page_score + keyword_score + snippet_score
    return round(min(confidence, 0.95), 3)


# ---------------------------------------------------------------------------
# Core text-extraction back-ends
# ---------------------------------------------------------------------------

def _extract_pdf_text_pymupdf(path: Path) -> tuple[str, int, str]:
    import fitz

    with fitz.open(path) as document:
        page_texts = [page.get_text("text") or "" for page in document]
        return "\n\f\n".join(page_texts), document.page_count, "PyMuPDF"


def _extract_pdf_text_pdfplumber(path: Path) -> tuple[str, int, str]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise TextExtractionError(
            "Install PyMuPDF or pdfplumber to extract PDF text."
        ) from exc

    with pdfplumber.open(path) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]
        return "\n\f\n".join(page_texts), len(pdf.pages), "pdfplumber"


# ---------------------------------------------------------------------------
# OCR path
# ---------------------------------------------------------------------------

def _configure_tesseract() -> None:
    """Point pytesseract at the Windows default install if not already in PATH."""
    try:
        import pytesseract
        if pytesseract.pytesseract.tesseract_cmd == "tesseract" and not shutil.which("tesseract"):
            win_path = Path(_TESSERACT_WIN_PATH)
            if win_path.exists():
                pytesseract.pytesseract.tesseract_cmd = str(win_path)
    except Exception:
        pass


def _extract_with_ocr(
    path: Path,
    page_count: int,
    text_cache_dir: str | Path | None = None,
) -> PDFExtractionResult:
    """Rasterize a scanned PDF at 300 DPI and run Tesseract per page."""
    if text_cache_dir:
        cached = _load_ocr_cache(path, text_cache_dir)
        if cached is not None:
            logger.debug("OCR cache hit: %s", path.name)
            if not _has_useful_text(cached):
                return PDFExtractionResult(
                    file_path=str(path),
                    page_count=page_count,
                    extraction_status=LOW_CONFIDENCE_TEXT,
                    extraction_confidence=0.0,
                    extraction_engine="tesseract_ocr",
                    full_text=cached,
                    review_required=True,
                    review_reason="OCR produced no useful text; human review is required.",
                )
            return _build_result_from_text(
                path, page_count, cached, engine="tesseract_ocr", ocr_penalty=True
            )

    try:
        import pytesseract
        from PIL import Image as PILImage
    except ImportError:
        return _ocr_required_result(
            path,
            page_count,
            "Install pytesseract and Pillow to enable OCR for scanned documents.",
        )

    _configure_tesseract()

    try:
        import fitz

        texts: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                mat = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                page_text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
                texts.append(page_text)
        ocr_text = "\n\f\n".join(texts)
    except Exception as exc:
        logger.warning("Tesseract OCR failed for %s: %s", path, exc)
        return _ocr_required_result(path, page_count, f"OCR failed: {exc}")

    if text_cache_dir:
        _save_ocr_cache(path, text_cache_dir, ocr_text)

    if not _has_useful_text(ocr_text):
        return PDFExtractionResult(
            file_path=str(path),
            page_count=page_count,
            extraction_status=LOW_CONFIDENCE_TEXT,
            extraction_confidence=0.0,
            extraction_engine="tesseract_ocr",
            full_text=ocr_text,
            review_required=True,
            review_reason="OCR produced no useful text; human review is required.",
        )

    return _build_result_from_text(
        path, page_count, ocr_text, engine="tesseract_ocr", ocr_penalty=True
    )


def _extract_image_ocr(
    path: Path,
    text_cache_dir: str | Path | None = None,
) -> PDFExtractionResult:
    """OCR a standalone image file (.png/.jpg/.tif)."""
    if text_cache_dir:
        cached = _load_ocr_cache(path, text_cache_dir)
        if cached is not None:
            logger.debug("OCR cache hit: %s", path.name)
            if not _has_useful_text(cached):
                return PDFExtractionResult(
                    file_path=str(path),
                    page_count=1,
                    extraction_status=LOW_CONFIDENCE_TEXT,
                    extraction_confidence=0.0,
                    extraction_engine="tesseract_ocr",
                    full_text=cached,
                    review_required=True,
                    review_reason="Image OCR produced no useful text; human review is required.",
                )
            return _build_result_from_text(
                path, 1, cached, engine="tesseract_ocr", ocr_penalty=True
            )

    try:
        import pytesseract
        from PIL import Image as PILImage
    except ImportError:
        return _ocr_required_result(
            path,
            1,
            "Install pytesseract and Pillow to enable OCR for image documents.",
        )

    _configure_tesseract()

    # Recorded instruments are routinely MULTI-PAGE TIFs (a Declaration of Pooled
    # Unit and its Exhibit A lease list, a recorded lease and its exhibits). PIL
    # opens such a file positioned on frame 0, so OCR'ing the image as-is reads
    # page 1 and silently discards the rest — the pages carrying the lease
    # schedule. Every frame is OCR'd and page_count reflects the real total.
    try:
        from PIL import ImageSequence

        img = PILImage.open(path)
        page_texts: list[str] = [
            pytesseract.image_to_string(frame, lang="eng", config="--psm 6")
            for frame in ImageSequence.Iterator(img)
        ]
    except Exception as exc:
        logger.warning("Image OCR failed for %s: %s", path, exc)
        return _ocr_required_result(path, 1, f"Image OCR failed: {exc}")

    page_count = len(page_texts) or 1
    # Same page separator the PDF OCR path uses, so downstream text handling
    # (page splitting, snippet offsets) behaves identically for both.
    ocr_text = "\n\f\n".join(page_texts)
    if page_count > 1:
        logger.debug("OCR'd %s pages of multi-page image %s", page_count, path.name)

    if text_cache_dir:
        _save_ocr_cache(path, text_cache_dir, ocr_text)

    if not _has_useful_text(ocr_text):
        return PDFExtractionResult(
            file_path=str(path),
            page_count=page_count,
            extraction_status=LOW_CONFIDENCE_TEXT,
            extraction_confidence=0.0,
            extraction_engine="tesseract_ocr",
            full_text=ocr_text,
            review_required=True,
            review_reason="Image OCR produced no useful text; human review is required.",
        )

    return _build_result_from_text(
        path, page_count, ocr_text, engine="tesseract_ocr", ocr_penalty=True
    )


def _build_result_from_text(
    path: Path,
    page_count: int,
    text: str,
    engine: str = "PyMuPDF",
    ocr_penalty: bool = False,
) -> PDFExtractionResult:
    possible_keywords = find_possible_document_type_keywords(text)
    legal_snippets = find_possible_legal_description_snippets(text)
    lease_term_snippets = find_possible_lease_primary_term_snippets(text)
    extracted_fields = extract_possible_fields(
        text=text,
        legal_snippets=legal_snippets,
        lease_term_snippets=lease_term_snippets,
    )
    confidence = calculate_extraction_confidence(
        text=text,
        page_count=page_count,
        possible_keywords=possible_keywords,
        legal_snippets=legal_snippets,
        lease_term_snippets=lease_term_snippets,
    )
    if ocr_penalty:
        confidence = round(confidence * OCR_CONFIDENCE_PENALTY, 3)
    low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD
    return PDFExtractionResult(
        file_path=str(path),
        page_count=page_count,
        extraction_status=LOW_CONFIDENCE_TEXT if low_confidence else TEXT_EXTRACTED,
        extraction_confidence=confidence,
        text_preview=_text_preview(text),
        possible_document_type_keywords=possible_keywords,
        possible_legal_description_snippets=legal_snippets,
        possible_lease_primary_term_snippets=lease_term_snippets,
        extracted_fields=extracted_fields,
        full_text=text,
        extraction_engine=engine,
        review_required=low_confidence,
        review_reason=(
            "PDF text extraction confidence is low; do not rely on possible "
            "keywords or snippets without human review."
        )
        if low_confidence
        else None,
    )


def _ocr_required_result(
    path: Path,
    page_count: int,
    reason: str,
    engine: str = "PyMuPDF",
) -> PDFExtractionResult:
    return PDFExtractionResult(
        file_path=str(path),
        page_count=page_count,
        extraction_status=OCR_REQUIRED,
        extraction_confidence=0.0,
        extraction_engine=engine,
        review_required=True,
        review_reason=reason,
    )


# ---------------------------------------------------------------------------
# OCR cache helpers
# ---------------------------------------------------------------------------

def _ocr_cache_key(path: Path) -> str:
    # Include a hash of the full resolved path, not just the stem: many source
    # trees carry the same basename in different folders (e.g. every lease
    # folder has its own "LEASE.pdf"/"LEASE.TIF"), and a stem-only key made
    # them all collide onto one cache entry — returning the first file's OCR
    # text for every other file. The stem stays in the name for readability.
    import hashlib

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem)[:60]
    digest = hashlib.md5(str(path.resolve()).encode("utf-8", "replace")).hexdigest()[:12]
    return f"{stem}_{digest}_ocr.txt"


def _load_ocr_cache(path: Path, cache_dir: str | Path) -> str | None:
    cache_file = Path(cache_dir) / _ocr_cache_key(path)
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _save_ocr_cache(path: Path, cache_dir: str | Path, text: str) -> None:
    try:
        cache_dir_path = Path(cache_dir)
        cache_dir_path.mkdir(parents=True, exist_ok=True)
        (cache_dir_path / _ocr_cache_key(path)).write_text(text, encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write OCR cache for %s: %s", path.name, exc)


# ---------------------------------------------------------------------------
# Private text helpers
# ---------------------------------------------------------------------------

def _has_useful_text(text: str) -> bool:
    alnum_count = sum(1 for character in text if character.isalnum())
    unique_words = len(set(re.findall(r"[A-Za-z]{3,}", text.lower())))
    return alnum_count >= 25 and unique_words >= 4


def _pages_with_useful_text(text: str) -> int:
    pages = text.split("\n\f\n")
    return sum(1 for page_text in pages if _has_useful_text(page_text))


def _text_preview(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:PREVIEW_CHAR_LIMIT]


def _normalized_for_matching(text: str) -> str:
    compact = re.sub(r"[^a-z0-9&' ]+", " ", text.lower())
    return re.sub(r"\s+", " ", compact).strip()


def _snippets_for_pattern(text: str, pattern: re.Pattern) -> list[str]:
    snippets: list[str] = []
    compact_text = re.sub(r"\s+", " ", text)
    for match in pattern.finditer(compact_text):
        start = max(match.start() - 80, 0)
        end = min(match.end() + 80, len(compact_text))
        snippet = compact_text[start:end].strip()
        if len(snippet) > SNIPPET_CHAR_LIMIT:
            snippet = snippet[:SNIPPET_CHAR_LIMIT].rstrip()
        snippets.append(snippet)
    return snippets


def _unique_limited(values: list[str], limit: int = 5) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalized_for_matching(value)
        if key and key not in seen:
            unique.append(value)
            seen.add(key)
        if len(unique) >= limit:
            break
    return unique


def _write_extracted_text(
    record: SourceDocument,
    extraction: PDFExtractionResult,
    extracted_text_dir: str | Path,
) -> Path:
    output_dir = Path(extracted_text_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_id = re.sub(r"[^A-Za-z0-9._-]+", "_", record.source_document_id)
    output_path = output_dir / f"{source_id}.txt"
    output_path.write_text(extraction.full_text, encoding="utf-8")
    return output_path


def _append_review_question(existing: str | None, addition: str) -> str:
    existing = clean_cell(existing)
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing} {addition}"


def _apply_title_extractor_fields(record: SourceDocument, full_text: str) -> None:
    """Produce template-grade CONVEYANCE and COMMENTS via title_extractor.extract().

    Uses record.document_type to pick the canonical prefix (Patent→"Grant of:",
    OGL→"Lease covering:", etc.) and extracts primary term / royalty / reservations
    for COMMENTS. Runs after the generic pattern extractor so canonical fields win.
    """
    try:
        import title_extractor as te  # root-level module; importable when app runs from project root
    except ImportError:
        logger.debug("title_extractor not found; skipping template-grade extraction")
        return

    try:
        tf = te.extract(record.document_type or "", full_text)
    except Exception as exc:
        logger.warning("title_extractor.extract failed for %s: %s", record.source_document_id, exc)
        return

    populated: dict = {}

    if tf.conveyance:
        record.conveyance = tf.conveyance
        populated["conveyance"] = tf.conveyance

    if tf.legal_description:
        record.legal_description = tf.legal_description
        populated["legal_description"] = tf.legal_description

    if tf.acreage and not record.acreage:
        record.acreage = tf.acreage
        populated["acreage"] = tf.acreage

    if tf.comments:
        record.comments = "\n".join(tf.comments)
        populated["comments"] = record.comments

    if populated:
        record.source_trace["title_extractor_fields"] = populated


def _can_apply_extracted_fields(extraction: PDFExtractionResult) -> bool:
    return (
        extraction.extraction_status == TEXT_EXTRACTED
        and extraction.extraction_confidence >= LOW_CONFIDENCE_THRESHOLD
        and bool(extraction.extracted_fields)
    )


def _apply_extracted_fields_to_record(
    record: SourceDocument,
    extracted_fields: dict[str, Any],
) -> None:
    populated: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []

    for field_name in (
        "grantor",
        "grantee",
        "legal_description",
        "acreage",
        "conveyance",
        "effective_date",
    ):
        value = extracted_fields.get(field_name)
        if value in (None, ""):
            continue
        existing = getattr(record, field_name)
        if existing not in (None, "") and not _same_value(existing, value):
            conflicts.append(
                {
                    "field": field_name,
                    "document_list_value": str(existing),
                    "pdf_value": str(value),
                }
            )
        setattr(record, field_name, value)
        populated[field_name] = enum_value(value)

    lease_status = _coerce_lease_status(extracted_fields.get("lease_status"))
    if lease_status:
        if record.lease_status and record.lease_status != lease_status:
            conflicts.append(
                {
                    "field": "lease_status",
                    "document_list_value": enum_value(record.lease_status),
                    "pdf_value": enum_value(lease_status),
                }
            )
        record.lease_status = lease_status
        populated["lease_status"] = enum_value(lease_status)

    if populated:
        record.source_trace.setdefault("pdf_populated_fields", {}).update(populated)

    if conflicts:
        record.source_trace.setdefault("pdf_field_conflicts", []).extend(conflicts)
        if record.status != ClassificationStatus.DUPLICATE:
            record.status = ClassificationStatus.REVIEW
        conflict_fields = ", ".join(conflict["field"] for conflict in conflicts)
        record.review_question = _append_review_question(
            record.review_question,
            f"PDF extracted field conflict requires review: {conflict_fields}.",
        )


def _same_value(left: Any, right: Any) -> bool:
    if hasattr(left, "isoformat") or hasattr(right, "isoformat"):
        return str(left) == str(right)
    return normalize_text(left) == normalize_text(right)


def _coerce_lease_status(value: Any) -> LeaseStatus | None:
    if isinstance(value, LeaseStatus):
        return value
    if not value:
        return None
    try:
        return LeaseStatus(str(value))
    except ValueError:
        return None


def _extract_parties(text: str) -> dict[str, str]:
    compact = re.sub(r"\s+", " ", text)
    patterns = [
        re.compile(
            r"\bbetween\s+(?P<grantor>.{3,180}?),\s+and\s+"
            r"(?P<grantee>.{3,180}?)(?:\.|,|\s+covering\b)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bby\s+and\s+between\s+(?P<grantor>.{3,180}?),\s+and\s+"
            r"(?P<grantee>.{3,180}?)(?:\.|,|\s+covering\b)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bfrom\s+(?P<grantor>.{3,180}?)\s+to\s+"
            r"(?P<grantee>.{3,180}?)(?:\.|,|\s+covering\b)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bgrantors?\s*[:\-]\s*(?P<grantor>.{3,180}?)\s+"
            r"grantees?\s*[:\-]\s*(?P<grantee>.{3,180}?)(?:\.|,|\n|$)",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(compact)
        if not match:
            continue
        grantor = _clean_party(match.group("grantor"))
        grantee = _clean_party(match.group("grantee"))
        if grantor and grantee:
            return {"grantor": grantor, "grantee": grantee}
    return {}


def _clean_party(value: str) -> str | None:
    value = re.sub(
        r"\b(?:as\s+)?(?:lessor|lessee|grantor|grantee)\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+", " ", value).strip(" ,;:-")
    return value or None


def _extract_effective_date(text: str):
    compact = re.sub(r"\s+", " ", text)
    patterns = [
        re.compile(
            r"\beffective\s+(?:as\s+of|date\s+of|date|on)?\s*"
            r"(?P<date>[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bcommencement\s+date\s+(?:of\s+)?"
            r"(?P<date>[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            re.IGNORECASE,
        ),
    ]
    for pattern in patterns:
        match = pattern.search(compact)
        if not match:
            continue
        parsed = _parse_extracted_date(match.group("date"))
        if parsed:
            return parsed
    return None


def _parse_extracted_date(value: str):
    parsed = parse_date(value)
    if parsed:
        return parsed
    cleaned = re.sub(r"\s+", " ", value.replace(",", "")).strip()
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    # Title opinion certification dates often carry trailing time/prose, e.g.
    # "December 11, 2012, at 5:00 p.m." — extract the leading "Month DD YYYY"
    # span and parse that, so the date is not silently dropped.
    match = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})", cleaned)
    if match:
        span = f"{match.group(1)} {match.group(2)} {match.group(3)}"
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(span, fmt).date()
            except ValueError:
                continue
    # Numeric M/D/Y anywhere in the string (e.g. "eff. 12/11/2012").
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", value)
    if match:
        month, day, year = (int(g) for g in match.groups())
        year = year + 2000 if year < 100 else year
        try:
            return datetime(year, month, day).date()
        except ValueError:
            pass
    return None


def _extract_acreage(text: str) -> str | None:
    match = re.search(
        r"\b(?P<acres>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s+"
        r"(?:gross\s+|net\s+)?acres?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group('acres')} acres"


def _extract_conveyance(text: str, legal_snippets: list[str]) -> str | None:
    compact = re.sub(r"\s+", " ", text)
    interest_match = re.search(
        r"\b(?P<interest>(?:an?\s+)?(?:undivided\s+)?"
        r"(?:\d+/\d+|\d+(?:\.\d+)?\s*%)\s+"
        r"(?:mineral\s+|royalty\s+|working\s+)?interest)\b",
        compact,
        re.IGNORECASE,
    )
    if not interest_match and not legal_snippets:
        return None
    interest = (
        re.sub(r"\s+", " ", interest_match.group("interest")).strip()
        if interest_match
        else "Interest"
    )
    if legal_snippets:
        return f"{interest}: {legal_snippets[0]}"
    return interest
