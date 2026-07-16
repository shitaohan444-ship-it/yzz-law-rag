"""使用固定检索集测试 1/5/10 路并发的正确率、墙钟与请求延迟。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import statistics
import sys
import time
from urllib.request import Request, urlopen

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.benchmark_search import CASES, _request_headers  # noqa: E402


def _search(
    url: str, case: tuple[str, str, str], timeout: float, top_k: int
) -> tuple[bool, float]:
    query, expected_doc, expected_article = case
    payload = json.dumps({"query": query, "top_k": top_k}, ensure_ascii=False).encode()
    request = Request(
        f"{url.rstrip('/')}/search",
        data=payload,
        headers=_request_headers(),
        method="POST",
    )
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode())
    elapsed_ms = (time.perf_counter() - started) * 1000
    first = (body.get("hits") or [{}])[0]
    correct = (
        first.get("doc_title") == expected_doc
        and first.get("article_no") == expected_article
    )
    return correct, elapsed_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG /search concurrency benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="与 benchmark_search.py 保持一致，默认 3",
    )
    args = parser.parse_args()

    failures = 0
    for concurrency in args.levels:
        selected = [CASES[index % len(CASES)] for index in range(concurrency)]
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = list(
                executor.map(
                    lambda case: _search(args.url, case, args.timeout, args.top_k),
                    selected,
                )
            )
        wall_ms = (time.perf_counter() - started) * 1000
        latencies = [elapsed for _, elapsed in results]
        correct = sum(ok for ok, _ in results)
        failures += concurrency - correct
        ordered = sorted(latencies)
        p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
        print(
            f"concurrency={concurrency} correctness={correct}/{concurrency} "
            f"wall={wall_ms:.0f}ms mean={statistics.mean(latencies):.0f}ms "
            f"p50={statistics.median(latencies):.0f}ms p95={p95:.0f}ms "
            f"max={max(latencies):.0f}ms"
        )
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
