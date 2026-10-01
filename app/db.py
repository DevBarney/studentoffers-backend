from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    source_id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    offer TEXT NOT NULL,
    description TEXT,
    claim_url TEXT,
    logo TEXT,
    location TEXT,
    github_offer INTEGER NOT NULL DEFAULT 0,
    is_underrated INTEGER NOT NULL DEFAULT 0,
    featured_order INTEGER,
    hidden_gem_order INTEGER,
    urgency_badge TEXT,
    category_main TEXT,
    category_sub TEXT,
    verification_status TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    extra_json TEXT,
    has_discount_codes INTEGER NOT NULL DEFAULT 0,
    has_alt_links INTEGER NOT NULL DEFAULT 0,
    canonical_url TEXT,
    raw_json TEXT NOT NULL,
    synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_offers_slug ON offers(slug);
CREATE INDEX IF NOT EXISTS idx_offers_category ON offers(category_main);
CREATE INDEX IF NOT EXISTS idx_offers_location ON offers(location);
CREATE INDEX IF NOT EXISTS idx_offers_name ON offers(name);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at TEXT NOT NULL,
    offer_count INTEGER NOT NULL,
    full_payload INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_offers(conn: sqlite3.Connection, rows: list[dict], synced_at: str) -> int:
    sql = """
    INSERT INTO offers (
        source_id, slug, name, offer, description, claim_url, logo, location,
        github_offer, is_underrated, featured_order, hidden_gem_order, urgency_badge,
        category_main, category_sub, verification_status, tags_json, extra_json,
        has_discount_codes, has_alt_links, canonical_url, raw_json, synced_at
    ) VALUES (
        :source_id, :slug, :name, :offer, :description, :claim_url, :logo, :location,
        :github_offer, :is_underrated, :featured_order, :hidden_gem_order, :urgency_badge,
        :category_main, :category_sub, :verification_status, :tags_json, :extra_json,
        :has_discount_codes, :has_alt_links, :canonical_url, :raw_json, :synced_at
    )
    ON CONFLICT(source_id) DO UPDATE SET
        slug=excluded.slug,
        name=excluded.name,
        offer=excluded.offer,
        description=excluded.description,
        claim_url=excluded.claim_url,
        logo=excluded.logo,
        location=excluded.location,
        github_offer=excluded.github_offer,
        is_underrated=excluded.is_underrated,
        featured_order=excluded.featured_order,
        hidden_gem_order=excluded.hidden_gem_order,
        urgency_badge=excluded.urgency_badge,
        category_main=excluded.category_main,
        category_sub=excluded.category_sub,
        verification_status=excluded.verification_status,
        tags_json=excluded.tags_json,
        extra_json=excluded.extra_json,
        has_discount_codes=excluded.has_discount_codes,
        has_alt_links=excluded.has_alt_links,
        canonical_url=excluded.canonical_url,
        raw_json=excluded.raw_json,
        synced_at=excluded.synced_at
    """
    for row in rows:
        row["synced_at"] = synced_at
    conn.executemany(sql, rows)
    ids = [row["source_id"] for row in rows]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM offers WHERE source_id NOT IN ({placeholders})", ids)
    conn.commit()
    return len(rows)
