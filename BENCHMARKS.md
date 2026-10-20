# Benchmarks

Every number here comes from `scripts/bench_search.py`. The raw per-request
results for each run are in `bench/<label>.json`.

## Method

| | |
|---|---|
| Machine | _fill in: CPU, RAM, OS_ |
| Server | waitress, 4 threads, `DEBUG=False` (`runserver` starts a thread per request, which hides connection reuse) |
| Database | Supabase free tier (remote Postgres + pgvector), region: _fill in_ |
| Cache | Redis 7 in Docker (`docker compose up -d redis`) |
| Catalog | 100 apps from `marketplace/fixtures/demo_apps.json`, embedded with `backfill_embeddings` |
| Queries | 50 natural-language queries, `scripts/search_queries.txt`, each sent once per run |
| Validity rule | A request counts only if it returned 200, ≥1 app and an explanation (a failed LLM call looks fast). Outage runs use `--count-all`. |

p95 from 50 samples is rough, so p50 is the headline number.

## Server command

```powershell
$env:DEBUG="False"; $env:SEARCH_ANON_THROTTLE="10000/minute"
.venv\Scripts\waitress-serve --threads=4 --listen=127.0.0.1:8000 cloud_market.wsgi:application
```

Each run below changes **one** setting. Restart the server after changing an env var.

## Latency (healthy Gemini)

| Run | Settings | Command | total p50 | total p95 | embed p50 | llm p50 | db p50 | connect p50 |
|---|---|---|---|---|---|---|---|---|
| A — baseline | `DB_CONN_MAX_AGE=0`, `REDIS_URL=` | `bench_search.py --label A-baseline --delay 4` | | | | | | |
| B — connection reuse | `DB_CONN_MAX_AGE=60`, `REDIS_URL=` | `--label B-conn-reuse --delay 4` | | | | | | |
| C — cache cold | B + `REDIS_URL=redis://localhost:6379/0` | `--label C-cache-cold --flush-cache --delay 4` | | | | | | |
| D — cache warm (repeat queries) | same as C | `--label D-cache-warm` | | | — | — | | |

`--delay 4` keeps cold runs under Gemini free-tier rate limits (each cold run is about 50 embedding + 50 LLM calls).

## Results summary

_Fill in after the runs, e.g._
- Repeat-search latency: _A total p50_ → _D total p50_.
