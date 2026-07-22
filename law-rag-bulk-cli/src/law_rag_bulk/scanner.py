from __future__ import annotations

import hashlib
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

DOCX_CONTENT_TYPE = "[Content_Types].xml"
DOCX_DOCUMENT_XML = "word/document.xml"


@dataclass(frozen=True)
class ScanEntry:
    relative_path: str
    absolute_path: str
    title: str
    size: int
    mtime_ns: int
    sha256: str | None
    status: str
    error_message: str | None = None


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def validate_docx(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if DOCX_CONTENT_TYPE not in names or DOCX_DOCUMENT_XML not in names:
                raise ValueError("DOCX 缺少必要的 Office XML 内容")
            damaged = archive.testzip()
            if damaged is not None:
                raise ValueError(f"DOCX 压缩内容损坏: {damaged}")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("文件扩展名为 DOCX，但内容不是有效 DOCX") from exc


def _has_hidden_attribute(path: Path) -> bool:
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & 0x2)


def _inspect(root: Path, path: Path) -> ScanEntry:
    relative = path.relative_to(root).as_posix()
    stat = path.stat()

    def result(status: str, digest: str | None, message: str | None = None) -> ScanEntry:
        return ScanEntry(
            relative_path=relative,
            absolute_path=str(path),
            title=path.stem,
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=digest,
            status=status,
            error_message=message,
        )

    if path.name.startswith("~$"):
        return result("invalid", None, "跳过 Office 临时文件")
    if any(part.startswith(".") for part in path.relative_to(root).parts) or _has_hidden_attribute(
        path
    ):
        return result("invalid", None, "跳过隐藏文件")
    try:
        validate_docx(path)
        digest = sha256_file(path)
    except (OSError, ValueError) as exc:
        return result("invalid", None, str(exc))
    return result("ready", digest)


def scan_docx(root: Path, workers: int = 4) -> list[ScanEntry]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"源路径不是目录: {root}")
    candidates: list[Path] = []
    for current, directories, files in os.walk(root):
        current_path = Path(current)
        directories[:] = sorted(
            directory
            for directory in directories
            if not directory.startswith(".") and not _has_hidden_attribute(current_path / directory)
        )
        candidates.extend(
            current_path / name for name in sorted(files) if Path(name).suffix.lower() == ".docx"
        )
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        entries = list(pool.map(lambda path: _inspect(root, path), candidates))
    return sorted(entries, key=lambda item: item.relative_path.casefold())
