"""HTTP service: naviseerr POSTs /v1/runs weekly, one worker builds editions, naviseerr polls."""

import hmac
import json
import os
import queue
import sys
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import run as _run
from .run import run_category  # module attribute so tests can monkeypatch it

ROOT = _run.ROOT
TOKEN = ""
RUNS: dict[str, dict] = {}
LOCK = threading.Lock()  # ponytail: one global lock and one worker; fine for a weekly job
QUEUE: queue.Queue = queue.Queue()
FINAL = {"succeeded", "partial", "failed"}


def _now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _token():
    t = os.environ.get("CURATOR_TOKEN", "")
    if len(t) < 16:  # uvicorn exits non-zero when startup raises
        raise RuntimeError(
            "CURATOR_TOKEN must be set and at least 16 characters (openssl rand -hex 32)"
        )
    return t


def _error(status, code, message):
    return HTTPException(status, {"code": code, "message": message})


def _save(r):
    d = ROOT / "runs"
    d.mkdir(exist_ok=True)
    (d / f"{r['runId']}.json").write_text(json.dumps(r, indent=1) + "\n")


def _worker():
    while (rid := QUEUE.get()) is not None:
        r = RUNS[rid]
        cats = _run.categories(ROOT)
        with LOCK:
            r.update(status="running", startedAt=_now())
            _save(r)
        for c in r["categories"]:
            with LOCK:
                c["status"] = "running"
                _save(r)
            try:  # a category removed from categories.yaml mid-run is an error, not a crash
                res = run_category(c["key"], cats[c["key"]], root=ROOT)
            except Exception as e:  # one failure never stops the other categories
                res = {"status": "error", "message": f"{type(e).__name__}: {e}"}
            with LOCK:
                c.update(res)
                _save(r)
        good = sum(c["status"] in ("written", "exists") for c in r["categories"])
        status = "succeeded" if good == len(r["categories"]) else "partial" if good else "failed"
        with LOCK:
            r.update(status=status, finishedAt=_now())
            _save(r)


@asynccontextmanager
async def lifespan(app):
    global ROOT, TOKEN
    TOKEN = _token()
    ROOT = Path(os.environ.get("CURATOR_ROOT") or _run.ROOT)
    RUNS.clear()
    for f in sorted((ROOT / "runs").glob("*.json")):
        r = json.loads(f.read_text())
        if r["status"] not in FINAL:
            r.update(status="failed", finishedAt=_now())
            for c in r["categories"]:
                if c["status"] in ("queued", "running"):
                    c.update(status="error", message="interrupted by restart")
            _save(r)
        RUNS[r["runId"]] = r
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    yield
    QUEUE.put(None)
    t.join(timeout=5)


def auth(request: Request):
    got = request.headers.get("authorization", "")
    if not (got.startswith("Bearer ") and hmac.compare_digest(got[7:], TOKEN)):
        raise _error(401, "UNAUTHORIZED", "missing or invalid bearer token")


app = FastAPI(title="playlist-curator", lifespan=lifespan)
v1 = dict(dependencies=[Depends(auth)])
BODY = Body(None)


@app.exception_handler(HTTPException)
async def _http_error(request, exc):
    detail = (
        exc.detail if isinstance(exc.detail, dict) else {"code": "ERROR", "message": exc.detail}
    )
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/runs", **v1)
def post_run(body: dict | None = BODY):
    cats = _run.categories(ROOT)
    keys = (body or {}).get("categories") or list(cats)
    unknown = [k for k in keys if k not in cats]
    if unknown:
        raise _error(400, "UNKNOWN_CATEGORY", f"unknown: {unknown}; known: {list(cats)}")
    with LOCK:
        active = next((r for r in RUNS.values() if r["status"] not in FINAL), None)
        if active:
            return active
        now = _now()
        rid = now.replace(":", "-")
        r = {
            "runId": rid,
            "status": "queued",
            "requestedAt": now,
            "startedAt": None,
            "finishedAt": None,
            "categories": [
                {
                    "key": k,
                    "status": "queued",
                    "editionDate": None,
                    "trackCount": None,
                    "message": None,
                }
                for k in keys
            ],
        }
        RUNS[rid] = r
        _save(r)
    QUEUE.put(rid)
    return JSONResponse(r, status_code=202)


@app.get("/v1/runs/latest", **v1)
def latest_run():
    if not RUNS:
        raise _error(404, "NOT_FOUND", "no run yet")
    return RUNS[max(RUNS)]


@app.get("/v1/runs/{run_id}", **v1)
def get_run(run_id: str):
    if run_id not in RUNS:
        raise _error(404, "NOT_FOUND", f"no run {run_id}")
    return RUNS[run_id]


def _edition_file(key, date=None):
    d = ROOT / "output" / key
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if date:
        files = [f for f in files if f.stem == date]
    return files[-1] if files else None


@app.get("/v1/editions", **v1)
def editions():
    out = []
    for key, cat in _run.categories(ROOT).items():
        if f := _edition_file(key):
            ed = json.loads(f.read_text())
            out.append(
                {
                    "category": key,
                    "title": cat["title"],
                    "editionDate": f.stem,
                    "trackCount": len(ed["tracks"]),
                }
            )
    return out


@app.get("/v1/editions/{key}", **v1)
def edition(key: str, date: str | None = None):
    if not (f := _edition_file(key, date)):
        raise _error(404, "NOT_FOUND", f"no edition for {key}" + (f" on {date}" if date else ""))
    return json.loads(f.read_text())


def main():
    import uvicorn

    try:
        _token()
    except RuntimeError as e:
        sys.exit(str(e))
    uvicorn.run("curator.service:app", host="0.0.0.0", port=8010)
