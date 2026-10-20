# Benchmarks

Every number here comes from `scripts/bench_search.py`. The raw per-request
results for each run are in `bench/<label>.json`.

## Method

| | |
|---|---|
| Date | 2026-10-20 (runs A, B, E–H), 2026-10-21 (runs C, D) |
| Machine | AMD Ryzen 7 6800H (8 cores / 16 threads), 15 GB RAM, Windows 11 |
| Server | waitress, 4 threads, `DEBUG=False` (`runserver` starts a thread per request, which hides connection reuse) |
| Database | Supabase free tier (Postgres 17, pgvector 0.8.2), region ap-southeast-2 (Sydney), via the session pooler. About 560 ms per query round trip from the test machine; a new connection costs about 2.8 s. |
| Cache | Redis 7 in Docker (`docker compose up -d redis`), used in runs C and D only |
| Catalog | 101 apps: 100 from `marketplace/fixtures/demo_apps.json` plus 1 existing, all embedded with `backfill_embeddings` |
| Queries | 50 natural-language queries, `scripts/search_queries.txt`, each sent once per run, one at a time |
| Counting | All runs used `--count-all` (see the Gemini note below). "Failed search" = non-200 or a non-null `error`. |

p95 from 50 samples is rough, so p50 is the headline number.

**Gemini conditions during these runs:** Gemini's generation models were returning 503 "high demand" and taking 17–22 s per call when they answered. Every explanation call in A and B hit the 4 s timeout, so no search got an explanation, but all of them still returned apps. The `llm` and `total` columns for A and B therefore reflect an overloaded LLM, capped by our timeout. They need a re-run under normal conditions. The embedding model was unaffected (about 0.85 s).

## Server command

```powershell
$env:DEBUG="False"; $env:SEARCH_ANON_THROTTLE="10000/minute"
.venv\Scripts\waitress-serve --threads=4 --listen=127.0.0.1:8000 cloud_market.wsgi:application
```

Each run below changes **one** setting. Restart the server after changing an env var.

## Latency (real Gemini)

| Run | Settings | Command | total p50 | total p95 | embed p50 | llm p50 | db p50 | connect p50 |
|---|---|---|---|---|---|---|---|---|
| A — baseline | `DB_CONN_MAX_AGE=0`, `REDIS_URL=` | `bench_search.py --label A-baseline --delay 4 --count-all` | 11.3 s ⚠️ | 11.9 s ⚠️ | 844 ms | 4.21 s ⚠️ (timeout) | 3.30 s | 2.81 s |
| B — connection reuse | `DB_CONN_MAX_AGE=60`, `REDIS_URL=` | `--label B-conn-reuse --delay 4 --count-all` | 11.3 s ⚠️ | 12.1 s ⚠️ | 845 ms | 4.22 s ⚠️ (timeout) | 3.33 s | 2.84 s |
| C — cache cold | `DB_CONN_MAX_AGE=600`, `REDIS_URL=redis://localhost:6379/0`, `GEMINI_LLM_TIMEOUT_MS=10000` | `--label C-cache-cold --flush-cache --limit 20` | 10.6 s | 12.9 s | 853 ms | 6.19 s | 2.88 s | 0 ms |
| D — cache warm (repeat queries) | same as C | `--label D-cache-warm --limit 20` | **3.49 s** | 11.8 s | — (20/20 hits) | — (13/20 hits) | 2.87 s | 0 ms |

⚠️ = affected by the Gemini overload described above.

`--delay 4` keeps A and B under Gemini free-tier rate limits (each is about 50 embedding + 50 LLM calls).

C and D are trimmed to the first 20 queries with no pause (about 5 minutes for both, 40 Gemini calls). Each search takes over 6 s, which keeps the LLM under 10 calls a minute. With 20 samples only p50 is meaningful. C and D both use `DB_CONN_MAX_AGE=600`, so C is the "before" for D. Run C only when Gemini is responding normally: failed explanations are never cached, so D would keep calling the LLM.

