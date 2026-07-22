from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .client import PlatformClient, flatten_categories
from .reporting import write_reports
from .runner import ingest_job, retry_job, upload_job
from .scanner import scan_docx
from .storage import DEFAULT_STATE_DIR, StateStore

DEFAULT_API_URL = "http://127.0.0.1:3000"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="law-rag-bulk", description="服务器端 DOCX 断点续传导入工具"
    )
    root.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR, help="SQLite 与报告目录")
    root.add_argument("--api-url", default=DEFAULT_API_URL, help="平台 API 地址")
    root.add_argument("--timeout", type=float, default=120.0, help="普通 API 请求超时秒数")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("categories", help="列出分类并标记是否可归档")

    create = commands.add_parser("create", help="创建任务、锁定分类并扫描 DOCX")
    create.add_argument("--source", type=Path, required=True, help="DOCX 源目录")
    create.add_argument("--category-id", required=True, help="可归档分类 ID")
    create.add_argument("--name", help="任务名称，默认使用源目录名")
    create.add_argument("--hash-workers", type=int, default=4, help="扫描与 SHA-256 并发数")

    for name, help_text in [
        ("upload", "仅上传 MinIO 并登记数据库，不启动 RAG"),
        ("status", "查看任务状态"),
        ("ingest", "人工确认后单独启动 RAG 入库"),
        ("retry", "重置失败项以便重试"),
        ("report", "生成 JSON 与 CSV 报告"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--job", required=True, help="任务 ID")
        if name in {"upload", "ingest"}:
            command.add_argument("--limit", type=int, help="本次最多处理文件数")
        if name == "ingest":
            command.add_argument("--confirm", action="store_true", help="确认显式启动 RAG 入库")
            command.add_argument(
                "--ingest-timeout", type=float, default=1000.0, help="单文件入库超时秒数"
            )
        if name == "retry":
            command.add_argument("--stage", choices=["upload", "ingest"], required=True)
        if name == "report":
            command.add_argument("--output-dir", type=Path)
    return root


def _print_categories(items: list[dict[str, Any]]) -> None:
    for item in flatten_categories(items):
        path = " / ".join(str(part) for part in item.get("path", [item.get("name", "")]))
        assignable = (
            item.get("assignable") and item.get("status") == "active" and not item.get("is_system")
        )
        print(f"{item.get('id')}\t{'可归档' if assignable else '不可归档'}\t{path}")


def _find_category(items: list[dict[str, Any]], category_id: str) -> dict[str, Any]:
    for item in flatten_categories(items):
        if str(item.get("id")) == category_id:
            if (
                not item.get("assignable")
                or item.get("status") != "active"
                or item.get("is_system")
            ):
                raise ValueError("所选分类当前不可归档")
            return item
    raise ValueError(f"分类不存在: {category_id}")


def _print_counts(counts: dict[str, int]) -> None:
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "categories":
            with PlatformClient(args.api_url, timeout=args.timeout) as client:
                _print_categories(client.categories())
            return 0

        with StateStore(args.state_dir) as store:
            if args.command == "create":
                with PlatformClient(args.api_url, timeout=args.timeout) as client:
                    category = _find_category(client.categories(), args.category_id)
                entries = scan_docx(args.source, args.hash_workers)
                job_id = store.create_job(
                    name=args.name or args.source.resolve().name,
                    source_root=args.source,
                    category_id=str(category["id"]),
                    category_name=str(category["name"]),
                    category_path=[
                        str(value) for value in category.get("path", [category["name"]])
                    ],
                    api_url=args.api_url,
                    entries=entries,
                )
                print(f"任务已创建且分类已锁定: {job_id}")
                _print_counts(store.counts(job_id))
            elif args.command == "status":
                job = store.get_job(args.job)
                print(f"任务: {job.id} | {job.name}")
                print(f"源目录: {job.source_root}")
                print(f"分类: {' / '.join(job.category_path)} ({job.category_id})")
                _print_counts(store.counts(args.job))
            elif args.command == "upload":
                job = store.get_job(args.job)
                with PlatformClient(job.api_url, timeout=args.timeout) as client:
                    _print_counts(upload_job(store, args.job, client, limit=args.limit))
            elif args.command == "ingest":
                if not args.confirm:
                    raise ValueError("入库不会自动执行；请核对上传结果后显式增加 --confirm")
                job = store.get_job(args.job)
                with PlatformClient(
                    job.api_url,
                    timeout=args.timeout,
                    ingest_timeout=args.ingest_timeout,
                ) as client:
                    _print_counts(ingest_job(store, args.job, client, limit=args.limit))
            elif args.command == "retry":
                store.get_job(args.job)
                print(f"已重置 {retry_job(store, args.job, args.stage)} 个失败项")
                _print_counts(store.counts(args.job))
            elif args.command == "report":
                paths = write_reports(store, args.job, args.output_dir)
                print(f"JSON: {paths[0]}")
                print(f"CSV: {paths[1]}")
        return 0
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
