# CloudMarket

![CI](https://github.com/woyeta/CloudMarket/actions/workflows/ci.yml/badge.svg)

A Django-based cloud application marketplace with a server-rendered frontend and a RESTful API built with Django REST Framework.

The app supports two user roles: **Customers** and **Developers**, enabling developers to publish applications and customers to browse, purchase, review, and download them. The REST API is documented with an auto-generated OpenAPI schema served via Swagger UI and ReDoc.

## Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/woyeta/CloudMarket.git
cd CloudMarket
pip install -r requirements.txt
```

Create a `.env` file from the example and apply migrations:

```bash
cp .env.example .env
python manage.py migrate
```

## Running the App

Run the Django development server:

```bash
python manage.py runserver
```

### API Documentation

Once the server is running, interactive API docs are available at:

- **Swagger UI**: [`/api/schema/swagger-ui/`](http://localhost:8000/api/schema/swagger-ui/)
- **ReDoc**: [`/api/schema/redoc/`](http://localhost:8000/api/schema/redoc/)

### Running Tests

Tests run against a local Postgres + pgvector container (never the Supabase database):

```bash
docker compose up -d db
DB_HOST=localhost DB_PORT=5433 DB_NAME=cloudmarket DB_USER=postgres DB_PASSWORD=postgres python manage.py test
```

GitHub Actions runs the same suite, plus a migration-drift check, on every push and pull request.

`GET /healthz` returns 503 if the database is down; Redis down is reported as `degraded` (200), since search works without it.

## Search latency

- **Per-stage timing.** Every search response has a `Server-Timing` header (`connect`, `cache`, `embed`, `db`, `llm`, `total`) and a matching log line.
- **Caching.** Query embeddings and LLM explanations are cached in Redis (`REDIS_URL`), keyed on the normalized query. Redis is optional: if it's unset or down, search calls Gemini as usual.
- **Connection reuse.** `DB_CONN_MAX_AGE` (default 60 s) keeps database connections open between requests.

Demo data and benchmarks:

```bash
docker compose up -d redis
python manage.py seed_mock_data --fixture marketplace/fixtures/demo_apps.json
python manage.py backfill_embeddings
python scripts/bench_search.py --label my-run --delay 4
```

See [BENCHMARKS.md](BENCHMARKS.md) for the method and results.
