from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings
from app.db import connect
from app.export import build_workbook
from app.scraper import UpstreamError, sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")


def ensure_cache() -> None:
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
    if count == 0:
        sync(full=False)


def row_to_offer(row) -> dict[str, Any]:
    data = dict(row)
    data["github_offer"] = bool(data["github_offer"])
    data["is_underrated"] = bool(data["is_underrated"])
    data["has_discount_codes"] = bool(data["has_discount_codes"])
    data["has_alt_links"] = bool(data["has_alt_links"])
    data["tags"] = json.loads(data.pop("tags_json") or "[]")
    extra = data.pop("extra_json")
    data["extra_info"] = json.loads(extra) if extra else None
    data.pop("raw_json", None)
    data["original_link"] = data.get("canonical_url")
    return data


@asynccontextmanager
async def lifespan(_: FastAPI):
    with connect():
        pass
    if settings.sync_on_startup:
        try:
            result = sync(full=False)
            log.info("startup sync %s", result)
        except Exception:
            log.exception("startup sync failed; API will serve the last cache")
    yield


app = FastAPI(
    title="Student Offers cache",
    description="Local cache of the public StudentOffers.co directory.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def home() -> FileResponse:
    page = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return FileResponse(page)


@app.get("/health")
def health() -> dict[str, Any]:
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        last = conn.execute("SELECT synced_at, offer_count, status FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {"ok": True, "cached_offers": count, "last_sync": dict(last) if last else None, "source": settings.source_base}


@app.post("/sync")
def run_sync(full: bool = Query(False)) -> dict[str, Any]:
    try:
        return sync(full=full)
    except UpstreamError as exc:
        raise HTTPException(status_code=exc.status or 502, detail=str(exc)) from exc


@app.get("/categories")
def categories() -> dict[str, Any]:
    ensure_cache()
    with connect() as conn:
        rows = conn.execute("SELECT category_main AS name, COUNT(*) AS count FROM offers WHERE category_main IS NOT NULL AND category_main != '' GROUP BY category_main ORDER BY count DESC, name").fetchall()
    return {"categories": [dict(row) for row in rows]}


@app.get("/offers")
def list_offers(q: str | None = None, category: str | None = None, location: str | None = None, limit: int = Query(24, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    ensure_cache()
    clauses = ["1=1"]
    params: list[Any] = []
    if q:
        like = f"%{q.strip()}%"
        clauses.append("(name LIKE ? OR offer LIKE ? OR description LIKE ? OR category_main LIKE ?)")
        params.extend([like, like, like, like])
    if category:
        clauses.append("category_main = ?")
        params.append(category)
    if location:
        clauses.append("location = ?")
        params.append(location)
    where = " AND ".join(clauses)
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM offers WHERE {where}", params).fetchone()[0]
        rows = conn.execute(f"SELECT source_id, slug, name, offer, description, claim_url, logo, location, github_offer, is_underrated, featured_order, hidden_gem_order, urgency_badge, category_main, category_sub, verification_status, tags_json, extra_json, has_discount_codes, has_alt_links, canonical_url, synced_at FROM offers WHERE {where} ORDER BY name LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "offers": [row_to_offer(row) for row in rows]}


@app.get("/offers.xlsx")
def export_offers(q: str | None = None, category: str | None = None, location: str | None = None):
    ensure_cache()
    clauses = ["1=1"]
    params: list[Any] = []
    if q:
        like = f"%{q.strip()}%"
        clauses.append("(name LIKE ? OR offer LIKE ? OR description LIKE ? OR category_main LIKE ?)")
        params.extend([like, like, like, like])
    if category:
        clauses.append("category_main = ?")
        params.append(category)
    if location:
        clauses.append("location = ?")
        params.append(location)
    where = " AND ".join(clauses)
    with connect() as conn:
        rows = conn.execute(f"SELECT source_id, slug, name, offer, description, claim_url, logo, location, github_offer, is_underrated, featured_order, hidden_gem_order, urgency_badge, category_main, category_sub, verification_status, tags_json, extra_json, has_discount_codes, has_alt_links, canonical_url, synced_at FROM offers WHERE {where} ORDER BY category_main, name", params).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No offers in cache. POST /sync first.")
    return StreamingResponse(build_workbook(rows), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=student-offers.xlsx"})


@app.get("/offers/{slug}")
def get_offer(slug: str) -> dict[str, Any]:
    ensure_cache()
    with connect() as conn:
        row = conn.execute("SELECT source_id, slug, name, offer, description, claim_url, logo, location, github_offer, is_underrated, featured_order, hidden_gem_order, urgency_badge, category_main, category_sub, verification_status, tags_json, extra_json, has_discount_codes, has_alt_links, canonical_url, synced_at FROM offers WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Offer not in cache.")
    return row_to_offer(row)
