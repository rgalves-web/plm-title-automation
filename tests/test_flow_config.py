"""Flow config: one place for operational settings, graceful about a missing OCR binary."""
from __future__ import annotations

import yaml

from src.flow.config import Config, configure_tesseract, load_config


def test_defaults_are_usable_without_a_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MINORH_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)               # no config.yaml here
    cfg = load_config()
    assert cfg.units_dir == "data/units"
    assert cfg.ocr_window_seconds >= 300      # long by default (source-truth is slow)
    assert cfg.source_path is None


def test_file_overrides_defaults(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(yaml.safe_dump({
        "tesseract_cmd": str(tmp_path / "tess.exe"),
        "ocr_window_seconds": 900,
        "units_dir": "data/units",
        "template_path": "T.xlsx",
        "ignored_unknown_key": 1,             # forward-compatible: ignored, not fatal
    }), encoding="utf-8")
    cfg = load_config(f)
    assert cfg.ocr_window_seconds == 900
    assert cfg.template_path == "T.xlsx"
    assert cfg.source_path == str(f)


def test_missing_tesseract_is_reported_not_fatal(tmp_path):
    cfg = Config(tesseract_cmd=str(tmp_path / "nope.exe"))
    assert cfg.tesseract_available() is False
    assert "not found" in cfg.tesseract_status()
    assert configure_tesseract(cfg) is False   # never raises


def test_present_tesseract_is_available(tmp_path):
    fake = tmp_path / "tesseract.exe"; fake.write_bytes(b"x")
    cfg = Config(tesseract_cmd=str(fake))
    assert cfg.tesseract_available() is True
    assert "ready" in cfg.tesseract_status()
