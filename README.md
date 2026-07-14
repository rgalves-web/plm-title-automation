# PLM Title Automation

Local MVP for audit-ready PLM/Arapahoe title document processing. The first version is deterministic and reviewable: it ingests a Document List, builds a Document Register, deduplicates likely duplicates, classifies rows by configurable rules, writes a preliminary runsheet into a copied Excel template, and produces QA workbooks.

## What This MVP Does

- Reads Document List files from `.xlsx`, `.xls`, or `.csv`.
- Creates a source-traceable `document_register.xlsx`.
- Marks likely duplicates without dropping the source row.
- Classifies documents as `INCLUDE_FULL`, `INCLUDE_LIMITED`, `REDLINE`, `REVIEW`, or `DUPLICATE`.
- Preserves ALM/GAC redline behavior: non-applicable documents remain accounted for and are placed at the bottom of the runsheet in red.
- Copies the provided template workbook and writes only to the detected runsheet sheet.
- Exports `redline_rows.xlsx`, `review_required.xlsx`, `QA_EXCEPTION_LOG.xlsx`, and `processing_summary.json`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Tesseract OCR (required for scanned documents)

OCR of scanned PDFs and image files requires the Tesseract binary in addition to the
`pytesseract` Python package.

**Windows** — install via winget (recommended):

```powershell
winget install UB-Mannheim.TesseractOCR
```

The app auto-detects `C:\Program Files\Tesseract-OCR\tesseract.exe`; no PATH change
needed.  Alternatively add the install directory to your PATH.

**macOS:**

```bash
brew install tesseract
```

**Linux (Debian/Ubuntu):**

```bash
sudo apt install tesseract-ocr
```

Without Tesseract, PDFs that contain only scanned images will be marked
`OCR_REQUIRED` and pushed to REVIEW instead of being extracted.

## Run The App

```powershell
streamlit run app.py
```

Or double-click `run_app.bat` from Windows Explorer.

Uploads are configured for up to 2 GB per file in `.streamlit/config.toml`.

If browser upload fails for a large ZIP, place it manually in `data/input/document_packages/` and select it from the sidebar.

## Generate Sample Files

```powershell
python scripts\generate_sample_data.py
```

The sample files are written to `data/input/sample/` and include a small Document List plus a template workbook that matches `config/template_map.yaml`.

## Golden Set Workflow

After review, use the app's `Golden Set` tab to mark corrected classifications and corrected runsheet rows as approved examples. Approved classification examples are stored in `data/golden_set/golden_classifications.csv`; approved runsheet rows are stored in `data/golden_set/golden_runsheet_rows.csv`.

The Golden Set tab can compare current classifier output against approved classification examples and report drift. The same regression check is covered by the unit tests.

## Run Tests

```powershell
pytest
```

## Configuration

- `config/rules.yaml`: deterministic classification keywords and precedence.
- `config/template_map.yaml`: runsheet sheet names, header aliases, required columns, and redline fill color.
- `config/terminology.yaml`: workflow/status labels and QA severity names.

## Notes For Future Extraction

This MVP intentionally avoids paid OCR or AI services. `src/pdf_reader.py` provides local PDF text extraction and TODO stubs where Azure Document Intelligence, AWS Textract, LlamaParse, or OpenAI extraction can later be plugged in without changing the audit model.
