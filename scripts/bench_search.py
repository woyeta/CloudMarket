"""
Search latency benchmark.

Sends each query in a file to POST /api/search/ once, reads the Server-Timing
header, and prints p50/p95 per stage. Raw results go to a JSON file so every
number in BENCHMARKS.md can be traced back to a run.

Validity rule (default): a request only counts if it returned 200, at least one
app and an explanation. A missing explanation usually means the LLM call failed
(often a free-tier 429), which would look faster than a real search.
For outage runs (fault injection) pass --count-all, which reports every request
plus the failed-search rate instead.

Examples:
    python scripts/bench_search.py --label baseline --delay 4
    python scripts/bench_search.py --label cache-cold --flush-cache --delay 4
    python scripts/bench_search.py --label cache-warm
    python scripts/bench_search.py --label outage-fail --count-all --delay 0
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

STAGES = ("connect", "cache", "embed", "db", "llm", "keyword", "total")


def parse_server_timing(header):
    """'db;dur=8.1, llm;dur=1240;desc="miss"' -> {"db": 8.1, "llm": 1240.0}"""
    timings = {}
    for part in filter(None, (p.strip() for p in (header or "").split(","))):
        name, *params = part.split(";")
        for param in params:
            if param.startswith("dur="):
                timings[name] = float(param[4:])
    return timings


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def search(base_url, query, timeout):
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/search/", data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, payload, timing = resp.status, json.loads(resp.read()), resp.headers.get("Server-Timing")
    except urllib.error.HTTPError as e:
        status, payload, timing = e.code, {}, e.headers.get("Server-Timing")
    except (urllib.error.URLError, TimeoutError) as e:
        status, payload, timing = 0, {"error": str(e)}, None
    wall_ms = (time.perf_counter() - t0) * 1000

    return {
        "query": query,
        "status": status,
        "wall_ms": round(wall_ms, 1),
        "timing": parse_server_timing(timing),
        "mode": payload.get("mode"),
        "apps": len(payload.get("apps") or []),
        "has_explanation": bool(payload.get("explanation")) and bool(payload.get("apps")),
        "error": payload.get("error"),
    }


def flush_cache(redis_url):
    import redis  # only needed for --flush-cache

    client = redis.Redis.from_url(redis_url)
    deleted = 0
    for pattern in ("emb:v1:*", "expl:v1:*"):
        for key in client.scan_iter(pattern):
            deleted += client.delete(key)
    print(f"Flushed {deleted} cache keys")


def summarize(results, count_all):
    if count_all:
        valid = results
    else:
        valid = [r for r in results if r["status"] == 200 and r["apps"] > 0 and r["has_explanation"]]

    failed = [r for r in results if r["status"] != 200 or r["error"]]
    summary = {
        "requests": len(results),
        "valid": len(valid),
        "discarded": len(results) - len(valid),
        "failed_search_rate": round(len(failed) / len(results), 3) if results else None,
        "with_results_rate": round(sum(r["apps"] > 0 for r in results) / len(results), 3) if results else None,
        "modes": {m: sum(r["mode"] == m for r in results) for m in {r["mode"] for r in results}},
        "client_wall_ms": {
            "p50": percentile([r["wall_ms"] for r in valid], 50),
            "p95": percentile([r["wall_ms"] for r in valid], 95),
        },
        "stages_ms": {},
    }
    for stage in STAGES:
        values = [r["timing"][stage] for r in valid if stage in r["timing"]]
        if values:
            summary["stages_ms"][stage] = {
                "n": len(values),
                "p50": round(percentile(values, 50), 1),
                "p95": round(percentile(values, 95), 1),
                "mean": round(statistics.mean(values), 1),
            }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--queries", default=str(Path(__file__).with_name("search_queries.txt")))
    parser.add_argument("--label", required=True, help="name of this run, used for the output file")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between requests (Gemini rate limits)")
    parser.add_argument("--repeat", type=int, default=1, help="send the whole query list this many times")
    parser.add_argument("--limit", type=int, help="only use the first N queries (shorter runs)")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--count-all", action="store_true", help="don't discard requests (outage runs)")
    parser.add_argument("--flush-cache", action="store_true", help="delete cached embeddings/explanations first")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--out-dir", default="bench")
    args = parser.parse_args()

    queries = [q.strip() for q in Path(args.queries).read_text(encoding="utf-8").splitlines() if q.strip()]
    if args.limit:
        queries = queries[:args.limit]
    if args.flush_cache:
        flush_cache(args.redis_url)

    results = []
    total = len(queries) * args.repeat
    for i, query in enumerate(queries * args.repeat, 1):
        result = search(args.base_url, query, args.timeout)
        results.append(result)
        print(f"[{i}/{total}] {result['status']} {result['mode']} apps={result['apps']} "
              f"{result['wall_ms']:.0f} ms  {query}", file=sys.stderr)
        if args.delay and i < total:
            time.sleep(args.delay)

    summary = summarize(results, args.count_all)
    out = Path(args.out_dir)
    out.mkdir(exist_ok=True)
    out_file = out / f"{args.label}.json"
    out_file.write_text(json.dumps({"label": args.label, "args": vars(args), "summary": summary,
                                    "results": results}, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nRaw results: {out_file}")


if __name__ == "__main__":
    main()
