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
    # Two DIFFERENT people (they do not match each other) both fit "W Brumbaugh".
    r = match_person("W Brumbaugh", ["Winston Brumbaugh", "Wilba Brumbaugh"])
    assert not r.matched
    assert len(r.ambiguous) == 2
    assert "distinct parties" in r.reason


def test_same_given_name_different_middle_names_is_one_party():
    # Middle names are ignored by design, so these are one party under the rule
    # — not an ambiguity. (They match each other, not just the query.)
    r = match_person("Lynn Cox", ["Lynn W. Cox", "Lynn Marie Cox"])
    assert r.matched


def test_repeated_spelling_of_one_party_is_not_ambiguous():
    r = match_person("Richard Cox", ["Richard T. Cox", "Richard T Cox"])
    assert r.matched  # same normalized party listed twice — not an ambiguity


# --- initial matching: restores real leases WITHOUT reopening false merges ---
# A structural rule that refused initials entirely was too strict: it dropped
# "W S Brumbaugh" (the DPU's own spelling) from Winston Brumbaugh and emptied
# MI/WI/acres on real rows. An initial is accepted only when exactly ONE
# candidate qualifies.

_BRUMBAUGH_OWNERS = ["Worsham Family Limited Partnership", "Moore-Burrow Ltd.",
                     "Winston Brumbaugh", "Lovene Brumbaugh", "Billy R. Caldwell",
                     "Linda Pritchard", "Carolyn Belew"]


def test_initial_matches_the_only_qualifying_candidate():
    r = match_person("W S Brumbaugh", _BRUMBAUGH_OWNERS)
    assert r.matched, r.reason
    assert _BRUMBAUGH_OWNERS[r.index] == "Winston Brumbaugh"
    assert r.matched_on == "initial"


def test_initial_is_ambiguous_when_two_candidates_qualify():
    # W could be Winston or Wilba — an initial cannot choose between them.
    r = match_person("W Brumbaugh", ["Winston Brumbaugh", "Wilba Brumbaugh"])
    assert not r.matched
    assert len(r.ambiguous) == 2
    assert "initial only" in r.reason


def test_given_name_match_still_beats_an_initial_match():
    # Lovene is named outright; the L initial must not drag in anyone else.
    r = match_person("Lovene Brumbaugh", _BRUMBAUGH_OWNERS)
    assert r.matched and r.matched_on == "given_name"
    assert _BRUMBAUGH_OWNERS[r.index] == "Lovene Brumbaugh"


def test_initial_path_does_not_reopen_the_father_son_false_merge():
    # The suffix guard still applies on the weaker tier.
    assert not match_person("Lynn W Cox", ["Lynn W Cox Jr"]).matched
    assert not match_person("W Cox Jr", ["Winston Cox"]).matched


def test_initial_path_does_not_match_a_different_given_name():
    # "John A Cox" must never reach Richard T. Cox via the A/T initials.
    assert not match_person("John A Cox", ["Richard T. Cox"]).matched


def test_initial_never_matches_across_surnames():
    assert not match_person("W S Brumbaugh", ["Winston Caldwell"]).matched


def test_initial_never_matches_an_entity():
    assert not match_person("K M Trust", ["Kramer Mineral Trust"]).matched


def test_no_match_reports_a_reason():
    r = match_person("ST TX MF-112592", ["Lynn W. Cox"])
    assert not r.matched and r.reason


def test_unparseable_query_is_reported_not_matched():
    assert not match_person("", ["Lynn W. Cox"]).matched
    assert not match_person(None, ["Lynn W. Cox"]).matched


def test_same_party_spelled_two_ways_is_not_ambiguous():
    # The opinions list this person as both "Winston Brumbaugh" and
    # "Winston S. Brumbaugh"; that is one party, not two.
    r = match_person("W S Brumbaugh", ["Winston Brumbaugh", "Winston S. Brumbaugh"])
    assert r.matched, r.reason
    assert r.matched_on == "initial"


def test_two_genuinely_different_people_remain_ambiguous():
    r = match_person("W Brumbaugh", ["Winston Brumbaugh", "Wilba Brumbaugh"])
    assert not r.matched and len(r.ambiguous) == 2


# --- OCR-variant tier: one mis-scanned letter must not drop a real owner ---

def test_single_character_ocr_variant_matches_when_unique():
    # The Cox supplement's MINERALS table prints "Marte" for "Marie" once.
    r = match_person("Marie Hulme", ["Marte Cantwell Hulme", "Lynn W. Cox"])
    assert r.matched and r.matched_on == "ocr_variant"
    assert r.index == 0


def test_ocr_variant_never_beats_a_real_given_name_match():
    r = match_person("Marie Hulme", ["Marte Cantwell Hulme", "Marie Cantwell Hulme"])
    assert r.matched and r.matched_on == "given_name"
    assert r.index == 1


def test_ocr_variant_needs_a_long_enough_token():
    # "Jon" vs "Ron" is one edit but far too short to be a safe inference.
    assert not match_person("Jon Cox", ["Ron Cox"]).matched


def test_ocr_variant_does_not_merge_two_real_people():
    # Two edits apart — different people, never merged.
    assert not match_person("Marie Hulme", ["Marcus Hulme"]).matched


def test_ocr_variant_respects_the_suffix_guard():
    assert not match_person("Marie Hulme", ["Marte Cantwell Hulme Jr"]).matched
