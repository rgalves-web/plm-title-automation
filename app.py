"""PLM Title Automation — Due Diligence (DD) frontend.

Three screens, one flow: drop files, watch it run, get the DDR. No terminal
needed. See dd_upload_runner.run_dd_upload() for what actually executes.
"""
from __future__ import annotations

import queue
import re
import threading
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

import streamlit as st

from src.dd.dd_upload_runner import DDUploadRunResult, run_dd_upload
from src.utils import timestamp

st.set_page_config(page_title="Minorh", layout="wide", initial_sidebar_state="collapsed")

UPLOAD_ROOT = Path("data/working/dd_uploads")
OUTPUT_ROOT = Path("data/output/dd")

# ---------------------------------------------------------------------------
# Brand styling
# ---------------------------------------------------------------------------

_BRAND_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400..700&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #111315 !important;
}
[data-testid="stHeader"] { background-color: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
#MainMenu, footer { visibility: hidden; }

* { color: #FFFFFF; }

h1, h2, h3, .brand-heading {
    font-family: 'Fraunces', serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
}

.brand-sub {
    color: #6B7280 !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 0.95rem;
}

.block-container { max-width: 760px; padding-top: 3.5rem; }

[data-testid="stFileUploaderDropzone"] {
    background-color: #1A1D1F !important;
    border: 1.5px dashed #34383C !important;
    border-radius: 12px !important;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: #9CDB1C !important; }
[data-testid="stFileUploaderDropzoneInstructions"] svg { display: none; }

.stTextArea textarea {
    background-color: #1A1D1F !important;
    border: 1.5px solid #34383C !important;
    border-radius: 12px !important;
    color: #FFFFFF !important;
}
.stTextArea textarea:focus { border-color: #9CDB1C !important; box-shadow: none !important; }

.upload-label {
    font-family: 'Fraunces', serif;
    font-size: 1.05rem;
    font-weight: 600;
    margin-bottom: 0.4rem;
    color: #FFFFFF;
}
.file-count-chip {
    display: inline-block;
    background-color: rgba(156, 219, 28, 0.14);
    color: #9CDB1C;
    border-radius: 999px;
    padding: 0.15rem 0.7rem;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 0.3rem;
}

div.stButton > button, div.stDownloadButton > button {
    background-color: #9CDB1C !important;
    color: #111315 !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    padding: 0.85rem 0 !important;
    width: 100%;
    transition: opacity 0.15s ease;
}
div.stButton > button:hover, div.stDownloadButton > button:hover { opacity: 0.88; }
div.stButton > button:disabled {
    background-color: #2A2D2F !important;
    color: #6B7280 !important;
}

[data-testid="stProgressBar"] div div { background-color: #9CDB1C !important; }
[data-testid="stProgressBar"] { background-color: #1A1D1F !important; border-radius: 8px; }

.feed-box {
    background-color: #1A1D1F;
    border: 1px solid #2A2D2F;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    max-height: 480px;
    overflow-y: auto;
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 0.88rem;
    line-height: 1.85;
}
.feed-row { color: #E5E7EB; }
.feed-row.warn { color: #FBBF24; }
.feed-row.err { color: #F87171; }
.feed-row.working { color: #9CDB1C; }

.section-title {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 1.15rem;
    margin-top: 1.8rem;
    margin-bottom: 0.5rem;
}
.section-title.completed { color: #9CDB1C; }
.section-title.failed { color: #F87171; }
.section-title.review { color: #FBBF24; }

.summary-item {
    background-color: #1A1D1F;
    border-radius: 10px;
    padding: 0.7rem 1rem;
    margin-bottom: 0.5rem;
    font-size: 0.92rem;
    color: #E5E7EB;
}

.empty-note { color: #6B7280; font-size: 0.92rem; margin-top: 0.5rem; }
</style>
"""

st.markdown(_BRAND_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "screen" not in st.session_state:
    st.session_state.screen = "input"
if "feed" not in st.session_state:
    st.session_state.feed = []
if "progress_queue" not in st.session_state:
    st.session_state.progress_queue = queue.Queue()
if "run_thread" not in st.session_state:
    st.session_state.run_thread = None
if "run_result" not in st.session_state:
    st.session_state.run_result = None


def _reset_to_input() -> None:
    st.session_state.screen = "input"
    st.session_state.feed = []
    st.session_state.progress_queue = queue.Queue()
    st.session_state.run_thread = None
    st.session_state.run_result = None


# ---------------------------------------------------------------------------
# Screen 1 — Input
# ---------------------------------------------------------------------------

def render_input_screen() -> None:
    st.markdown("<h1>Minorh</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='brand-sub'>Drop your instructions, documents, and template. We'll handle the rest.</p>",
        unsafe_allow_html=True,
    )
    st.write("")

    st.markdown("<div class='upload-label'>Instructions</div>", unsafe_allow_html=True)
    instructions_text = st.text_area(
        "instructions", label_visibility="collapsed", height=110,
        placeholder="Paste instructions here, or drop a .txt / .pdf file below...",
    )
    instructions_file = st.file_uploader(
        "instructions_file", label_visibility="collapsed", type=["txt", "pdf"], key="instructions_file",
    )

    st.write("")
    st.markdown("<div class='upload-label'>Documents</div>", unsafe_allow_html=True)
    documents = st.file_uploader(
        "documents", label_visibility="collapsed", type=["pdf", "xlsx", "xlsm", "zip"],
        accept_multiple_files=True, key="documents",
    )
    if documents:
        st.markdown(f"<span class='file-count-chip'>{len(documents)} files added</span>", unsafe_allow_html=True)

    st.write("")
    st.markdown("<div class='upload-label'>Template</div>", unsafe_allow_html=True)
    template = st.file_uploader(
        "template", label_visibility="collapsed", type=["xlsx"], key="template",
    )

    st.write("")
    st.markdown("<div class='upload-label'>Unit Name <span style='color:#6B7280;font-size:0.85rem;font-weight:400'>(optional — leave blank to run all units)</span></div>", unsafe_allow_html=True)
    unit_name_filter = st.text_input(
        "unit_name", label_visibility="collapsed",
        placeholder="e.g. BOWEN A UNIT",
    )

    st.write("")
    has_instructions = bool(instructions_text.strip()) or instructions_file is not None
    has_documents = bool(documents)
    has_template = template is not None
    ready = has_instructions and has_documents and has_template

    if st.button("RUN", disabled=not ready, use_container_width=True):
        _start_run(instructions_text, instructions_file, documents, template, unit_name_filter.strip() or None)
        st.rerun()


_TO_FILE_NUM_RE = re.compile(r"^(T0\d{4,})", re.IGNORECASE)


def _extract_pdfs_from_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    """Title opinions often arrive bundled in a zip per file number.  When the
    zip name starts with a T0XXXXX file number (e.g. 'T0141486 (...).zip'),
    every PDF inside is prefixed with that number so filename-based routing can
    identify it as a title opinion regardless of the original PDF name."""
    import zipfile

    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    m = _TO_FILE_NUM_RE.match(zip_path.stem)
    file_number_prefix = m.group(1).upper() if m else None

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".pdf"):
                continue
            original_name = Path(info.filename).name
            if file_number_prefix and not _TO_FILE_NUM_RE.match(original_name):
                target_name = f"{file_number_prefix} - {original_name}"
            else:
                target_name = original_name
            target = dest_dir / target_name
            if not target.exists():
                with zf.open(info) as src, target.open("wb") as out:
                    out.write(src.read())
            extracted.append(target)
    return extracted


def _start_run(instructions_text, instructions_file, documents, template, unit_name_filter=None) -> None:
    run_id = timestamp()
    run_dir = UPLOAD_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    instructions_value = instructions_text.strip()
    if instructions_file is not None:
        instructions_path = run_dir / instructions_file.name
        instructions_path.write_bytes(instructions_file.getvalue())
        if instructions_file.name.lower().endswith(".txt"):
            instructions_value = instructions_path.read_text(encoding="utf-8", errors="replace")

    document_paths = []
    for uploaded in documents:
        dest = run_dir / uploaded.name
        dest.write_bytes(uploaded.getvalue())
        if dest.suffix.lower() == ".zip":
            document_paths.extend(_extract_pdfs_from_zip(dest, run_dir / "_extracted" / dest.stem))
        else:
            document_paths.append(dest)

    template_path = run_dir / template.name
    template_path.write_bytes(template.getvalue())

    output_root = OUTPUT_ROOT / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    progress_q = st.session_state.progress_queue

    def callback(icon: str, message: str) -> None:
        progress_q.put((icon, message))

    def worker() -> None:
        try:
            result = run_dd_upload(
                document_paths=document_paths,
                ddr_template_path=template_path,
                output_root=output_root,
                instructions_text=instructions_value,
                progress_callback=callback,
                unit_name_filter=unit_name_filter,
            )
            progress_q.put(("__done__", result))
        except Exception as exc:  # last-resort guard so the UI never hangs silently
            progress_q.put(("err", f"Unexpected failure: {exc}"))
            progress_q.put(("__done__", DDUploadRunResult(routed=None, fatal_error=str(exc))))

    thread = threading.Thread(target=worker, daemon=True)
    st.session_state.run_thread = thread
    st.session_state.screen = "progress"
    thread.start()


# ---------------------------------------------------------------------------
# Screen 2 — Progress
# ---------------------------------------------------------------------------

ICONS = {"ok": "✅", "working": "⏳", "warn": "⚠️", "err": "❌"}


@st.fragment(run_every=0.6)
def render_progress_fragment() -> None:
    q = st.session_state.progress_queue
    while True:
        try:
            icon, payload = q.get_nowait()
        except queue.Empty:
            break
        if icon == "__done__":
            st.session_state.run_result = payload
        else:
            st.session_state.feed.append((icon, payload))

    feed = st.session_state.feed
    done_count = sum(1 for icon, _ in feed if icon in ("ok", "warn", "err"))
    if st.session_state.run_result is not None:
        pct = 1.0
    else:
        pct = min(0.95, done_count / max(done_count + 3, 6))

    st.progress(pct)

    rows_html = []
    for icon, message in feed[-300:]:
        rows_html.append(f"<div class='feed-row {icon}'>{ICONS.get(icon, '')} {message}</div>")
    st.markdown(f"<div class='feed-box'>{''.join(rows_html) or 'Starting...'}</div>", unsafe_allow_html=True)

    if st.session_state.run_result is not None:
        st.session_state.screen = "complete"
        st.rerun()


def render_progress_screen() -> None:
    st.markdown("<h1>Processing</h1>", unsafe_allow_html=True)
    st.write("")
    render_progress_fragment()


# ---------------------------------------------------------------------------
# Screen 3 — Completion
# ---------------------------------------------------------------------------

def render_completion_screen() -> None:
    result: DDUploadRunResult = st.session_state.run_result

    st.markdown("<h1>Summary</h1>", unsafe_allow_html=True)
    st.write("")

    completed_items: list[str] = []
    failed_items: list[str] = []
    review_items: list[str] = []
    downloadable_paths: list[Path] = []

    if result.fatal_error:
        failed_items.append(result.fatal_error)
    else:
        for outcome in result.unit_outcomes:
            if outcome.error:
                failed_items.append(f"Unit {outcome.unit_name} — {outcome.error}")
                continue
            r = outcome.result
            summary = r.summary
            wi_status = summary["reconciliation_wi_status"]
            nri_status = summary["reconciliation_nri_status"]
            completed_items.append(
                f"Unit {outcome.unit_name} — {summary['title_opinions_total']} title opinion(s) processed"
            )
            if wi_status == "NOT_COMPUTED" or nri_status == "NOT_COMPUTED":
                review_items.append(
                    f"Unit {outcome.unit_name} — WI/NRI reconciliation against the Well List was "
                    f"NOT computed (missing unit gross acres and/or Well List interest data)"
                )
            else:
                completed_items.append(f"Unit {outcome.unit_name} — WI {wi_status}, NRI {nri_status}")
            if summary["title_opinions_no_pdf"]:
                review_items.append(
                    f"Unit {outcome.unit_name} — {summary['title_opinions_no_pdf']} title opinion(s) "
                    f"had no source PDF and were skipped"
                )
            for exc in r.qa_exceptions:
                line = f"{exc.source_document_id or outcome.unit_name} — {exc.message}"
                if exc.severity == "ERROR":
                    failed_items.append(line)
                else:
                    review_items.append(line)
            downloadable_paths.append(r.ddr_result.output_path)

    st.markdown("<div class='section-title completed'>✅ COMPLETED</div>", unsafe_allow_html=True)
    if completed_items:
        for item in completed_items:
            st.markdown(f"<div class='summary-item'>{item}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='empty-note'>Nothing completed.</p>", unsafe_allow_html=True)

    st.markdown("<div class='section-title failed'>❌ NOT COMPLETED</div>", unsafe_allow_html=True)
    if failed_items:
        for item in failed_items:
            st.markdown(f"<div class='summary-item'>{item}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='empty-note'>No failures.</p>", unsafe_allow_html=True)

    st.markdown("<div class='section-title review'>⚠️ NEEDS REVIEW</div>", unsafe_allow_html=True)
    if review_items:
        for item in review_items:
            st.markdown(f"<div class='summary-item'>{item}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='empty-note'>Nothing flagged.</p>", unsafe_allow_html=True)

    st.write("")
    if downloadable_paths:
        if len(downloadable_paths) == 1:
            path = downloadable_paths[0]
            st.download_button(
                "⬇ Download DDR", data=path.read_bytes(), file_name=path.name,
                use_container_width=True,
            )
        else:
            import io
            import zipfile
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                for path in downloadable_paths:
                    zf.write(path, arcname=path.name)
            st.download_button(
                "⬇ Download DDRs (.zip)", data=buf.getvalue(), file_name="ddr_filled.zip",
                use_container_width=True,
            )
    else:
        st.markdown(
            "<p class='empty-note'>No DDR could be produced — see Not Completed above for why.</p>",
            unsafe_allow_html=True,
        )

    st.write("")
    if st.button("Start a new run", use_container_width=True):
        _reset_to_input()
        st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

if st.session_state.screen == "input":
    render_input_screen()
elif st.session_state.screen == "progress":
    render_progress_screen()
elif st.session_state.screen == "complete":
    render_completion_screen()
