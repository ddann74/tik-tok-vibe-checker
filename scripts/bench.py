"""PRD §7 non-functional requirements: measures real p50/p95 latency over 20
requests against a running server, plus process memory, and writes
bench_results.json. Replaces the source report's unverified 287ms/42ms/127MB
claims with numbers you can actually reproduce.

Usage:
    uvicorn npl_engine.server:app --host 127.0.0.1 --port 8000 &
    python scripts/bench.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx


def percentile(values: list[float], pct: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    k = (len(values) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def bench_endpoint(client: httpx.Client, method: str, path: str, n: int, **kwargs) -> dict:
    durations = []
    for _ in range(n):
        start = time.perf_counter()
        r = client.request(method, path, **kwargs)
        durations.append((time.perf_counter() - start) * 1000)
        r.raise_for_status()
    return {
        "n": n,
        "p50_ms": round(percentile(durations, 0.50), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "min_ms": round(min(durations), 2),
        "max_ms": round(max(durations), 2),
        "mean_ms": round(statistics.mean(durations), 2),
    }


def process_memory_mb(pid: int | None) -> float | None:
    if pid is None:
        return None
    try:
        import psutil

        return round(psutil.Process(pid).memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--server-pid", type=int, default=None, help="PID of the uvicorn process, for memory measurement")
    parser.add_argument("--out", default="bench_results.json")
    args = parser.parse_args()

    sample_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        results = {
            "base_url": args.base_url,
            "requests_per_endpoint": args.requests,
            "GET /health": bench_endpoint(client, "GET", "/health", args.requests),
            "POST /analyze_match": bench_endpoint(
                client, "POST", "/analyze_match", args.requests, params={"url": sample_url}
            ),
            "GET /search_key_moments": bench_endpoint(
                client, "GET", "/search_key_moments", args.requests, params={"q": "goal"}
            ),
            "memory_mb": process_memory_mb(args.server_pid),
        }

    Path(args.out).write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
