from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from shutil import copyfileobj
from typing import BinaryIO
from zipfile import ZipFile
import re

import pandas as pd


DOCUMENT_LIST_NAME_MARKERS = ("documentlist", "document_list", "document list")
ARAPAHOE_DOC_TYPE_MAP = {
    "AFF": "Affidavit",
    "AFFIDN": "Affidavit",
    "AGR": "Agreement",
    "AGRMOD": "Agreement Modification",
    "AGRSUB": "Agreement Subordination",
    "ASN": "Assignment",
    "ASNCOR": "Correction Assignment",
    "DED": "Deed",
    "DEDMIN": "Mineral Deed",
    "DEDPRP": "Personal Representative Deed",
    "DEDPTR": "Public Trustee's Deed",
    "DEDQCL": "Quit Claim Deed",
    "DEDWAR": "Warranty Deed",
    "EAS": "Easement",
    "EASASN": "Assignment of Easement",
    "EASMOD": "Easement Modification",
    "EASREL": "Release of Easement",
    "EASROW": "Right of Way Easement",
    "EASUTL": "Utility Easement",
    "JDG": "Judgment",
    "LEN": "Lien",
    "LENREL": "Release of Lien",
    "LIS": "Lis Pendens",
    "LISREL": "Release of Lis Pendens",
    "LSE": "Lease",
    "MLN": "Mechanic's Lien",
    "MLNREL": "Release of Mechanic's Lien",
    "MTG": "Mortgage",
    "MTGASN": "Assignment of Mortgage",
    "MTGMOD": "Mortgage Modification",
    "MTGPRL": "Partial Release of Mortgage",
    "MTGREL": "Release of Mortgage",
    "MTGSUB": "Mortgage Subordination",
    "MTGSUP": "Mortgage Supplement",
    "OGL": "Oil and Gas Lease",
    "OGLAFF": "Affidavit regarding Oil and Gas Lease",
    "OGLASN": "Assignment of Oil and Gas Lease",
    "OGLDOC": "Oil and Gas Lease Document",
    "OGLMOD": "Modification of Oil and Gas Lease",
    "OGLMTG": "Mortgage of Oil and Gas Lease",
    "OGLPRL": "Partial Release of Oil and Gas Lease",
    "OGLRAT": "Ratification of Oil and Gas Lease",
    "OGLREL": "Release of Oil and Gas Lease",
    "OGLUCC": "UCC Oil and Gas Lease",
    "PAT": "Patent",
    "POL": "Pooling Agreement",
    "POLAMD": "Pooling Agreement Amendment",
    "REL": "Release",
    "ROYASN": "Assignment of Royalty",
    "ROYDED": "Royalty Deed",
    "TDD": "Deed of Trust",
    "TDDAMD": "Amendment of Deed of Trust",
    "TDDASN": "Assignment of Deed of Trust",
    "TDDMOD": "Modification of Deed of Trust",
    "TDDPRL": "Partial Release of Deed of Trust",
    "TDDREL": "Release of Deed of Trust",
    "TDDSUB": "Subordination of Deed of Trust",
    "UCC": "UCC Financing Statement",
    "UCCAMD": "UCC Amendment",
    "UCCASN": "UCC Assignment",
    "UCCTER": "UCC Termination",
}


@dataclass
class PackageDocumentList:
    dataframe: pd.DataFrame
    member_name: str
    row_count: int


def read_document_list(file_or_path: str | Path | BinaryIO) -> pd.DataFrame:
    name = getattr(file_or_path, "name", str(file_or_path))
    suffix = Path(name).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(file_or_path)
    if suffix == ".csv":
        return pd.read_csv(file_or_path)
    raise ValueError(f"Unsupported Document List type: {suffix or name}")


def find_document_lists_in_package(zip_path: str | Path) -> list[str]:
    zip_path = Path(zip_path)
    with ZipFile(zip_path) as archive:
        candidates = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            name = Path(info.filename).name.lower()
            if suffix not in {".xlsx", ".xlsm", ".xls", ".csv"}:
                continue
            if any(marker in name for marker in DOCUMENT_LIST_NAME_MARKERS):
                candidates.append(info.filename)
        return candidates


def read_document_list_from_package(
    zip_path: str | Path,
    member_name: str | None = None,
) -> PackageDocumentList:
    zip_path = Path(zip_path)
    with ZipFile(zip_path) as archive:
        candidates = [member_name] if member_name else find_document_lists_in_package(zip_path)
        if not candidates:
            raise ValueError(f"No Document List XLSX/CSV found inside {zip_path.name}.")

        best: PackageDocumentList | None = None
        for candidate in candidates:
            with archive.open(candidate) as handle:
                payload = BytesIO(handle.read())
                payload.name = Path(candidate).name
                dataframe = read_document_list(payload)
                dataframe = enrich_document_list_from_package(dataframe, archive)
            result = PackageDocumentList(
                dataframe=dataframe,
                member_name=candidate,
                row_count=len(dataframe),
            )
            if best is None or result.row_count > best.row_count:
                best = result

    if best is None:
        raise ValueError(f"No readable Document List found inside {zip_path.name}.")
    return best


def enrich_document_list_from_package(dataframe: pd.DataFrame, archive: ZipFile) -> pd.DataFrame:
    dataframe = dataframe.copy()
    if "Doc Type" in dataframe.columns:
        dataframe["Raw Doc Type"] = dataframe["Doc Type"].fillna("").astype(str)
        if "Document Type" not in dataframe.columns:
            dataframe["Document Type"] = dataframe["Raw Doc Type"].map(
                lambda value: ARAPAHOE_DOC_TYPE_MAP.get(value.strip().upper(), value)
            )

    if "Reception Number" in dataframe.columns and "Original File Name" not in dataframe.columns:
        pdf_index = _package_pdf_index(archive)
        dataframe["Original File Name"] = dataframe["Reception Number"].map(
            lambda value: pdf_index.get(_document_number_key(value), "")
        )
    return dataframe


def build_document_list_from_package_files(zip_path: str | Path) -> PackageDocumentList:
    zip_path = Path(zip_path)
    rows = []
    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
                continue
            rows.append(
                {
                    "Document Title": Path(info.filename).stem,
                    "File Name": info.filename,
                    "Original File Name": info.filename,
                    "File Size": info.file_size,
                    "Doc Type": "",
                    "Comments": "Created from document package file listing; no Document List was found.",
                }
            )
    dataframe = pd.DataFrame(rows)
    return PackageDocumentList(
        dataframe=dataframe,
        member_name=f"{zip_path.name} file listing",
        row_count=len(dataframe),
    )


def _package_pdf_index(archive: ZipFile) -> dict[str, str]:
    index: dict[str, str] = {}
    for info in archive.infolist():
        if info.is_dir() or Path(info.filename).suffix.lower() != ".pdf":
            continue
        key = _document_number_key(Path(info.filename).stem)
        if key and key not in index:
            index[key] = info.filename
    return index


def _document_number_key(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    text = re.sub(r"^[A-Za-z]+", "", Path(text).stem)
    return re.sub(r"[^0-9]", "", text)


def save_uploaded_file(uploaded_file, output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / Path(uploaded_file.name).name
    with output_path.open("wb") as handle:
        uploaded_file.seek(0)
        copyfileobj(uploaded_file, handle, length=1024 * 1024 * 8)
    return output_path
