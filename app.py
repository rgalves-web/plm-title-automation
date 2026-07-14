"""Minorh — Due Diligence Report (DDR) builder.

Three screens, one flow: point at a unit folder (or upload its files), watch it
run, download the DDR. The deterministic DD pipeline is untouched; this module
is only the branded surface over dd_upload_runner.run_dd_upload().
"""
from __future__ import annotations

import queue
import re
import threading
import zipfile
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

import streamlit as st

from src.dd.dd_upload_runner import DDUploadRunResult, run_dd_upload
from src.utils import timestamp

st.set_page_config(page_title="minorh — Due Diligence", layout="wide", initial_sidebar_state="collapsed")

UPLOAD_ROOT = Path("data/working/dd_uploads")
OUTPUT_ROOT = Path("data/output/dd")

# ---------------------------------------------------------------------------
# Minorh brand
# ---------------------------------------------------------------------------

_BRAND_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@1,9..144,900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --g900:#111315; --g800:#181B1F; --g700:#23272D;
  --paper:#EDF1F4; --gray400:#97A1AB; --gray500:#69737D;
  --lime:#9CDB1C;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
  background-color: var(--g900) !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"] { display:none !important; }
#MainMenu, footer, [data-testid="stDecoration"] { display:none !important; visibility:hidden; }

*, .stMarkdown, p, span, div, label { font-family:'Inter', -apple-system, 'Segoe UI', sans-serif; color:var(--paper); }
.block-container { max-width: 780px; padding-top: 3rem; padding-bottom: 4rem; }

/* Display headline — Fraunces 900 italic, once per screen. */
.headline { font-family:'Fraunces', serif; font-weight:900; font-style:italic;
  font-size: 2.6rem; line-height:1.05; letter-spacing:-0.015em; margin:0 0 .35rem 0; color:var(--paper); }
.headline .dot { color:var(--lime); }
.subhead { color:var(--gray400); font-size:0.98rem; margin:0 0 1.6rem 0; }

/* Micro-labels — uppercase Inter, Gray 400. */
.label { font-size:0.72rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase;
  color:var(--gray400); margin:1.3rem 0 0.45rem 0; }
.hint { color:var(--gray500); font-size:0.8rem; font-weight:400; text-transform:none; letter-spacing:0; }

/* Data — JetBrains Mono for anything verifiable. */
.mono, .mono * { font-family:'JetBrains Mono', monospace !important; }

/* Inputs */
.stTextInput input, .stTextArea textarea {
  background-color:var(--g800) !important; border:1px solid var(--g700) !important;
  border-radius:6px !important; color:var(--paper) !important; font-family:'Inter',sans-serif !important; }
.stTextInput input:focus, .stTextArea textarea:focus {
  outline:2px solid var(--lime) !important; outline-offset:3px !important; border-color:var(--g700) !important; box-shadow:none !important; }
[data-testid="stFileUploaderDropzone"] {
  background-color:var(--g800) !important; border:1px dashed var(--g700) !important; border-radius:6px !important; }
[data-testid="stFileUploaderDropzone"]:hover { border-color:var(--gray500) !important; }
[data-testid="stFileUploaderDropzoneInstructions"] svg { display:none; }

/* Buttons — one lime primary per screen; radius 6px. Secondary = bordered ghost. */
div.stButton > button {
  background-color:var(--lime) !important; color:var(--g900) !important; border:none !important;
  border-radius:6px !important; font-weight:600 !important; font-size:0.95rem !important;
  padding:0.7rem 0 !important; width:100%; transition:opacity .15s ease; }
div.stButton > button:hover { opacity:0.9; }
div.stButton > button:disabled { background-color:var(--g700) !important; color:var(--gray500) !important; }
div.stButton > button:focus-visible { outline:2px solid var(--lime) !important; outline-offset:3px !important; }
/* Secondary buttons (Streamlit 'secondary' kind) */
div.stButton > button[kind="secondary"] {
  background-color:transparent !important; color:var(--paper) !important; border:1px solid var(--g700) !important; font-weight:500 !important; }
div.stDownloadButton > button {
  background-color:var(--lime) !important; color:var(--g900) !important; border:none !important;
  border-radius:6px !important; font-weight:600 !important; padding:0.7rem 0 !important; width:100%; }
div.stDownloadButton > button:focus-visible { outline:2px solid var(--lime) !important; outline-offset:3px !important; }