**Cache runs (C → D), same 20 queries, same server:**
- The 13 queries whose explanation succeeded in C were full cache hits in D: median **11.2 s → 3.4 s (−70%)**, with **zero Gemini calls**. What remains is database time (`db` p50 2.87 s).
- 7 of C's 20 explanations failed (Gemini was slow, 4–9 s per call). Failures are never cached, so D called the LLM again for those 7; that's why D's p95 is still 11.8 s.
- Across all 20 queries: median 10.6 s → 3.5 s, and Gemini calls went from 40 to 7.
- A Redis lookup costs 2–5 ms.
- `connect` stayed at 0 ms in both runs: with `DB_CONN_MAX_AGE=600` (and one warm-up request per server thread), connections were reused.
- The explanation timeout was raised to 10 s for C and D because Gemini's generation latency was 4–9 s that day; with the default 4 s, almost every explanation fails, nothing gets cached, and D measures nothing.

**Where the time went (run A, p50):** database connect 2.81 s + queries 3.30 s = 6.1 s, about 54% of the 11.3 s request. The embedding call is 0.84 s (7%). The explanation call is capped at 4.2 s by the timeout; without the timeout it would have been 17–22 s.

**Why B didn't help:** 42 of 50 requests in B still opened a new connection. `CONN_MAX_AGE` is the maximum *age* of a connection, not how long it may sit idle. With 4 server threads and about 15 s between requests (11 s request + 4 s delay), each thread's turn comes around about every 60 s, by which point its connection has reached the 60 s limit and is closed. The outage runs below, where requests are about 1 s apart, show reuse working (`connect` p50 = 0 ms). The next run to try is `DB_CONN_MAX_AGE=600`, or `--threads=1` for a single-user benchmark.

## Reliability (simulated Gemini outage)

Fault runs never call Gemini, so they cost no quota. Use `REDIS_URL=` so every request goes through the embedding path.

"Failed search" = non-200 or a non-null `error`. The API reports outages as HTTP 200 + error, so status codes alone would miss them.

| Run | Settings | Command | failed searches | with results | total p50 | total p95 |
|---|---|---|---|---|---|---|
| E — before, Gemini failing | `ALLOW_FAULT_INJECTION=True`, `GEMINI_FAULT=fail`, `SEARCH_FALLBACK_ENABLED=False` | `--label E-fail-before --count-all` | 100% | 0% | 890 ms | 1.13 s |
| F — after, Gemini failing | `GEMINI_FAULT=fail`, fallback on | `--label F-fail-after --count-all` | **0%** | **100%** | 3.40 s | 6.14 s |
| G — before, Gemini hanging | `GEMINI_FAULT=hang` (10 s), `GEMINI_EMBED_TIMEOUT_MS=0`, fallback off | `--label G-hang-before --count-all` | 100% | 0% | 13.1 s | 13.9 s |
| H — after, Gemini hanging | `GEMINI_FAULT=hang` (10 s), `GEMINI_EMBED_TIMEOUT_MS=2000`, fallback on | `--label H-hang-after --count-all` | **0%** | **100%** | 5.19 s | 8.12 s |

- E is faster than F only because it gives up immediately with an error.
- F's time is almost all database round trips: `db` p50 2.81 s for the keyword query plus the category/OS lookups.
- In H every request waits out the 2 s embedding timeout (`embed` p50 = 2000 ms) before falling back; the rest is database time (`db` p50 2.66 s). A circuit breaker would remove the 2 s wait after the first few failures.

## Results summary

- **Outage (reliability):** with Gemini failing, failed searches went from 100% to 0% (E → F), and every search returned results through the keyword fallback. With Gemini hanging, failed searches went from 100% to 0% and p50 latency from 13.1 s to 5.2 s (G → H).
- **Caching (repeat queries):** median search latency went from 11.2 s to 3.4 s (−70%) with no Gemini calls on full cache hits (C → D).
- **Profiling:** against a remote Supabase database, connection setup plus queries were about 54% of request time, and the embedding call only 7%. After caching, database round trips are nearly all of the remaining 3.4 s, so reducing them is the next latency win.
- **Still to measure:** A and B under normal Gemini conditions, and B again with `DB_CONN_MAX_AGE=600` (C and D suggest it removes the ~2.8 s connect cost).
