"""L0 + the closed vocabulary load, validate, and fail loudly when wrong."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.knowledge.loader import (
    KnowledgeError,
    knowledge_root,
    load_knowledge,
)


def test_the_real_knowledge_base_loads_and_validates():
    k = load_knowledge()
    assert k.ontology.version >= 1
    assert len(k.ontology.entities) == 8            # OKF_SPEC §2
    assert set(k.identity_keys.keys) <= set(k.ontology.entities)
    assert k.exclusion_reasons.reasons


def test_the_package_directory_is_not_mistaken_for_the_knowledge_base():
    # src/knowledge/ is this Python package; knowledge/ is the data.
    root = knowledge_root()
    assert (root / "ontology" / "entities.yaml").is_file()
    assert root.name == "knowledge" and not (root / "loader.py").exists()


# --- identity: a partial key never confirms --------------------------------

def test_a_lease_needs_both_number_and_recording():
    k = load_knowledge()
    assert k.missing_identity_fields("lease", {"eog_lease_number": "0000000-000"}) \
        == ["recording_book_page"]
    assert k.missing_identity_fields(
        "lease", {"eog_lease_number": "0000000-000",
                  "recording_book_page": "479.590"}) == []


def test_a_unit_is_never_identified_by_name():
    k = load_knowledge()
    key = k.identity_key("unit")
    assert "name" in key.never_identify_by
    # Name alone leaves the whole key missing — so it stays a candidate.
    assert set(k.missing_identity_fields("unit", {"name": "Some Unit"})) == \
        {"dpu_book_page", "effective_date"}


def test_a_survey_needs_abstract_and_block():
    k = load_knowledge()
    assert k.missing_identity_fields("survey", {"abstract": "319"}) == ["block"]
    assert "abstract_alone" in k.identity_key("survey").never_identify_by


def test_a_title_opinion_key_is_abstract_acres_and_cert_date():
    # The key the resolver finding calls for.
    k = load_knowledge()
    assert set(k.identity_key("title_opinion").required) == \
        {"abstract", "gross_acres", "cert_date"}
    assert "filename" in k.identity_key("title_opinion").never_identify_by


def test_an_unknown_entity_has_no_key():
    with pytest.raises(KnowledgeError, match="no identity key"):
        load_knowledge().identity_key("dragon")


# --- the closed vocabulary --------------------------------------------------

def test_reasons_are_a_closed_set():
    k = load_knowledge()
    assert k.is_valid_reason("doc_nao_localizado", "blank")
    assert not k.is_valid_reason("porque sim")               # free prose
    assert not k.is_valid_reason("fora_do_tipo", "blank")    # wrong context


def test_the_three_blank_reasons_are_a_subset_of_the_vocabulary():
    k = load_knowledge()
    for name in ("doc_nao_localizado", "pendente_de_terceiro",
                 "fato_inexistente_no_registro"):
        assert name in k.exclusion_reasons.blank_reasons
        assert "blank" in k.exclusion_reasons.reasons[name].applies_to


# --- a schema error breaks the boot ----------------------------------------

_OK_TAXONOMY = {"version": 1, "categories": {"lease_ogl": {
    "label": "L", "feeds": ["lease_review"], "relevance_test": "?",
    "disposition_default": "read", "risk_tier": "high"}}, "feedless_allowed": []}
_OK_CAT_TO_DDR = {"version": 1, "destinations": {
    "lease_review": {"resolves_to": ["Lease Review"], "writes": ["x"]}}}


def _write_base(tmp_path: Path, *, entities: dict, keys: dict, reasons: dict,
                taxonomy: dict | None = None, cat_to_ddr: dict | None = None):
    (tmp_path / "ontology").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "taxonomy").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ontology" / "entities.yaml").write_text(
        yaml.safe_dump(entities), encoding="utf-8")
    (tmp_path / "ontology" / "identity_keys.yaml").write_text(
        yaml.safe_dump(keys), encoding="utf-8")
    (tmp_path / "rules" / "exclusion_reasons.yaml").write_text(
        yaml.safe_dump(reasons), encoding="utf-8")
    (tmp_path / "taxonomy" / "categories.yaml").write_text(
        yaml.safe_dump(taxonomy or _OK_TAXONOMY), encoding="utf-8")
    (tmp_path / "taxonomy" / "category_to_ddr.yaml").write_text(
        yaml.safe_dump(cat_to_ddr or _OK_CAT_TO_DDR), encoding="utf-8")
    return tmp_path


_OK_ENT = {"version": 1,
           "entities": {"lease": {"label": "L", "description": "d", "relations": []}},
           "relations": {}}
_OK_KEYS = {"version": 1, "keys": {"lease": {"required": ["eog_lease_number"]}},
            "reference_states": ["candidate", "confirmed"]}
_OK_REASONS = {"version": 1,
               "reasons": {"doc_nao_localizado": {
                   "label": "x", "applies_to": ["blank"], "definition": "d"}},
               "blank_reasons": ["doc_nao_localizado"]}


def test_a_valid_minimal_base_loads(tmp_path):
    assert load_knowledge(_write_base(tmp_path, entities=_OK_ENT, keys=_OK_KEYS,
                                      reasons=_OK_REASONS))


def test_a_relation_naming_an_unknown_entity_breaks_the_boot(tmp_path):
    ent = {**_OK_ENT, "relations": {"bad": {"from": "lease", "to": "ghost",
                                            "proof": "p"}}}
    with pytest.raises(KnowledgeError, match="unknown entity"):
        load_knowledge(_write_base(tmp_path, entities=ent, keys=_OK_KEYS,
                                   reasons=_OK_REASONS))


def test_an_identity_key_for_an_unknown_entity_breaks_the_boot(tmp_path):
    keys = {**_OK_KEYS, "keys": {"ghost": {"required": ["x"]}}}
    with pytest.raises(KnowledgeError, match="unknown entities"):
        load_knowledge(_write_base(tmp_path, entities=_OK_ENT, keys=keys,
                                   reasons=_OK_REASONS))


def test_a_blank_reason_that_does_not_apply_to_blanks_breaks_the_boot(tmp_path):
    reasons = {"version": 1,
               "reasons": {"r": {"label": "x", "applies_to": ["skip"],
                                 "definition": "d"}},
               "blank_reasons": ["r"]}
    with pytest.raises(KnowledgeError, match="does not apply to blanks"):
        load_knowledge(_write_base(tmp_path, entities=_OK_ENT, keys=_OK_KEYS,
                                   reasons=reasons))


def test_a_missing_file_breaks_the_boot(tmp_path):
    (tmp_path / "ontology").mkdir(parents=True)
    (tmp_path / "ontology" / "entities.yaml").write_text(
        yaml.safe_dump(_OK_ENT), encoding="utf-8")
    with pytest.raises(KnowledgeError, match="missing"):
        load_knowledge(tmp_path)


# --- caching ----------------------------------------------------------------

def test_the_cache_keys_on_content_not_on_time(tmp_path):
    base = _write_base(tmp_path, entities=_OK_ENT, keys=_OK_KEYS, reasons=_OK_REASONS)
    first = load_knowledge(base)
    assert load_knowledge(base) is first            # unchanged -> same object
    ent = {**_OK_ENT, "entities": {**_OK_ENT["entities"],
                                   "well": {"label": "W", "description": "d",
                                            "relations": []}}}
    (base / "ontology" / "entities.yaml").write_text(yaml.safe_dump(ent), encoding="utf-8")
    second = load_knowledge(base)
    assert second is not first and "well" in second.ontology.entities
