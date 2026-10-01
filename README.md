# Student Offers backend

Local cache and search API for the public directory at [studentoffers.co](https://www.studentoffers.co).

The site documents a read-only JSON API (`GET /api/offers`, 60 requests/minute, no auth) in `/api-docs` and `/llms.txt`. This service syncs that directory into SQLite and serves filtered search. It does not scrape HTML, bypass Cloudflare, or hit `/admin`.

`robots.txt` disallows `/api/` for generic crawlers. Their agent docs still publish that API for structured reads. This client sends an identifiable User-Agent, makes one list request per sync, and stores the result so you are not polling them.

Offer details change. Always open `claim_url` before telling someone a discount is live.

## Run

```bash
cd studentoffers-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Startup syncs the directory once. Docs: http://127.0.0.1:8000/docs

## Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | Cache size and last sync |
| POST | `/sync?full=false` | Pull the public directory again |
| GET | `/categories` | Category counts |
| GET | `/offers` | Search and filter |
| GET | `/offers.xlsx` | Same filters, downloaded as Excel. Includes original link and claim link |

Query params on `/offers`: `q`, `category`, `subcategory`, `location`, `tag`, `github`, `underrated`, `verified_only`, `limit`, `offset`.

```bash
curl -X POST http://127.0.0.1:8000/sync
curl "http://127.0.0.1:8000/offers?q=spotify&limit=5"
curl -o student-offers.xlsx http://127.0.0.1:8000/offers.xlsx
curl -o ai-offers.xlsx "http://127.0.0.1:8000/offers.xlsx?category=AI%20%26%20Machine%20Learning"
```

`POST /sync?full=true` asks upstream for `?full=1` (alt links, codes, FAQ). That is still one request.

## Docker

```bash
docker build -t studentoffers-backend .
docker run --rm -p 8000:8000 -v studentoffers-data:/data studentoffers-backend
```
