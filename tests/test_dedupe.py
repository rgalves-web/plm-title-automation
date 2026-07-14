from src.dedupe import deduplicate_documents
from src.schemas import SourceDocument


def test_duplicate_instrument_number_marks_second_record():
    first = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Patent",
        instrument_number="1001",
    )
    second = SourceDocument(
        source_document_id="DOC-000002",
        source_row_number=3,
        document_type="Patent",
        instrument_number="1001",
    )

    deduplicate_documents([first, second])

    assert first.duplicate_of is None
    assert second.duplicate_of == "DOC-000001"
    assert second.dedupe_confidence == 1.0
