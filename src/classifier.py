from __future__ import annotations

from pathlib import Path
from typing import Any

from src.lease_engine import infer_lease_status, is_oil_and_gas_lease
from src.schemas import ClassificationStatus, LeaseStatus, SourceDocument
from src.utils import normalize_text, read_yaml


DEFAULT_RULES_PATH = Path("config/rules.yaml")


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    return read_yaml(path)


def classify_documents(
    records: list[SourceDocument],
    rules: dict[str, Any] | None = None,
) -> list[SourceDocument]:
    rules = rules or load_rules()
    for record in records:
        classify_document(record, rules)
    return records


def classify_document(
    record: SourceDocument,
    rules: dict[str, Any] | None = None,
) -> SourceDocument:
    rules = rules or load_rules()

    if record.duplicate_of:
        record.status = ClassificationStatus.DUPLICATE
        record.classification_confidence = record.dedupe_confidence or 1.0
        record.classification_reason = f"Duplicate of {record.duplicate_of}"
        _attach_lease_status(record)
        return record

    text = normalize_text(record.search_text())
    classification_rules = rules.get("classification", {})

    redline_hit = _find_rule_hit(text, classification_rules.get("redline", {}))
    if redline_hit and not _has_title_event_override(text, rules):
        record.status = ClassificationStatus.REDLINE
        record.classification_confidence = 0.95
        record.classification_reason = f"Matched redline rule: {redline_hit[0]}"
        record.redline_reason = _reason_from_hit(redline_hit)
        return record

    review_hit = _find_rule_hit(text, classification_rules.get("review", {}))
    if review_hit and not _is_clear_lease_related_assignment(text, rules):
        record.status = ClassificationStatus.REVIEW
        record.classification_confidence = 0.75
        record.classification_reason = f"Matched review rule: {review_hit[0]}"
        record.review_question = _review_question_from_hit(review_hit)
        _attach_lease_status(record)
        return record

    include_full_hit = _find_rule_hit(text, classification_rules.get("include_full", {}))
    if include_full_hit:
        record.status = ClassificationStatus.INCLUDE_FULL
        record.classification_confidence = 0.9
        record.classification_reason = f"Matched include rule: {include_full_hit[0]}"
        _attach_lease_status(record)
        _mark_expired_lease_comment(record)
        return record

    include_limited_hit = _find_rule_hit(
        text, classification_rules.get("include_limited", {})
    )
    if include_limited_hit:
        record.status = ClassificationStatus.INCLUDE_LIMITED
        record.classification_confidence = 0.8
        record.classification_reason = f"Matched limited include rule: {include_limited_hit[0]}"
        return record

    record.status = ClassificationStatus.REVIEW
    record.classification_confidence = 0.5
    record.classification_reason = "No deterministic rule matched"
    record.review_question = "Confirm whether this instrument affects title or minerals."
    _attach_lease_status(record)
    return record


def _find_rule_hit(
    text: str,
    grouped_keywords: dict[str, list[str]],
) -> tuple[str, str] | None:
    for rule_name, keywords in grouped_keywords.items():
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            if normalized_keyword and normalized_keyword in text:
                return rule_name, keyword
    return None


def _has_title_event_override(text: str, rules: dict[str, Any]) -> bool:
    terms = rules.get("overrides", {}).get("title_event_terms", [])
    return any(normalize_text(term) in text for term in terms)


def _is_clear_lease_related_assignment(text: str, rules: dict[str, Any]) -> bool:
    if "assignment" not in text and "bill of sale" not in text:
        return False
    lease_terms = rules.get("overrides", {}).get("lease_terms", [])
    return any(normalize_text(term) in text for term in lease_terms)


def _reason_from_hit(hit: tuple[str, str]) -> str:
    rule_name, keyword = hit
    return f"Non-title category '{rule_name}' matched keyword '{keyword}'."


def _review_question_from_hit(hit: tuple[str, str]) -> str:
    rule_name, keyword = hit
    if rule_name in {"unclear_assignment", "possible_title_effect"}:
        return f"Review whether keyword '{keyword}' affects title, minerals, or an active/potential lease."
    return f"Review instrument because rule '{rule_name}' matched keyword '{keyword}'."


def _attach_lease_status(record: SourceDocument) -> None:
    lease_status = infer_lease_status(record)
    if lease_status:
        record.lease_status = lease_status
        if lease_status == LeaseStatus.REVIEW and not record.review_question:
            record.review_question = "Confirm lease status, primary term, and release status."


def _mark_expired_lease_comment(record: SourceDocument) -> None:
    if is_oil_and_gas_lease(record) and record.lease_status == LeaseStatus.EXPIRED:
        existing = record.comments or ""
        if "EXPIRED" not in existing.upper():
            record.comments = f"{existing}; EXPIRED".strip("; ")