/* Progress */
[data-testid="stProgressBar"] > div > div { background-color:var(--lime) !important; }
[data-testid="stProgressBar"] > div { background-color:var(--g700) !important; border-radius:4px; }

.feed { background-color:var(--g800); border:1px solid var(--g700); border-radius:6px;
  padding:1rem 1.15rem; max-height:460px; overflow-y:auto; font-size:0.86rem; line-height:1.9; }
.feed .row { color:var(--paper); border-bottom:1px solid var(--g700); padding:0.12rem 0; }
.feed .row:last-child { border-bottom:none; }
.feed .row.working { color:var(--gray400); }
.feed .row.warn { color:#E6B450; }
.feed .row.err { color:#E0685E; }
.feed .row .mono { color:var(--lime); }

/* Completion sections + cards (no zebra; hairline separated) */
.sec { font-size:0.72rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase;
  color:var(--gray400); margin:1.6rem 0 0.6rem 0; }
.card { background-color:var(--g800); border:1px solid var(--g700); border-radius:6px;
  padding:0.7rem 0.9rem; margin-bottom:0.5rem; font-size:0.9rem; color:var(--paper); }
.card .cite { color:var(--gray500); font-family:'JetBrains Mono',monospace; font-size:0.78rem; }
.card .val { color:var(--lime); font-family:'JetBrains Mono',monospace; }
.muted { color:var(--gray500); font-size:0.88rem; }
.divider { height:1px; background:var(--g700); margin:1.4rem 0; border:none; }
</style>
"""

st.markdown(_BRAND_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

for key, default in (
    ("screen", "input"), ("feed", None), ("progress_queue", None),
    ("run_thread", None), ("run_result", None),
):
    if key not in st.session_state:
        st.session_state[key] = [] if key == "feed" else (queue.Queue() if key == "progress_queue" else default)


def _reset_to_input() -> None:
    st.session_state.screen = "input"
    st.session_state.feed = []
    st.session_state.progress_queue = queue.Queue()
    st.session_state.run_thread = None
    st.session_state.run_result = None


# ---------------------------------------------------------------------------
# Folder + upload input handling
# ---------------------------------------------------------------------------

_TO_FILE_NUM_RE = re.compile(r"^(T0\d{4,})", re.IGNORECASE)
_DDR_TEMPLATE_RE = re.compile(r"ddr.*template|template.*ddr", re.IGNORECASE)


def _extract_pdfs_from_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    """Flatten a zip's PDFs; prefix members with a leading T0##### file number
    from the zip name so filename-based routing still recognizes them."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    m = _TO_FILE_NUM_RE.match(zip_path.stem)
    prefix = m.group(1).upper() if m else None
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".pdf"):
                continue
            name = Path(info.filename).name
            target = dest_dir / (f"{prefix} - {name}" if prefix and not _TO_FILE_NUM_RE.match(name) else name)
            if not target.exists():
                with zf.open(info) as src, target.open("wb") as out:
                    out.write(src.read())
            extracted.append(target)
    return extracted


def enumerate_folder(folder: Path, extract_dir: Path) -> tuple[list[Path], Path | None]:
    """Turn a local folder into (document_paths, ddr_template_path): every PDF
    and workbook (zips flattened), with the DDR template pulled aside. Mirrors
    the uploader's behavior so folder and upload paths feed the pipeline
    identically."""
    documents: list[Path] = []
    template: Path | None = None
    for path in sorted(folder.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        if suffix == ".zip":
            documents.extend(_extract_pdfs_from_zip(path, extract_dir / path.stem))
        elif suffix == ".pdf":
            documents.append(path)
        elif suffix in (".xlsx", ".xlsm"):
            if template is None and _DDR_TEMPLATE_RE.search(path.name):
                template = path
            else:
                documents.append(path)
    return documents, template


# ---------------------------------------------------------------------------
# Screen 1 — Input
# ---------------------------------------------------------------------------

def render_input_screen() -> None:
    st.markdown("<div class='headline'>minorh<span class='dot'>.</span></div>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subhead'>Build a Due Diligence Report (DDR) for a unit. Point at the unit's "
        "local folder, or upload its files.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("<div class='label'>Unit folder <span class='hint'>local path — reference workbooks, "
                "title opinions, and the DDR template</span></div>", unsafe_allow_html=True)
    folder_path = st.text_input("folder", label_visibility="collapsed",
                                placeholder=r"C:\...\MAXWELL A UNIT")

    st.markdown("<div class='label'>Unit name <span class='hint'>optional — blank runs every unit "
                "in the Project Log</span></div>", unsafe_allow_html=True)
    unit_name = st.text_input("unit", label_visibility="collapsed", placeholder="MAXWELL A UNIT")

    st.markdown("<div class='label'>Instructions <span class='hint'>optional</span></div>", unsafe_allow_html=True)
    instructions_text = st.text_area("instructions", label_visibility="collapsed", height=90,
                                     placeholder="Scope or notes for this unit.")

    with st.expander("Upload files instead of a folder"):
        documents = st.file_uploader("documents", label_visibility="collapsed",
                                     type=["pdf", "xlsx", "xlsm", "zip"],
                                     accept_multiple_files=True, key="documents")
        template = st.file_uploader("template (DDR .xlsx)", type=["xlsx"], key="template")

    folder = Path(folder_path.strip().strip('"')) if folder_path.strip() else None
    folder_ok = bool(folder and folder.exists() and folder.is_dir())
    upload_ok = bool(documents and template)
    if folder_path.strip() and not folder_ok:
        st.markdown("<p class='muted'>That folder was not found.</p>", unsafe_allow_html=True)

    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
    if st.button("Build DDR", disabled=not (folder_ok or upload_ok), use_container_width=True):
        _start_run(folder if folder_ok else None, instructions_text,
                   documents if upload_ok else None, template if upload_ok else None,
                   unit_name.strip() or None)
        st.rerun()


def _start_run(folder, instructions_text, documents, template, unit_name_filter) -> None:
    run_id = timestamp()
    run_dir = UPLOAD_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_root = OUTPUT_ROOT / run_id
    output_root.mkdir(parents=True, exist_ok=True)

    if folder is not None:
        document_paths, template_path = enumerate_folder(folder, run_dir / "_extracted")
    else:
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

    progress_q = st.session_state.progress_queue

    def callback(icon: str, message: str) -> None:
        progress_q.put((icon, message))

    def worker() -> None:
        try:
            if template_path is None:
                raise ValueError("No DDR template (a workbook whose name contains 'DDR' and "
                                 "'template') was found in the folder.")
            result = run_dd_upload(
                document_paths=document_paths,
                ddr_template_path=template_path,
                output_root=output_root,
                instructions_text=(instructions_text or "").strip(),
                progress_callback=callback,
                unit_name_filter=unit_name_filter,
            )
            progress_q.put(("__done__", result))
        except Exception as exc:
            progress_q.put(("err", f"Run stopped: {exc}"))
            progress_q.put(("__done__", DDUploadRunResult(routed=None, fatal_error=str(exc))))

    thread = threading.Thread(target=worker, daemon=True)
    st.session_state.run_thread = thread
    st.session_state.screen = "progress"
    thread.start()


# ---------------------------------------------------------------------------
# Screen 2 — Progress
# ---------------------------------------------------------------------------

# Wrap standalone numbers/dates/file-numbers in the feed with the mono class so
# verifiable values read in JetBrains Mono.
_MONO_TOKEN_RE = re.compile(
    r"(\bT0\d{4,}\b|\b\d{1,4}[./]\d{1,2}[./]\d{2,4}\b|\b\d+\.\d{2,}\b|\b\d{2,}\b)")


def _monoize(message: str) -> str:
    from html import escape
    return _MONO_TOKEN_RE.sub(lambda m: f"<span class='mono'>{m.group(0)}</span>", escape(message))


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
    pct = 1.0 if st.session_state.run_result is not None else min(0.95, done_count / max(done_count + 3, 6))
    st.progress(pct)

    rows = [f"<div class='row {icon}'>{_monoize(msg)}</div>" for icon, msg in feed[-300:]]
    st.markdown(f"<div class='feed'>{''.join(rows) or 'Starting the run.'}</div>", unsafe_allow_html=True)

    if st.session_state.run_result is not None:
        st.session_state.screen = "complete"
        st.rerun()


def render_progress_screen() -> None:
    st.markdown("<div class='headline'>Reading the file<span class='dot'>.</span></div>", unsafe_allow_html=True)
    st.markdown("<p class='subhead'>Parsing title opinions, resolving the controlling certification "
                "date, and building the DDR.</p>", unsafe_allow_html=True)
    render_progress_fragment()


# ---------------------------------------------------------------------------
# Screen 3 — Completion
# ---------------------------------------------------------------------------

def _review_items(unit_name: str, summary: dict, qa_exceptions, ddr_name: str) -> list[str]:
    """Specific, actionable review points: exact file, tab, row/area, and what
    to check. The app resolves nothing — it tells the reviewer where to look in
    the downloaded workbook."""
    items: list[str] = []
    wi, nri = summary.get("reconciliation_wi_status"), summary.get("reconciliation_nri_status")
    if wi == "N/A" or nri == "N/A":
        items.append(
            f"<span class='cite'>{ddr_name} · Ownership - Wells · row 3</span><br>"
            "Confirm the computed leasehold WI/NRI against the Well List PSA (wellbore) figures. "
            "A gap is the JOA / non-consent uplift into the wellbore, not a title defect — "
            "cross-check the Agreements tab.")
    elif wi in ("WARNING", "NOT_COMPUTED") or nri in ("WARNING", "NOT_COMPUTED"):
        items.append(
            f"<span class='cite'>{ddr_name} · Ownership - Wells · row 3</span><br>"
            "WI/NRI reconciliation did not pass — verify the Seller's interest against the opinions.")
    if summary.get("title_opinions_no_pdf"):
        items.append(
            f"<span class='cite'>{ddr_name} · PLM Title Review</span><br>"
            f"{summary['title_opinions_no_pdf']} title opinion(s) had no source PDF — obtain and review each.")
    items.append(
        f"<span class='cite'>{ddr_name} · Ownership Report · row 5 (Unit Gross)</span><br>"
        "Verify unit gross acres (derived from the title opinion legal description) against a survey or plat.")
    items.append(
        f"<span class='cite'>{ddr_name} · Runsheet</span><br>"
        "Confirm the supplemental-title result from the controlling certification date "
        f"(<span class='val'>{summary.get('controlling_certification_date', '—')}</span>) to present.")
    for exc in qa_exceptions:
        if getattr(exc, "severity", "") == "WARNING":
            items.append(f"<span class='cite'>{ddr_name} · Summary · Outstanding Curative</span><br>{exc.message}")
    return items


def render_completion_screen() -> None:
    result: DDUploadRunResult = st.session_state.run_result
    st.markdown("<div class='headline'>Ready to review<span class='dot'>.</span></div>", unsafe_allow_html=True)

    produced: list[str] = []
    failed: list[str] = []
    review: list[str] = []
    downloads: list[Path] = []

    if result.fatal_error:
        failed.append(result.fatal_error)
    else:
        for outcome in result.unit_outcomes:
            if outcome.error:
                failed.append(f"{outcome.unit_name} — {outcome.error}")
                continue
            s = outcome.result.summary
            ddr = outcome.result.ddr_result.output_path
            downloads.append(ddr)
            produced.append(
                f"{outcome.unit_name} — <span class='val'>{s['title_opinions_total']}</span> "
                f"title opinion(s), certification date "
                f"<span class='val'>{s.get('controlling_certification_date', '—')}</span>")
            review.extend(_review_items(outcome.unit_name, s, outcome.result.qa_exceptions, ddr.name))

    # Download first — the primary action.
    if downloads:
        if len(downloads) == 1:
            p = downloads[0]
            st.download_button("Download DDR", data=p.read_bytes(), file_name=p.name, use_container_width=True)
        else:
            import io
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                for p in downloads:
                    zf.write(p, arcname=p.name)
            st.download_button("Download DDRs (.zip)", data=buf.getvalue(),
                               file_name="ddr_reports.zip", use_container_width=True)

    st.markdown("<div class='sec'>Produced</div>", unsafe_allow_html=True)
    if produced:
        for item in produced:
            st.markdown(f"<div class='card'>{item}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='muted'>No DDR was produced. See below for why.</p>", unsafe_allow_html=True)

    if failed:
        st.markdown("<div class='sec'>Not completed</div>", unsafe_allow_html=True)
        for item in failed:
            st.markdown(f"<div class='card'>{item}</div>", unsafe_allow_html=True)

    st.markdown("<div class='sec'>Needs human review</div>", unsafe_allow_html=True)
    if review:
        for item in review:
            st.markdown(f"<div class='card'>{item}</div>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='muted'>Nothing flagged.</p>", unsafe_allow_html=True)

    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
    if st.button("Start another unit", use_container_width=True, type="secondary"):
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
