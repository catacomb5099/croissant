import json
import logging
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from curator import service
from curator.run import ROOT

TOKEN = "test-token-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    shutil.copy(ROOT / "categories.yaml", tmp_path / "categories.yaml")
    monkeypatch.setenv("CURATOR_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATOR_TOKEN", TOKEN)

    def fake(key, cat, *, root, **kw):
        time.sleep(0.2)
        return {"key": key, "status": "written", "editionDate": "2026-09-27", "trackCount": 40}

    monkeypatch.setattr(service, "run_category", fake)
    return tmp_path


@pytest.fixture
def client(root):
    with TestClient(service.app) as c:
        yield c


def wait_final(client, rid):
    for _ in range(50):
        r = client.get(f"/v1/runs/{rid}", headers=AUTH).json()
        if r["status"] in service.FINAL:
            return r
        time.sleep(0.1)
    raise AssertionError(f"run {rid} never finished: {r}")


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_health_checks_logged_only_at_debug():
    log = logging.getLogger("uvicorn.access")
    before = log.level

    def passes(path):
        r = log.makeRecord(
            log.name,
            logging.INFO,
            "",
            0,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:1", "GET", path, "1.1", 200),
            None,
        )
        return bool(log.filter(r)), r.levelname

    try:
        log.setLevel(logging.INFO)
        assert passes("/health") == (False, "DEBUG")
        assert passes("/v1/runs/latest") == (True, "INFO")
        log.setLevel(logging.DEBUG)
        assert passes("/health") == (True, "DEBUG")
    finally:
        log.setLevel(before)


