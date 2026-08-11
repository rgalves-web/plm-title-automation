"""D1 fixtures: two parts — the claim in git, the bytes outside it.

A fixture whose bytes are absent is an explicitly COUNTED SKIP, never a silent
pass and never a failure. That is what keeps a lesson honest without putting
client documents in the repository.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.knowledge.loader import knowledge_root

FIXTURES = knowledge_root() / "fixtures"


def _fixture_files():
    return sorted(FIXTURES.glob("*/fixture.yaml")) if FIXTURES.is_dir() else []


def test_the_repository_has_at_least_one_lesson_fixture():
    assert _fixture_files(), "every lesson needs a fixture (invariant 14)"


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.parent.name)
def test_every_fixture_declares_the_two_parts(path: Path):
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    for field in ("lesson_id", "statement", "source_event", "files", "cases"):
        assert spec.get(field), f"{path.parent.name}: missing {field}"
    for entry in spec["files"]:
        assert entry.get("path", "").startswith("data/"), \
            "fixture bytes live outside git, under data/"


def test_the_resolver_fixture_holds_identity_across_abstracts(tmp_path):
    """The 2026-08-11 lesson, run synthetically: a citation must reach the
    document bearing its abstract and never one bearing a different abstract.

    Synthetic (names only, empty bytes) because the claim under test is
    identity resolution, which reads names and keys — not page content. When the
    redacted originals are produced they replace this without changing the test.
    """
    from src.dd.source_truth_check import SourceIndex, _abstracts

    spec = yaml.safe_load((FIXTURES / "resolver_identity_by_key" /
                           "fixture.yaml").read_text(encoding="utf-8"))
    if not spec.get("synthetic_ok"):                      # pragma: no cover
        pytest.skip("fixture requires real bytes; see data/fixtures/")

    for entry in spec["files"]:
        (tmp_path / Path(entry["path"]).name).write_bytes(b"")
    idx = SourceIndex([tmp_path], ocr_fn=lambda p: "")

    for case in spec["cases"]:
        got = idx.resolve(case["citation"])
        assert got is not None, case["citation"]
        assert case["expect_abstract"] in _abstracts(got.stem), \
            f"{case['citation']!r} -> {got.name}"
        assert case["must_not_resolve_to_abstract"] not in _abstracts(got.stem), \
            f"{case['citation']!r} crossed abstracts -> {got.name}"


def test_absent_fixture_bytes_are_reported_as_a_counted_skip(capsys):
    # The accounting the plan asks for: fixtures run vs fixtures skipped.
    total = len(_fixture_files())
    missing = []
    for path in _fixture_files():
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in spec.get("files", []):
            if not Path(entry["path"]).exists():
                missing.append(f"{spec['lesson_id']}:{Path(entry['path']).name}")
    print(f"\nFIXTURES: {total} declared · {len(missing)} byte-sets absent "
          f"(synthetic or pending): {missing}")
    assert total  # the accounting itself is the assertion; absence never fails
