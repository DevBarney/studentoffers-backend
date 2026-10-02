import hashlib
import hmac
import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.db import connect
from app.scraper import UpstreamError, sync

router = APIRouter(prefix="/admin")
COOKIE = "offers_admin"
PASSWORD = os.getenv("ADMIN_PASSWORD", "offers-admin-7427")


def token() -> str:
    return hmac.new(b"student-offers-admin", PASSWORD.encode(), hashlib.sha256).hexdigest()


def require_admin(request: Request) -> None:
    if not hmac.compare_digest(request.cookies.get(COOKIE, ""), token()):
        raise HTTPException(status_code=401, detail="Admin login required")


class Login(BaseModel):
    password: str


@router.post("/login")
def login(body: Login, response: Response) -> dict:
    if not hmac.compare_digest(body.password, PASSWORD):
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(COOKIE, token(), httponly=True, samesite="lax", max_age=60 * 60 * 12)
    return {"ok": True}


@router.get("/stats")
def stats(request: Request) -> dict:
    require_admin(request)
    with connect() as conn:
        offers = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        github = conn.execute("SELECT COUNT(*) FROM offers WHERE github_offer = 1").fetchone()[0]
        categories = conn.execute("SELECT COUNT(DISTINCT category_main) FROM offers").fetchone()[0]
        last = conn.execute("SELECT synced_at, offer_count, status FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {"offers": offers, "github_pack": github, "categories": categories, "last_sync": dict(last) if last else None}


@router.post("/sync")
def admin_sync(request: Request) -> dict:
    require_admin(request)
    try:
        return sync(full=False)
    except UpstreamError as exc:
        raise HTTPException(status_code=exc.status or 502, detail=str(exc)) from exc
