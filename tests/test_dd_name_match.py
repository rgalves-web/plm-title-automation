"""Deterministic person-name matching (Maxwell lessons item 5).

Golden pairs come from the approved v5 baseline's manual verification: each pair
is the SAME party printed two ways in the title opinions.
"""
from __future__ import annotations

import pytest

from src.dd.name_match import match_person, names_match, parse_person_name

_SAME_PARTY = [
    ("Marie Hulme", "Marie Cantwell Hulme"),
    ("Melba Sanderfer", "Melba Joy McGrew Sanderfer"),
    ("Jeb Mcnew", "Jim Jeb McNew"),
    ("Linda Springfield", "Linda Ray Croxton Springfield"),
    ("Peter Wallace Jr.", "Pete Andrew Wallace Jr."),
    ("Richard Cox", "Richard T. Cox"),
]


def _match(a: str, b: str) -> bool:
    return names_match(parse_person_name(a), parse_person_name(b))


@pytest.mark.parametrize("a, b", _SAME_PARTY)
def test_golden_pairs_are_the_same_party(a, b):
    assert _match(a, b)


@pytest.mark.parametrize("a, b", _SAME_PARTY)
def test_matching_is_symmetric(a, b):
    assert _match(a, b) == _match(b, a)


def test_middle_names_and_initials_are_ignored():
    assert _match("Richard Cox", "Richard T. Cox")
    assert _match("Linda Springfield", "Linda Ray Croxton Springfield")


def test_short_form_given_name_matches_by_prefix():
    assert _match("Peter Wallace Jr.", "Pete Andrew Wallace Jr.")


def test_too_short_a_prefix_does_not_match():
    # "Jo" is not enough to claim "John" — guards against over-merging.
    assert not _match("Jo Cox", "John Cox")


def test_different_given_names_same_surname_do_not_match():
    assert not _match("John A Cox", "Richard T. Cox")


def test_identity_suffix_separates_father_and_son():
    # The old fuzzy matcher scored this 87 and wrongly unified them.
    assert not _match("Lynn W Cox", "Lynn W Cox Jr")
    assert not _match("Peter Wallace Jr.", "Peter Wallace Sr.")


def test_initials_only_is_not_enough_to_identify():
    assert not _match("R. T. Cox", "Richard Cox")


def test_different_surname_never_matches():
    assert not _match("Sandra Lynn Walker", "Lynn W Cox")


def test_estate_wrapper_is_not_identity():
    assert _match("Estate of Mary June Croxton, deceased", "Mary June Croxton Estate")


def test_entities_require_exact_identity():
    assert _match("Kramer Mineral Trust", "Kramer Mineral Trust")
    assert not _match("Kramer Mineral Trust", "Jacob A Warnock Inc")
    # An entity is never the same party as a person who shares a token.
    assert not _match("Kramer Mineral Trust", "John Kramer")


def test_match_person_returns_single_index():
    r = match_person("Richard Cox", ["Lynn W. Cox", "Richard T. Cox", "John A. Cox"])
    assert r.matched and r.index == 1


def test_ambiguous_match_returns_empty_and_itemizes():
    r = match_person("Lynn Cox", ["Lynn W. Cox", "Lynn Marie Cox"])
    assert not r.matched
    assert len(r.ambiguous) == 2
    assert "distinct parties" in r.reason


def test_repeated_spelling_of_one_party_is_not_ambiguous():
    r = match_person("Richard Cox", ["Richard T. Cox", "Richard T Cox"])
    assert r.matched  # same normalized party listed twice — not an ambiguity


def test_no_match_reports_a_reason():
    r = match_person("ST TX MF-112592", ["Lynn W. Cox"])
    assert not r.matched and r.reason


def test_unparseable_query_is_reported_not_matched():
    assert not match_person("", ["Lynn W. Cox"]).matched
    assert not match_person(None, ["Lynn W. Cox"]).matched
