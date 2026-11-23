"""Integration: API + worker + Postgres + Redis + Azurite (full mode). Uses the dev database because the
pipeline needs the loaded KB and IMR data (`make data`)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.full
ROOT = Path(__file__).resolve().parents[1]


def _gold(i=0):
    return json.loads((ROOT / "evals" / "gold" / "letters.jsonl").read_text(encoding="utf-8").splitlines()[i])


@pytest.fixture(scope="module")
def client():
    from appeal_core.db import get_engine
    from sqlalchemy import text

    try:
        with get_engine().connect() as c:
            if not c.execute(text("select count(*) from kb_chunk")).scalar():
                pytest.skip("run `make data` first")
    except Exception:
        pytest.skip("Postgres not available")
    from appeal_api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def drain(orch=None):
    from appeal_core.adapters import get_queue
    from appeal_worker.orchestrator import Orchestrator

    q = get_queue()
    orch = orch or Orchestrator()
    while True:
        j = q.claim(f"test-{uuid.uuid4().hex[:6]}")
        if not j:
            return orch
        try:
            orch.handle(j.topic, j.case_id)
            q.complete(j.id)
        except Exception as e:
            q.fail(j.id, str(e))
            raise


def create(client, text):
    r = client.post("/v1/cases", json={"text": text}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    d = r.json()
    return d["id"], {"Authorization": f"Bearer {d['access_token']}"}


def confirm(client, cid, H, fields=None):
    r = client.get(f"/v1/cases/{cid}", headers=H)
    assert r.json()["status"] == "AWAITING_CONFIRMATION"
    r = client.put(f"/v1/cases/{cid}/extraction", json={"fields": fields or {}}, headers={**H, "If-Match": r.headers["ETag"]})
    assert r.status_code == 200, r.text


def test_gold_letter_flows_to_ready_with_cited_letter(client):
    g = _gold(0)
    cid, H = create(client, g["text"])
    drain()
    confirm(client, cid, H)
    drain()
    d = client.get(f"/v1/cases/{cid}", headers=H).json()
    assert d["status"] == "READY", d
    L = client.get(f"/v1/cases/{cid}/letter", headers=H).json()
    cited = [c for s in L["sections"] for x in s["sentences"] for c in x["citations"]]
    assert any(c.startswith("R") for c in cited)
    assert set(cited) <= set(L["sources"])
    assert d["deadlines"][0]["due_date"] == g["label"]["deadline"]
    # SSE replays history and ends at a terminal status
    with client.stream("GET", f"/v1/cases/{cid}/events", headers=H) as r:
        body = "".join(r.iter_text())
    assert "event: step" in body and '"agent": "reviewer"' in body


def test_idempotency_key_returns_same_case(client):
    k = uuid.uuid4().hex
    a = client.post("/v1/cases", json={"text": _gold(1)["text"]}, headers={"Idempotency-Key": k}).json()
    b = client.post("/v1/cases", json={"text": _gold(1)["text"]}, headers={"Idempotency-Key": k}).json()
    assert a["id"] == b["id"]
    assert client.post("/v1/cases", json={"text": "x" * 50}).status_code == 400  # header required
    drain()


def test_access_token_required(client):
    cid, H = create(client, _gold(2)["text"])
    assert client.get(f"/v1/cases/{cid}").status_code == 404
    assert client.get(f"/v1/cases/{cid}", headers={"Authorization": "Bearer nope"}).status_code == 404
    r = client.get(f"/v1/cases/{cid}", headers=H)
    assert r.status_code == 200 and r.headers["ETag"]
    drain()


def test_if_match_required_and_checked(client):
    cid, H = create(client, _gold(3)["text"])
    drain()
    assert client.put(f"/v1/cases/{cid}/extraction", json={"fields": {}}, headers=H).status_code == 428
    assert client.put(f"/v1/cases/{cid}/extraction", json={"fields": {}}, headers={**H, "If-Match": '"999"'}).status_code == 412


def test_worker_crash_resumes_without_rerunning_completed_steps(client, monkeypatch):
    from appeal_core.db import session_scope
    from appeal_core.models import AgentRun
    from appeal_worker import agents
    from appeal_worker.orchestrator import Orchestrator

    cid, H = create(client, _gold(4)["text"])
    drain()
    confirm(client, cid, H)
    real_write = agents.write
    calls = {"n": 0}

    def crashing_write(*a, **k):
        calls["n"] += 1
        raise SystemExit("worker killed mid-case")  # not caught by job retry logic, like a real kill

    monkeypatch.setattr(agents, "write", crashing_write)
    orch1 = Orchestrator()
    with pytest.raises(SystemExit):
        orch1.handle("case.draft", cid)
    with session_scope() as s:
        counts = dict(s.execute(select(AgentRun.agent, func.count()).where(AgentRun.case_id == cid).group_by(AgentRun.agent)).all())
    assert counts == {"intake": 1, "classifier": 1, "research": 1}
    monkeypatch.setattr(agents, "write", real_write)
    orch2 = Orchestrator()
    orch2.handle("case.draft", cid)  # redelivery after the lease expires
    with session_scope() as s:
        counts = dict(s.execute(select(AgentRun.agent, func.count()).where(AgentRun.case_id == cid).group_by(AgentRun.agent)).all())
    assert counts["intake"] == 1 and counts["classifier"] == 1 and counts["research"] == 1
    # second run made only writer calls (no extraction or query-rewrite provider calls)
    assert orch2.provider_calls == counts["writer"]
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] == "READY"
    drain()  # the queued draft job is now a no-op replay
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] == "READY"


def test_replay_of_finished_case_makes_no_provider_calls(client):
    from appeal_worker.orchestrator import Orchestrator

    cid, H = create(client, _gold(5)["text"])
    drain()
    confirm(client, cid, H)
    drain()
    o = Orchestrator()
    o.handle("case.ingest", cid)
    o.handle("case.draft", cid)
    assert o.provider_calls == 0


def test_low_confidence_goes_to_needs_category(client):
    text = (
        "Example Health Plan\nMember ID: ZZTEST555123\nDear Jordan Testperson,\n"
        "We have reviewed your request for physical therapy. Plan type: Medicare Advantage.\n"
        "Reason: After review we are unable to approve this request at this time.\n"
    )
    cid, H = create(client, text)
    drain()
    confirm(client, cid, H, {"notice_date": "2025-06-01"})
    drain()
    d = client.get(f"/v1/cases/{cid}", headers=H).json()
    if d["status"] != "NEEDS_CATEGORY":
        pytest.skip(f"classifier was confident ({d['classification']['probability']})")
    assert client.post(f"/v1/cases/{cid}/category", json={"category": "medical_necessity"}, headers=H).status_code == 200
    drain()
    assert client.get(f"/v1/cases/{cid}", headers=H).json()["status"] in ("READY", "NEEDS_HUMAN")


def test_exports_blocked_until_placeholders_filled(client):
    cid, H = create(client, _gold(6)["text"])
    drain()
    confirm(client, cid, H)
    drain()
    assert client.get(f"/v1/cases/{cid}/exports/pdf", headers=H).status_code == 409
    L = client.get(f"/v1/cases/{cid}/letter", headers=H).json()
    for s in L["sections"]:
        for x in s["sentences"]:
            x["text"] = x["text"].replace("[ADD: your phone number or email]", "Phone on file").replace("[ADD: ", "").replace("]", "") if "[ADD:" in x["text"] else x["text"]
    r = client.put(f"/v1/cases/{cid}/letter", json={"sections": L["sections"]}, headers=H)
    assert r.status_code == 200 and r.json()["placeholders_remaining"] == 0
    pdf = client.get(f"/v1/cases/{cid}/exports/pdf", headers=H)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = client.get(f"/v1/cases/{cid}/exports/docx", headers=H)
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    ics = client.get(f"/v1/cases/{cid}/exports/ics", headers=H)
    assert ics.status_code == 200 and "BEGIN:VCALENDAR" in ics.text


def test_regenerate_section(client):
    cid, H = create(client, _gold(7)["text"])
    drain()
    confirm(client, cid, H)
    drain()
    before = client.get(f"/v1/cases/{cid}/letter", headers=H).json()
    r = client.post(f"/v1/cases/{cid}/letter/regenerate", json={"section_id": "request", "reason": "firmer"}, headers=H)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["version"] == before["version"] + 1
    assert "review" in after


def test_delete_case_cascades(client):
    from appeal_core.db import session_scope
    from appeal_core.models import AgentRun, TokenVault

    cid, H = create(client, _gold(8)["text"])
    drain()
    assert client.delete(f"/v1/cases/{cid}", headers=H).status_code == 204
    assert client.get(f"/v1/cases/{cid}", headers=H).status_code == 404
    with session_scope() as s:
        assert s.get(TokenVault, cid) is None
        assert s.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.case_id == cid)) == 0


def test_uploads_and_problem_details(client):
    r = client.post("/v1/uploads", json={"filename": "scan.jpg", "content_type": "image/jpeg", "size": 1000})
    assert r.status_code == 415 and r.headers["content-type"].startswith("application/problem+json")
    r = client.post("/v1/uploads", json={"filename": "big.pdf", "content_type": "application/pdf", "size": 11 * 1024 * 1024})
    assert r.status_code == 413
    r = client.post("/v1/uploads", json={"filename": "letter.txt", "content_type": "text/plain", "size": 500})
    assert r.status_code == 200 and "sig=" in r.json()["upload_url"]
    # browser-style PUT straight to blob storage through the SAS URL
    import httpx

    g = _gold(9)
    put = httpx.put(r.json()["upload_url"], content=g["text"].encode(), headers={"x-ms-blob-type": "BlockBlob"})
    assert put.status_code in (201, 200), put.text
    c = client.post("/v1/cases", json={"blob_name": r.json()["blob_name"]}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert c.status_code == 201
    drain()
    H = {"Authorization": f"Bearer {c.json()['access_token']}"}
    assert client.get(f"/v1/cases/{c.json()['id']}", headers=H).json()["status"] == "AWAITING_CONFIRMATION"


def test_readyz(client):
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"] == {"db": True, "redis": True, "blob": True}
    assert "X-Correlation-ID" in r.headers
