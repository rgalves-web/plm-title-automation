"""Title Case normalization with the exception list (Collin item 4)."""
from __future__ import annotations

from src.dd.title_case import to_title_case


def test_basic_all_caps_to_title():
    assert to_title_case("LYNN W COX") == "Lynn W Cox"
    assert to_title_case("MARY JUNE CROXTON ESTATE") == "Mary June Croxton Estate"


def test_entity_forms_preserved():
    assert to_title_case("JDMI LLC") == "Jdmi LLC"
    assert to_title_case("MOORE-BURROW LTD ET AL") == "Moore-Burrow Ltd. et al"
    assert to_title_case("EOG RESOURCES INC") == "Eog Resources Inc."


def test_name_suffixes_and_roles():
    assert to_title_case("PETER WALLACE JR") == "Peter Wallace Jr."
    assert to_title_case("BOBBIE BRASHEAR JR TRUSTEE") == "Bobbie Brashear Jr. Trustee"
    assert to_title_case("JOHN SMITH III") == "John Smith III"


def test_legal_reference_preserved():
    # Survey abstract A-122 and block numbers keep their exact form.
    out = to_title_case("119.2 ACRES OUT OF THE SAMUEL CABLE SURVEY A-122 BLK 7")
    assert "A-122" in out
    assert "Samuel Cable Survey" in out


def test_already_mixed_case_is_left_untouched():
    assert to_title_case("Lynn W. Cox et al") == "Lynn W. Cox et al"


def test_idempotent():
    once = to_title_case("W S BRUMBAUGH ET AL")
    assert to_title_case(once) == once


def test_none_and_blank():
    assert to_title_case(None) is None
    assert to_title_case("   ") == "   "
