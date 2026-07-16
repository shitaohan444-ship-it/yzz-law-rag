"""对已启动的 /search 做可重复的正确性与延迟基准。

用法：
    python scripts/benchmark_search.py
    python scripts/benchmark_search.py --repeat 3 --warmup 1
"""
import argparse
import json
import math
import os
import statistics
import time
import urllib.request


CASES = [
    ("试用期工资最低不能少于多少", "劳动合同法", "第二十条"),
    ("没签书面合同能要双倍工资吗", "劳动合同法", "第八十二条"),
    ("合同违约金过高可以要求减少吗", "民法典合同编", "第五百八十五条"),
    (
        "工作人员执行工作任务造成他人损害公司赔吗",
        "民法典侵权责任编",
        "第一千一百九十一条",
    ),
    ("承诺生效时合同是否成立", "民法典合同编", "第四百八十三条"),
]


def _request_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    token = os.getenv("RAG_SERVICE_TOKEN", "").strip()
    user_id = os.getenv("RAG_TEST_USER_ID", "").strip()
    if bool(token) != bool(user_id):
        raise RuntimeError(
            "RAG_SERVICE_TOKEN and RAG_TEST_USER_ID must be configured together"
        )
    if token:
        headers.update(
            {
                "Authorization": f"Bearer {token}",
                "X-RAG-User-Id": user_id,
            }
        )
    return headers


def _search(base_url: str, query: str) -> tuple[float, dict]:
    payload = json.dumps({"query": query, "top_k": 3}, ensure_ascii=False).encode(
        "utf-8"
    )
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/search",
        data=payload,
        headers=_request_headers(),
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    return (time.perf_counter() - start) * 1000, body


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="law-rag-kb /search latency benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    if args.warmup < 0 or args.repeat < 1:
        parser.error("--warmup must be >= 0 and --repeat must be >= 1")

    for _ in range(args.warmup):
        _search(args.url, CASES[0][0])

    timings: list[float] = []
    passed = 0
    total = len(CASES) * args.repeat
    for run in range(1, args.repeat + 1):
        for query, expected_doc, expected_article in CASES:
            elapsed_ms, body = _search(args.url, query)
            timings.append(elapsed_ms)
            hit = body.get("hits", [{}])[0] if body.get("hits") else {}
            ok = (
                hit.get("doc_title") == expected_doc
                and hit.get("article_no") == expected_article
            )
            passed += int(ok)
            print(
                f"[{'PASS' if ok else 'FAIL'}] run={run} {elapsed_ms:7.0f}ms "
                f"{query} -> {hit.get('doc_title')}/{hit.get('article_no')}"
            )

    print("\n--- benchmark summary ---")
    print(f"correctness={passed}/{total} ({passed / total:.0%})")
    print(
        f"mean={statistics.mean(timings):.0f}ms "
        f"p50={statistics.median(timings):.0f}ms "
        f"p95={_percentile(timings, 0.95):.0f}ms "
        f"max={max(timings):.0f}ms"
    )
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
