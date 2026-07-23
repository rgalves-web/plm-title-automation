"""One config for the flow layer — the single place operational settings live.

Replaces knowledge that today is scattered or hardcoded: the tesseract binary
path (assessment debt §4, duplicated in two modules), the OCR window an operator
otherwise has to remember (§3.4), and where per-unit case files are kept.

Loading order (first hit wins, then merged over built-in defaults):
    explicit path arg  ->  $MINORH_CONFIG  ->  ./config.yaml  ->  defaults only.

Nothing here degrades ungracefully: a missing tesseract binary is reported
honestly via ``tesseract_status()`` rather than crashing at OCR time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_ENV_VAR = "MINORH_CONFIG"
DEFAULT_CONFIG_NAME = "config.yaml"

# The known Windows install; not on PATH (assessment §3.3). A real config.yaml
# overrides this, and absence is surfaced, never fatal.
_DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_DEFAULTS: dict[str, Any] = {
    "tesseract_cmd": _DEFAULT_TESSERACT,
    "source_roots": [],
    "ocr_window_seconds": 600,          # long by default: source-truth OCR is slow
    "model": "claude-opus-4-8",
    "units_dir": "data/units",
    "template_path": None,
    "project_root": None,               # acquisition folder holding <UNIT>/ project dirs
    "manifests_dir": "data/output/dd",  # where per-unit manifest.yaml files live
}


@dataclass
class Config:
    tesseract_cmd: str | None = _DEFAULT_TESSERACT
    source_roots: list[str] = field(default_factory=list)
    ocr_window_seconds: int = 600
    model: str = "claude-opus-4-8"
    units_dir: str = "data/units"
    template_path: str | None = None
    project_root: str | None = None
    manifests_dir: str = "data/output/dd"
    source_path: str | None = None      # where this config was loaded from (provenance)

    def tesseract_available(self) -> bool:
        return bool(self.tesseract_cmd) and Path(self.tesseract_cmd).exists()

    def tesseract_status(self) -> str:
        """An honest one-liner for the UI / logs — never a silent failure."""
        if not self.tesseract_cmd:
            return "tesseract not configured (set tesseract_cmd in config.yaml)"
        if not Path(self.tesseract_cmd).exists():
            return f"tesseract configured but not found at {self.tesseract_cmd}"
        return f"tesseract ready at {self.tesseract_cmd}"

    def units_path(self) -> Path:
        return Path(self.units_dir)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tesseract_cmd": self.tesseract_cmd,
            "source_roots": list(self.source_roots),
            "ocr_window_seconds": self.ocr_window_seconds,
            "model": self.model,
            "units_dir": self.units_dir,
            "template_path": self.template_path,
            "project_root": self.project_root,
            "manifests_dir": self.manifests_dir,
        }


def _config_file(explicit: str | Path | None) -> Path | None:
    for candidate in (explicit,
                      os.environ.get(CONFIG_ENV_VAR),
                      Path.cwd() / DEFAULT_CONFIG_NAME):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def load_config(path: str | Path | None = None) -> Config:
    """Build a Config from defaults overlaid with a YAML file, if one is found.

    Unknown keys in the file are ignored (forward-compatible); known keys
    override the defaults. Always returns a usable Config."""
    merged = dict(_DEFAULTS)
    source: str | None = None
    file = _config_file(path)
    if file is not None:
        import yaml
        loaded = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        for key in _DEFAULTS:
            if key in loaded:
                merged[key] = loaded[key]
        source = str(file)
    return Config(source_path=source, **merged)


def configure_tesseract(config: Config) -> bool:
    """Point pytesseract at the configured binary if it exists. Returns whether
    OCR is available. Never raises — a missing binary is a reported state, not a
    crash (callers check the return / config.tesseract_status())."""
    if not config.tesseract_available():
        return False
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
        return True
    except Exception:  # pytesseract absent or misconfigured — degrade honestly
        return False
