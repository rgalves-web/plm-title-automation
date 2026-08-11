"""D3 — knowledge/ holds no unit fact. Enforced here, not by good intentions.

If a unit fact leaks into knowledge/, it poisons the next unit. If a rule stays
trapped in a case, it is lost. The boundary is the OKF's most important
structural rule, so it is a test.
"""
from __future__ import annotations

from src.knowledge.linter import lint_knowledge
from src.knowledge.loader import knowledge_root


def test_the_real_knowledge_base_contains_no_unit_fact():
    findings = lint_knowledge(knowledge_root())
    assert not findings, "\n".join(f.describe() for f in findings)


def _base(tmp_path, body: str):
    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "precedence.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_lease_number_in_a_rule_is_caught(tmp_path):
    f = lint_knowledge(_base(tmp_path, "note: applies to 0220649-007\n"))
    assert f and f[0].kind == "lease number"


def test_a_unit_name_in_a_rule_is_caught(tmp_path):
    f = lint_knowledge(_base(tmp_path, "note: the Bowen unit is special\n"))
    assert f and f[0].kind == "unit name"


def test_a_contract_a_title_opinion_and_an_api_are_caught(tmp_path):
    for body, kind in (("x: K1400725\n", "contract number"),
                       ("x: T0140210\n", "title opinion number"),
                       ("x: 42-337-34187\n", "API number"),
                       ("x: Vol 479 Pg 590\n", "recording reference")):
        f = lint_knowledge(_base(tmp_path, body))
        assert f and f[0].kind == kind, (body, [x.kind for x in f])


def test_unit_scoped_lessons_are_exempt_quarantine(tmp_path):
    d = tmp_path / "lessons" / "unit"
    d.mkdir(parents=True)
    (d / "SOME_UNIT.yaml").write_text("note: applies to 0220649-007\n", encoding="utf-8")
    assert lint_knowledge(tmp_path) == []


def test_fixtures_are_exempt(tmp_path):
    d = tmp_path / "fixtures" / "some_lesson"
    d.mkdir(parents=True)
    (d / "fixture.yaml").write_text("citation: T0140210\n", encoding="utf-8")
    assert lint_knowledge(tmp_path) == []


def test_a_line_declared_as_provenance_is_allowed(tmp_path):
    # Recording WHERE a rule came from is not the same as encoding a case in it.
    body = "statement: the newest cert date controls\nsource_event: seen on T0140210\n"
    assert lint_knowledge(_base(tmp_path, body)) == []
