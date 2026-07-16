from pathlib import Path

import pytest

from src.pdf_reader import (
    LOW_CONFIDENCE_TEXT,
    OCR_REQUIRED,
    TEXT_EXTRACTED,
    apply_extraction_to_record,
    extract_pdf,
)
from src.schemas import ClassificationStatus, SourceDocument


fitz = pytest.importorskip("fitz")


def _write_pdf(path: Path, pages: list[str]) -> Path:
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_textbox((72, 72, 540, 720), text, fontsize=11)
    document.save(path)
    document.close()
    return path


def test_extract_pdf_structured_metadata_and_snippets(tmp_path):
    pdf_path = _write_pdf(
        tmp_path / "lease.pdf",
        [
            (
                "Oil and Gas Lease between Jane Smith, a widow, and PLM Energy LLC. "
                "Legal Description: Section 1 Township 4S Range 64W, Arapahoe County, Colorado. "
                "This lease has a primary term of 5 years and as long thereafter as oil or gas is produced. "
                "This text is long enough to be useful for extraction confidence but remains a possible signal only."
            )
        ],
    )

    result = extract_pdf(pdf_path)

    assert result.page_count == 1
    assert result.extraction_status == TEXT_EXTRACTED
    assert result.extraction_confidence >= 0.55
    assert "Oil and Gas Lease" in result.possible_document_type_keywords
    assert any(
        "Section 1 Township 4S Range 64W" in snippet
        for snippet in result.possible_legal_description_snippets
    )
    assert any(
        "primary term of 5 years" in snippet
        for snippet in result.possible_lease_primary_term_snippets
    )
    assert "Oil and Gas Lease" in result.text_preview


def test_blank_pdf_marks_needs_review(tmp_path):
    """A blank/image-only PDF must push the record to REVIEW regardless of OCR availability.

    With Tesseract installed: blank page → OCR runs → no useful text → LOW_CONFIDENCE_TEXT.
    Without Tesseract: → OCR_REQUIRED.  Both are non-TEXT_EXTRACTED and require review.
    """
    pdf_path = _write_pdf(tmp_path / "blank.pdf", [""])
    result = extract_pdf(pdf_path)

    assert result.page_count == 1
    assert result.extraction_status in {OCR_REQUIRED, LOW_CONFIDENCE_TEXT}
    assert result.extraction_confidence == 0.0
    assert result.review_required is True

    record = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Unknown",
    )
    apply_extraction_to_record(record, result)

    assert record.pdf_extraction_status in {OCR_REQUIRED, LOW_CONFIDENCE_TEXT}
    assert record.status == ClassificationStatus.REVIEW
    assert record.review_question


def test_low_confidence_text_marks_review_without_final_legal_conclusion(tmp_path):
    pdf_path = _write_pdf(
        tmp_path / "weak.pdf",
        ["Patent Section 1 Township 4S Range 64W."],
    )
    result = extract_pdf(pdf_path)

    assert result.extraction_status == LOW_CONFIDENCE_TEXT
    assert result.review_required is True
    assert "Patent" in result.possible_document_type_keywords

    record = SourceDocument(
        source_document_id="DOC-000002",
        source_row_number=3,
    )
    apply_extraction_to_record(record, result)

    assert record.status == ClassificationStatus.REVIEW
    assert record.document_type is None
    assert record.classification_reason is None
    assert record.possible_document_type_keywords == ["Patent"]


# ---------------------------------------------------------------------------
# Multi-page image OCR (Maxwell lessons item 3)
# Recorded instruments are multi-page TIFs — a Declaration of Pooled Unit and
# its Exhibit "A" lease schedule, a recorded lease and its exhibits. PIL opens
# such a file on frame 0, so OCR'ing the image object read page 1 and silently
# dropped the rest: the real Maxwell DPU yielded 1 page / 4,673 chars instead of
# 8 pages / 13,774, losing the entire lease schedule.
# ---------------------------------------------------------------------------

def _fake_pytesseract(counter: list[int]):
    import types

    def image_to_string(image, **_kwargs):
        counter.append(1)
        return f"PAGE{len(counter)} TEXT with enough words to look like a real document body"

    module = types.ModuleType("pytesseract")
    module.image_to_string = image_to_string
    module.pytesseract = types.SimpleNamespace(tesseract_cmd="tesseract")
    return module


def _write_multipage_tif(path: Path, frames: int):
    PILImage = pytest.importorskip("PIL.Image")
    images = [PILImage.new("1", (60, 40), 1) for _ in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:])
    return path


def test_multipage_tiff_ocrs_every_frame(tmp_path, monkeypatch):
    import sys

    from src.pdf_reader import extract_document

    pytest.importorskip("PIL")
    tif = _write_multipage_tif(tmp_path / "unit_dec.tif", frames=8)
    monkeypatch.setitem(sys.modules, "pytesseract", _fake_pytesseract([]))

    result = extract_document(tif)

    assert result.page_count == 8, "every frame of a multi-page TIF must be OCR'd"
    assert "PAGE1" in result.full_text
    assert "PAGE8" in result.full_text, "later pages (the Exhibit A schedule) must not be dropped"


def test_singlepage_tiff_still_reports_one_page(tmp_path, monkeypatch):
    import sys

    from src.pdf_reader import extract_document

    pytest.importorskip("PIL")
    tif = _write_multipage_tif(tmp_path / "one.tif", frames=1)
    monkeypatch.setitem(sys.modules, "pytesseract", _fake_pytesseract([]))

    result = extract_document(tif)
    assert result.page_count == 1
    assert "PAGE1" in result.full_text


def test_multipage_tiff_pages_use_the_same_separator_as_pdf_ocr(tmp_path, monkeypatch):
    import sys

    from src.pdf_reader import extract_document

    pytest.importorskip("PIL")
    tif = _write_multipage_tif(tmp_path / "three.tif", frames=3)
    monkeypatch.setitem(sys.modules, "pytesseract", _fake_pytesseract([]))

    result = extract_document(tif)
    assert result.full_text.count("\f") == 2  # N pages -> N-1 separators
