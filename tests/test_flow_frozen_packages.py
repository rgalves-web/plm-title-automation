"""Delivered packages are read-only — no PR may write a byte inside them.

Bowen A and Maxwell A are shipped. They live on only as regression fixtures, in
READ mode. The fence exists because a replay already did write into one: on
2026-08-11 a regression rewrote "DDR - Bowen A Unit_validation.txt" inside the
delivered package. Nothing was lost, but a shipped artefact changed as a side
effect of re-reading it, and that must be impossible rather than merely avoided.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import openpyxl
import pytest

from src.flow.deliverable_io import (
    FROZEN_MARKERS,
    FrozenArtifactError,
    assert_not_frozen,
    save_and_verify,
)


def _frozen(tmp_path) -> Path:
    p = tmp_path / "BOWEN A UNIT" / "SUBMISSION PLM" / "Bowen A Unit"
    p.mkdir(parents=True)
    return p


def test_the_guard_refuses_any_path_inside_a_delivered_package(tmp_path):
    frozen = _frozen(tmp_path)
    with pytest.raises(FrozenArtifactError, match="frozen"):
        assert_not_frozen(frozen / "DDR - Bowen A Unit_validation.txt")
    with pytest.raises(FrozenArtifactError):
        assert_not_frozen(frozen / "deep" / "nested" / "file.xlsx")


def test_the_guard_allows_everything_outside(tmp_path):
    assert assert_not_frozen(tmp_path / "WORK" / "DDR.xlsx")
    assert assert_not_frozen(tmp_path / "JOSH B UNIT" / "SUBMISSION" / "x.txt")


def test_a_deliverable_save_cannot_land_in_a_delivered_package(tmp_path):
    frozen = _frozen(tmp_path)
    with pytest.raises(FrozenArtifactError):
        save_and_verify(openpyxl.Workbook(), frozen / "DDR.xlsx")
    assert not (frozen / "DDR.xlsx").exists()


def test_a_validation_sidecar_cannot_land_in_a_delivered_package(tmp_path):
    from src.dd.ddr_validator import ValidationReport, write_validation_sidecar
    frozen = _frozen(tmp_path)
    ddr = frozen / "DDR - Bowen A Unit.xlsx"
    openpyxl.Workbook().save(ddr)          # the shipped file may exist
    with pytest.raises(FrozenArtifactError):
        write_validation_sidecar(ValidationReport(), ddr)
    assert not (frozen / "DDR - Bowen A Unit_validation.txt").exists()


def test_the_packager_cannot_stage_into_a_delivered_package(tmp_path):
    from src.dd.submission_packager import SubmissionPlan, stage_submission
    frozen = _frozen(tmp_path)
    plan = SubmissionPlan(unit_name="BOWEN A UNIT", unit_title="Bowen A Unit")
    with pytest.raises(FrozenArtifactError):
        stage_submission(plan, frozen)


def test_every_write_path_this_repo_owns_consults_the_guard():
    # A new write path added without the guard is the failure mode this catches.
    from src.dd import ddr_validator, submission_packager
    from src.flow import deliverable_io
    for fn in (deliverable_io.save_and_verify,
               ddr_validator.write_validation_sidecar,
               submission_packager.stage_submission):
        assert "assert_not_frozen" in inspect.getsource(fn), fn.__name__


def test_the_marker_is_the_shipped_package_folder():
    assert "SUBMISSION PLM" in FROZEN_MARKERS
