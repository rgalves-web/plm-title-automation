"""Evidence ledger: append-only record whose derived allowlist kills trap §3.1."""
from __future__ import annotations

from src.flow.evidence_ledger import (
    KIND_CONTRACT,
    KIND_LEASE,
    KIND_TITLE_OPINION,
    STATUS_CORRECTED,
    STATUS_DROPPED,
    STATUS_UNPLACED,
    EvidenceEntry,
    EvidenceLedger,
)


def _seed() -> EvidenceLedger:
    led = EvidenceLedger()
    led.record("T-O ORIG BRUMBAUGH.PDF", KIND_TITLE_OPINION, "T0140253")
    led.record("T-O SUPP KRAMER.PDF", KIND_TITLE_OPINION, "T0140319")
    led.record("K1400170.zip", KIND_CONTRACT, "K1400170")
    led.record("0190122-007.pdf", KIND_LEASE, "0190122-007")
    return led


def test_derive_allowlist_from_confirmed_evidence():
    led = _seed()
    allow = led.derive_allowlist("MAXWELL A UNIT")
    assert allow["title_opinions"] == {"T0140253", "T0140319"}
    assert allow["contracts"] == {"K1400170"}
    assert allow["leases"] == {"0190122-007"}
    assert allow["identity_tokens"] == {"MAXWELL"}   # via unit_identity_tokens


def test_only_trusted_status_widens_the_allowlist():
    led = _seed()
    led.record("ghost.pdf", KIND_TITLE_OPINION, "T9999999", status=STATUS_DROPPED)
    led.add(EvidenceEntry("unplaced.pdf", KIND_TITLE_OPINION, "T8888888",
                          status=STATUS_UNPLACED, reason="could not identify"))
    allow = led.derive_allowlist("MAXWELL A UNIT")
    assert "T9999999" not in allow["title_opinions"]   # merely dropped
    assert "T8888888" not in allow["title_opinions"]   # unplaced
    assert allow["title_opinions"] == {"T0140253", "T0140319"}


def test_corrected_counts_as_trusted():
    led = EvidenceLedger()
    led.add(EvidenceEntry("x.pdf", KIND_TITLE_OPINION, "T0140456", status=STATUS_CORRECTED))
    assert led.derive_allowlist("U")["title_opinions"] == {"T0140456"}


def test_unplaced_is_visible_never_lost():
    led = _seed()
    led.add(EvidenceEntry("weird.tif", KIND_TITLE_OPINION, None,
                          status=STATUS_UNPLACED, reason="no identifying token"))
    up = led.unplaced()
    assert len(up) == 1 and up[0].reason == "no identifying token"


def test_roundtrip_dict():
    led = _seed()
    back = EvidenceLedger.from_dict(led.to_dict())
    assert back.derive_allowlist("U") == led.derive_allowlist("U")
    assert [e.identifier for e in back.entries] == [e.identifier for e in led.entries]
