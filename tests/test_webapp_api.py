"""Web API wiring over the flow spine (FastAPI TestClient, temp dirs, no engine)."""
from __future__ import annotations

import yaml
import pytest
from fastapi.testclient import TestClient

from src.flow.config import Config
from src.flow.unit_state import load_state, save_state
from src.webapp.server import create_app

UNIT = "FAKE UNIT"
_MANIFEST = {
    "unit_name": UNIT, "client_name": "BKV",
    "title_opinions": [{"file_number": "T-O ORIG X A-122", "lessor": "X"}],
    "reference_contracts": [
        {"file_number": "K1400813", "record_type": "DESIGNATION OF POOLED UNIT"},
        {"file_number": "K1400170", "record_type": "FARMOUT AGREEMENT"},
    ],
    "leases": [{"lease_no": "0190122-007", "lessor": "B"}],
    "wells": [{"well_name": f"{UNIT} #1H", "well_api": "42-337-34216",
               "current_wi": "0.99", "current_nri": "0.74"}],
}


@pytest.fixture
def client(tmp_path):
    manifests = tmp_path / "manifests"
    (manifests / UNIT).mkdir(parents=True)
    (manifests / UNIT / "manifest.yaml").write_text(yaml.safe_dump(_MANIFEST), encoding="utf-8")
    cfg = Config(units_dir=str(tmp_path / "units"), manifests_dir=str(manifests),
                 project_root=str(tmp_path / "projects"))
    app = create_app(cfg)
    c = TestClient(app)
    c._cfg = cfg
    return c


def test_config_and_empty_board(client):
    assert client.get("/api/config").json()["units_dir"].endswith("units")
    board = client.get("/api/units").json()
    assert board["units"] == []
    assert UNIT in board["openable"]


def test_open_builds_checklist_and_dpu_contract(client):
    u = client.post(f"/api/units/{UNIT}/open").json()
    assert u["stage"] == "OPEN"
    assert len(u["checklist"]) == 5                       # 1 TO + 2 contracts + 1 lease + 1 RRC
    # DPU contract detected from the manifest's DESIGNATION OF POOLED UNIT.
    assert any(f["value"] == "K1400813" for f in u["facts"])
    assert UNIT in [c["unit_name"] for c in client.get("/api/units").json()["units"]]


def test_stage_transition(client):
    client.post(f"/api/units/{UNIT}/open")
    u = client.post(f"/api/units/{UNIT}/stage", json={"to": "GATHER"}).json()
    assert u["stage"] == "GATHER"


def test_seed_from_record_derives_allowlist(client):
    client.post(f"/api/units/{UNIT}/open")
    u = client.post(f"/api/units/{UNIT}/drop/seed").json()
    al = u["derived_allowlist"]
    assert "K1400813" in al["contracts"] and "K1400170" in al["contracts"]
    assert al["leases"] == 1
    assert al["identity_tokens"] == ["FAKE"]              # unit_identity_tokens("FAKE UNIT")
    assert u["stage"] == "DROP"


def test_add_evidence_manually(client):
    client.post(f"/api/units/{UNIT}/open")
    u = client.post(f"/api/units/{UNIT}/evidence", json={"entries": [
        {"file": "T0140319.pdf", "kind": "title_opinion", "identifier": "T0140319", "status": "confirmed"}]}).json()
    assert "T0140319" in u["derived_allowlist"]["title_opinions"]


def test_verdict_and_trace_from_seeded_review(client):
    client.post(f"/api/units/{UNIT}/open")
    # Seed a review queue + trace as the source-truth job would.
    st = load_state(UNIT, client._cfg.units_dir)
    st.gate_results = {
        "review_queue": [{"tab": "Title Review", "cell": "B31", "field": "OPR ref",
                          "value": "495/388", "label": "NEEDS EYES", "outcome": "ANCHORED-VERIFIED"}],
        "traces": {"Title Review!B31": {"tab": "Title Review", "cell": "B31",
                   "value": "495/388", "source_file": "IMG.png", "method": "ANCHORED-VERIFIED",
                   "detail": "matched by vol/page", "needs_verdict": True}},
    }
    save_state(st, client._cfg.units_dir)

    tr = client.get(f"/api/units/{UNIT}/trace", params={"tab": "Title Review", "cell": "B31"}).json()
    assert tr["source_file"] == "IMG.png" and tr["needs_verdict"] is True

    client.post(f"/api/units/{UNIT}/verdict",
                json={"tab": "Title Review", "cell": "B31", "verdict": "confirmed"})
    st2 = load_state(UNIT, client._cfg.units_dir)
    assert st2.verdicts["Title Review!B31"]["verdict"] == "confirmed"


def test_unknown_unit_404(client):
    assert client.get("/api/units/NOPE").status_code == 404


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "minorh" in r.text
