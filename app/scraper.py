"""Student Offers sync backend.

Uses the public, unauthenticated JSON directory documented at
https://www.studentoffers.co/api-docs and https://www.studentoffers.co/llms.txt.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.db import connect, upsert_offers

log = logging.getLogger("scraper")

LIST_URL = f"{settings.source_base}/api/offers"
DETAIL_URL = f"{settings.source_base}/api/offers/by-slug/{{slug}}"


class UpstreamError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "application/json",
    }


def _parse_extra(raw: Any) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"text": raw}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": raw}


def normalize(offer: dict[str, Any]) -> dict[str, Any]:
    tags = offer.get("tags") or [
        t for t in (offer.get("tag1"), offer.get("tag2"), offer.get("tag3")) if t
    ]
    extra = _parse_extra(offer.get("extra_info"))
    return {
        "source_id": int(offer["id"]),
        "slug": offer.get("slug") or "",
        "name": offer.get("name") or "",
        "offer": offer.get("offer") or "",
        "description": offer.get("description"),
        "claim_url": offer.get("claim_url"),
        "logo": offer.get("logo"),
        "location": offer.get("location"),
        "github_offer": 1 if offer.get("github_offer") else 0,
        "is_underrated": 1 if offer.get("is_underrated") else 0,
        "featured_order": offer.get("featured_order"),
        "hidden_gem_order": offer.get("hidden_gem_order"),
        "urgency_badge": offer.get("urgency_badge"),
        "category_main": offer.get("category_main"),
        "category_sub": offer.get("category_sub"),
        "verification_status": offer.get("verification_status"),
        "tags_json": json.dumps(tags),
        "extra_json": json.dumps(extra) if extra is not None else None,
        "has_discount_codes": 1 if offer.get("has_discount_codes") else 0,
        "has_alt_links": 1 if offer.get("has_alt_links") else 0,
        "canonical_url": (
            f"{settings.source_base}/offer/{offer['slug']}" if offer.get("slug") else None
        ),
        "raw_json": json.dumps(offer),
    }


def fetch_offers(*, full: bool = False) -> list[dict[str, Any]]:
    params = {"full": "1"} if full else None
    started = time.monotonic()
    with httpx.Client(timeout=settings.request_timeout, follow_redirects=True) as client:
        response = client.get(LIST_URL, params=params, headers=_headers())
    remaining = response.headers.get("RateLimit-Remaining")
    log.info(
        "upstream status=%s bytes=%s rate_remaining=%s elapsed=%.2fs",
        response.status_code,
        len(response.content),
        remaining,
        time.monotonic() - started,
    )
    if response.status_code == 429:
        retry = response.headers.get("Retry-After", "60")
        raise UpstreamError(f"Rate limited. Retry after {retry}s.", status=429)
    if response.status_code >= 400:
        raise UpstreamError(
            f"Upstream returned {response.status_code}: {response.text[:300]}",
            status=response.status_code,
        )
    payload = response.json()
    if isinstance(payload, dict) and "error" in payload:
        err = payload["error"]
        raise UpstreamError(err.get("message") or "Upstream error", status=response.status_code)
    if not isinstance(payload, list):
        raise UpstreamError("Expected a JSON array of offers")
    return payload


def fetch_offer(slug: str) -> dict[str, Any]:
    url = DETAIL_URL.format(slug=slug)
    with httpx.Client(timeout=settings.request_timeout, follow_redirects=True) as client:
        response = client.get(url, headers=_headers())
    if response.status_code == 429:
        raise UpstreamError("Rate limited.", status=429)
    if response.status_code == 404:
        raise UpstreamError("Offer not found upstream.", status=404)
    if response.status_code >= 400:
        raise UpstreamError(f"Upstream returned {response.status_code}", status=response.status_code)
    payload = response.json()
    if isinstance(payload, dict) and "error" in payload:
        raise UpstreamError(payload["error"].get("message") or "Upstream error")
    return payload


def sync(*, full: bool = False) -> dict[str, Any]:
    offers = fetch_offers(full=full)
    rows = [normalize(item) for item in offers if item.get("id") is not None]
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        written = upsert_offers(conn, rows, synced_at=now)
        conn.execute(
            "INSERT INTO sync_runs (synced_at, offer_count, full_payload, status) VALUES (?, ?, ?, ?)",
            (now, written, 1 if full else 0, "ok"),
        )
    return {
        "synced_at": now,
        "offer_count": written,
        "full": full,
        "source": LIST_URL,
    }
