from src.document_register import records_to_dataframe
from src.golden_set import (
    append_golden_classifications,
    append_golden_runsheet_rows,
    compare_classifier_to_golden,
    golden_classifications_path,
    golden_runsheet_rows_path,
    load_golden_classifications,
    load_golden_runsheet_rows,
    prepare_classification_approval_table,
    prepare_runsheet_approval_table,
)
from src.schemas import ClassificationStatus, SourceDocument


def _patent_record() -> SourceDocument:
    return SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Patent",
        document_title="United States Patent",
        instrument_number="1001",
        grantor="United States of America",
        grantee="John Smith, a married man",
        status=ClassificationStatus.INCLUDE_FULL,
    )


def test_approved_examples_are_saved_to_golden_csvs(tmp_path):
    register_df = records_to_dataframe([_patent_record()])

    classification_df = prepare_classification_approval_table(register_df)
    classification_df.loc[0, "approved"] = True
    classification_df.loc[0, "status"] = "REVIEW"
    classification_df.loc[0, "review_question"] = "Reviewer corrected classification."

    runsheet_df = prepare_runsheet_approval_table(register_df)
    runsheet_df.loc[0, "approved"] = True
    runsheet_df.loc[0, "comments"] = "Reviewer corrected extracted comment."

    classification_count = append_golden_classifications(
        classification_df,
        golden_dir=tmp_path,
        project_name="Golden Test",
    )
    runsheet_count = append_golden_runsheet_rows(
        runsheet_df,
        golden_dir=tmp_path,
        project_name="Golden Test",
    )

    assert classification_count == 1
    assert runsheet_count == 1
    assert golden_classifications_path(tmp_path).exists()
    assert golden_runsheet_rows_path(tmp_path).exists()

    classifications = load_golden_classifications(tmp_path)
    runsheet_rows = load_golden_runsheet_rows(tmp_path)

    assert classifications.loc[0, "expected_status"] == "REVIEW"
    assert classifications.loc[0, "expected_review_question"] == "Reviewer corrected classification."
    assert runsheet_rows.loc[0, "comments"] == "Reviewer corrected extracted comment."


def test_classifier_regression_passes_when_golden_set_matches(tmp_path):
    register_df = records_to_dataframe([_patent_record()])
    approval_df = prepare_classification_approval_table(register_df)
    approval_df.loc[0, "approved"] = True

    append_golden_classifications(approval_df, golden_dir=tmp_path)

    report = compare_classifier_to_golden(tmp_path)

    assert report["passed"] is True
    assert report["total_examples"] == 1
    assert report["drift_count"] == 0
    assert report["drifts"] == []


def test_classifier_regression_reports_drift_against_golden_set(tmp_path):
    register_df = records_to_dataframe([_patent_record()])
    approval_df = prepare_classification_approval_table(register_df)
    approval_df.loc[0, "approved"] = True
    approval_df.loc[0, "status"] = "REDLINE"
    approval_df.loc[0, "redline_reason"] = "Reviewer intentionally changed expected output."

    append_golden_classifications(approval_df, golden_dir=tmp_path)

    report = compare_classifier_to_golden(tmp_path)

    assert report["passed"] is False
    assert report["total_examples"] == 1
    assert report["drift_count"] >= 1
    assert any(
        drift["field"] == "status"
        and drift["expected"] == "REDLINE"
        and drift["actual"] == "INCLUDE_FULL"
        for drift in report["drifts"]
    )