def test_auth_rejected(client):
    assert client.get("/v1/editions").status_code == 401
    r = client.get("/v1/editions", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_run_is_idempotent_and_reaches_final_state(client):
    r1 = client.post("/v1/runs", json={"categories": ["80s-indie-pop"]}, headers=AUTH)
    assert r1.status_code == 202
    assert r1.json()["status"] == "queued"
    r2 = client.post("/v1/runs", headers=AUTH)
    assert r2.status_code == 200
    assert r2.json()["runId"] == r1.json()["runId"]
    final = wait_final(client, r1.json()["runId"])
    assert final["status"] == "succeeded"
    assert final["categories"][0]["status"] == "written"
    assert final["finishedAt"]
    assert client.get("/v1/runs/latest", headers=AUTH).json()["runId"] == final["runId"]


def test_unknown_category(client):
    r = client.post("/v1/runs", json={"categories": ["nope"]}, headers=AUTH)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNKNOWN_CATEGORY"
    assert client.get("/v1/runs/nope", headers=AUTH).status_code == 404


def test_editions_from_output_folder(root, client):
    d = root / "output" / "80s-indie-pop"
    d.mkdir(parents=True)
    for day in ("2026-09-20", "2026-09-27"):
        (d / f"{day}.json").write_text(json.dumps({"editionDate": day, "tracks": [{}] * 40}))
    assert client.get("/v1/editions", headers=AUTH).json() == [
        {
            "category": "80s-indie-pop",
            "title": "80s indie pop",
            "year": "1980-1989",
            "editionDate": "2026-09-27",
            "trackCount": 40,
        }
    ]
    assert (
        client.get("/v1/editions/80s-indie-pop", headers=AUTH).json()["editionDate"] == "2026-09-27"
    )
    r = client.get("/v1/editions/80s-indie-pop", params={"date": "2026-09-20"}, headers=AUTH)
    assert r.json()["editionDate"] == "2026-09-20"
    assert client.get("/v1/editions/current-pop", headers=AUTH).status_code == 404


def test_interrupted_run_marked_failed_on_startup(root):
    (root / "runs").mkdir()
    stale = {
        "runId": "2026-01-01T00-00-00Z",
        "status": "running",
        "requestedAt": "2026-01-01T00:00:00Z",
        "startedAt": "2026-01-01T00:00:01Z",
        "finishedAt": None,
        "categories": [
            {
                "key": "current-pop",
                "status": "running",
                "editionDate": None,
                "trackCount": None,
                "message": None,
            }
        ],
    }
    (root / "runs" / "2026-01-01T00-00-00Z.json").write_text(json.dumps(stale))
    with TestClient(service.app) as c:
        r = c.get("/v1/runs/2026-01-01T00-00-00Z", headers=AUTH).json()
    assert r["status"] == "failed"
    assert r["categories"][0] == stale["categories"][0] | {
        "status": "error",
        "message": "interrupted by restart",
    }
    assert (
        json.loads((root / "runs" / "2026-01-01T00-00-00Z.json").read_text())["status"] == "failed"
    )


def test_refuses_to_start_without_token(root, monkeypatch):
    monkeypatch.setenv("CURATOR_TOKEN", "short")
    with pytest.raises(RuntimeError, match="CURATOR_TOKEN"), TestClient(service.app):
        pass


def test_token_from_file(root, monkeypatch):
    monkeypatch.delenv("CURATOR_TOKEN")
    (root / "token").write_text(TOKEN + "\n")
    monkeypatch.setenv("CURATOR_TOKEN_FILE", str(root / "token"))
    with TestClient(service.app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.get("/v1/editions", headers=AUTH).status_code == 200
        assert c.get("/v1/editions", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_install_data_folder_holds_token_and_state(root, tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "curator.token").write_text(TOKEN + "\n")
    monkeypatch.delenv("CURATOR_TOKEN")
    monkeypatch.setenv("CURATOR_DATA_DIR", str(data))
    with TestClient(service.app) as c:
        rid = c.post("/v1/runs", json={"categories": ["80s-indie-pop"]}, headers=AUTH)
        wait_final(c, rid.json()["runId"])
    assert (data / "curator" / "runs" / f"{rid.json()['runId']}.json").exists()
    assert not (root / "runs").exists()  # categories.yaml still comes from CURATOR_ROOT


def test_both_token_sources_refused(root, monkeypatch):
    (root / "token").write_text(TOKEN)
    monkeypatch.setenv("CURATOR_TOKEN_FILE", str(root / "token"))  # root also sets CURATOR_TOKEN
    with pytest.raises(RuntimeError, match="not both"), TestClient(service.app):
        pass


def test_short_token_file_refused(root, monkeypatch):
    monkeypatch.delenv("CURATOR_TOKEN")
    (root / "token").write_text("fifteen-chars-x")
    monkeypatch.setenv("CURATOR_TOKEN_FILE", str(root / "token"))
    with pytest.raises(RuntimeError, match="CURATOR_TOKEN_FILE"), TestClient(service.app):
        pass


def test_run_is_partial_when_only_some_categories_produce_an_edition(client, monkeypatch):
    import curator.service as svc

    def fake(key, cat, *, root):
        if key == "90s-grime":
            return {
                "status": "no_albums",
                "editionDate": "2026-01-01",
                "trackCount": None,
                "message": "none",
            }
        return {"status": "written", "editionDate": "2026-01-01", "trackCount": 40, "message": "ok"}

    monkeypatch.setattr(svc, "run_category", fake)
    rid = client.post(
        "/v1/runs", json={"categories": ["80s-indie-pop", "90s-grime"]}, headers=AUTH
    ).json()["runId"]
    final = wait_final(client, rid)
    assert final["status"] == "partial"


def test_search_reports_are_appended_one_line_each(root, client):
    batch = {"schema": 1, "reports": [{"id": "a", "song": {"title": "Wonderwall"}}, {"id": "b"}]}
    assert client.post("/v1/search-reports", json=batch).status_code == 401
    assert client.post("/v1/search-reports", json=batch, headers=AUTH).json() == {"stored": 2}
    empty = {"schema": 1, "reports": []}
    assert client.post("/v1/search-reports", json=empty, headers=AUTH).json() == {"stored": 0}
    client.post("/v1/search-reports", json={"schema": 1, "reports": [{"id": "c"}]}, headers=AUTH)

    (f,) = (root / "reports").glob("*.jsonl")
    assert [json.loads(line)["id"] for line in f.read_text().splitlines()] == ["a", "b", "c"]


def test_search_reports_refuse_what_is_not_a_schema_1_batch(client):
    def post(body):
        return client.post("/v1/search-reports", content=body, headers=AUTH).status_code

    assert post(b"not json") == 400
    assert post(json.dumps({"schema": 2, "reports": []})) == 400
    assert post(json.dumps({"schema": 1, "reports": ["x"]})) == 400
    assert post(b" " * (service.MAX_REPORT_BYTES + 1)) == 413


def test_search_report_sender_address_is_never_logged():
    log = logging.getLogger("uvicorn.access")
    args = ("203.0.113.7:5123", "POST", "/v1/search-reports", "1.1", 200)
    r = log.makeRecord(log.name, logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', args, None)
    assert log.filter(r)
    assert "203.0.113.7" not in r.getMessage()
