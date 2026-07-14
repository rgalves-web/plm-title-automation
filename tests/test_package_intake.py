from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from src.document_register import create_document_register, detect_column_mapping
from src.intake import read_document_list_from_package


def test_read_document_list_from_package_prefers_largest_and_enriches_rows(tmp_path):
    zip_path = tmp_path / "package.zip"
    small = pd.DataFrame(
        [
            {
                "Reception Number": "100-2020",
                "Recording Date": "01/01/2020",
                "Doc Type": "PAT",
                "Grantor": "United States",
                "Grantee": "Owner",
            }
        ]
    )
    large = pd.DataFrame(
        [
            {
                "Reception Number": "100-2020",
                "Recording Date": "01/01/2020",
                "Doc Type": "PAT",
                "Grantor": "United States",
                "Grantee": "Owner",
            },
            {
                "Reception Number": "200-2020",
                "Recording Date": "01/02/2020",
                "Doc Type": "DEDMIN",
                "Grantor": "A",
                "Grantee": "B",
            },
        ]
    )

    with ZipFile(zip_path, "w") as archive:
        archive.writestr("old/Section-DocumentList.csv", small.to_csv(index=False))
        archive.writestr("new/Section-DocumentList.csv", large.to_csv(index=False))
        archive.writestr("new/images/AR100-2020.pdf", b"%PDF-1.4\n")
        archive.writestr("new/images/AR200-2020.pdf", b"%PDF-1.4\n")

    result = read_document_list_from_package(zip_path)
    mapping = detect_column_mapping(result.dataframe)[0]
    records = create_document_register(result.dataframe, column_mapping=mapping)

    assert result.row_count == 2
    assert result.member_name == "new/Section-DocumentList.csv"
    assert result.dataframe.loc[0, "Document Type"] == "Patent"
    assert result.dataframe.loc[1, "Document Type"] == "Mineral Deed"
    assert result.dataframe.loc[1, "Original File Name"] == "new/images/AR200-2020.pdf"
    assert records[0].document_type == "Patent"
    assert records[1].document_type == "Mineral Deed"
