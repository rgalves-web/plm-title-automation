"""Vision reading for scanned pages — mandatory, not optional.

Flow spec §2 rule 1: vision, not just OCR, for anything scanned. This module is
why that rule is affordable. Deterministic OCR handles born-digital text and
cheap confirmations; vision is spent where OCR provably fails — dense tables,
plats, screenshots — and its answers are cached by page hash so the same page is
never paid for twice.

Discipline carried in from CLAUDE.md invariant 7: a PAGE is sent, never a whole
document, and only the pages a task actually needs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE_DIRNAME = "vision_cache"
DEFAULT_MODEL = "claude-sonnet-4-5"


class VisionUnavailable(RuntimeError):
    """No vision path configured — the caller must degrade honestly, not guess."""


@dataclass
class PageImage:
    png: bytes
    page_no: int
    source: str

    def digest(self) -> str:
        return hashlib.sha256(self.png).hexdigest()[:32]


# The API refuses an image whose side exceeds this. Downscaling here keeps the
# page readable; silently sending an oversized image would fail the whole read.
MAX_EDGE_PX = 7800


def _fit(png: bytes) -> bytes:
    import io

    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    img = Image.open(io.BytesIO(png))
    if max(img.size) <= MAX_EDGE_PX:
        return png
    scale = MAX_EDGE_PX / max(img.size)
    img = img.resize((int(img.width * scale), int(img.height * scale)),
                     Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_pages(pdf_path: str | Path, pages: list[int], dpi: int = 200) -> list[PageImage]:
    """Render only the pages asked for — never the whole document."""
    import fitz

    doc = fitz.open(str(pdf_path))
    out: list[PageImage] = []
    try:
        for page_no in pages:
            pix = doc[page_no - 1].get_pixmap(dpi=dpi)
            out.append(PageImage(png=_fit(pix.tobytes("png")), page_no=page_no,
                                 source=Path(pdf_path).name))
    finally:
        doc.close()
    return out


def _client():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(".env"))
    except Exception:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise VisionUnavailable(
            "ANTHROPIC_API_KEY is not set — scanned pages cannot be read by "
            "vision. OCR-only results must be reported as partial, never as "
            "complete (flow spec §2 rule 1).")
    import anthropic
    return anthropic.Anthropic(api_key=key)


def read_page(image: PageImage, instruction: str, *, cache_dir: str | Path,
              model: str = DEFAULT_MODEL, max_tokens: int = 4000) -> str:
    """Ask one page one question. Cached by (page bytes + instruction)."""
    cache = Path(cache_dir) / CACHE_DIRNAME
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(
        (image.digest() + instruction).encode("utf-8")).hexdigest()[:32]
    hit = cache / f"{key}.json"
    if hit.exists():
        return json.loads(hit.read_text(encoding="utf-8"))["text"]

    client = _client()
    message = client.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {
                "type": "base64", "media_type": "image/png",
                "data": base64.standard_b64encode(image.png).decode("ascii")}},
            {"type": "text", "text": instruction},
        ]}])
    text = "".join(block.text for block in message.content
                   if getattr(block, "type", "") == "text")
    hit.write_text(json.dumps({"text": text, "source": image.source,
                               "page": image.page_no}), encoding="utf-8")
    return text


EXHIBIT_A_INSTRUCTION = """This is one page of Exhibit "A" of a recorded
Declaration of Pooled Unit: the table of oil and gas leases pooled into the unit.

Transcribe EVERY data row, one per line, exactly as printed, in this format:

  <EOG LEASE NO.>|<LESSOR>|<LESSEE>|<DATE>|<VOLUME>|<PAGE>

Rules:
- Transcribe, never infer. If a cell is blank or illegible, write ? for it.
- Keep the lease number exactly as printed, including its separator.
- Do not skip rows, do not merge rows, do not add rows.
- Output only the rows. No preamble, no commentary, no totals.
"""
