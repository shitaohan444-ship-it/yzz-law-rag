from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import logging
import mimetypes
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Literal
import zipfile

import fitz
import httpx
from PIL import Image
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.storage import download as storage_download
from app.drafting_lite.evidence_directory import (
    EvidenceDirectoryResult,
    EvidenceItem,
    EvidenceSourceRef,
)


logger = logging.getLogger("uvicorn.error")

SCHEMA_VERSION = "evidence_media_package.v1"
ARTIFACT_TYPE = "evidence_package"
_WORD_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MIME = "application/pdf"
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


class PackagedEvidenceFile(BaseModel):
    package_path: str
    media_type: str
    original_file_name: str
    original_sha256: str
    output_sha256: str
    page_ranges: list[str] = Field(default_factory=list)
    transform_method: str
    fallback_level: str
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    validation_issues: list[str] = Field(default_factory=list)


class EvidencePackageItem(BaseModel):
    evidence_id: str
    sequence: int = Field(ge=1)
    evidence_name: str
    packaged_files: list[PackagedEvidenceFile] = Field(default_factory=list)
    validation_issues: list[str] = Field(default_factory=list)


class EvidenceMediaPackageResult(BaseModel):
    version: Literal["evidence_media_package.v1"] = SCHEMA_VERSION
    status: Literal["generated", "partial"]
    items: list[EvidencePackageItem]
    validation_issues: list[str] = Field(default_factory=list)
    package_filename: str
    package_sha256: str


class EvidenceSourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class _SourceAsset:
    identity: str
    path: Path
    file_name: str
    mime_type: str
    source_kind: str
    sha256: str


def _safe_name(value: str, *, limit: int = 80, default: str = "证据") -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return cleaned[:limit].rstrip(" ._") or default


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _chinese_number(value: int) -> str:
    if value <= 0 or value >= 10_000:
        return str(value)
    digits = "零一二三四五六七八九"
    units = ["", "十", "百", "千"]
    result: list[str] = []
    zero_pending = False
    for index, char in enumerate(str(value)):
        digit = int(char)
        position = len(str(value)) - index - 1
        if digit == 0:
            zero_pending = bool(result)
            continue
        if zero_pending:
            result.append("零")
            zero_pending = False
        if not (digit == 1 and position == 1 and not result):
            result.append(digits[digit])
        result.append(units[position])
    return "".join(result)


def _extension_for_mime(mime_type: str | None) -> str:
    normalized = str(mime_type or "").lower().split(";", 1)[0].strip()
    return {
        "application/pdf": ".pdf",
        _WORD_MIME: ".docx",
        "application/msword": ".doc",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tiff",
        "image/bmp": ".bmp",
        "image/webp": ".webp",
    }.get(normalized) or mimetypes.guess_extension(normalized) or ""


def _public_ref(ref: EvidenceSourceRef) -> dict[str, Any]:
    value = ref.model_dump(mode="json", exclude_none=True)
    # stored_name is an internal randomized task filename and has no audit value
    # for the downloader. Object-store keys are never part of EvidenceSourceRef.
    value.pop("stored_name", None)
    return value


def _validate_zip_member(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not name:
        raise ValueError("证据材料包包含非法路径")


class _SourceRegistry:
    def __init__(
        self,
        job_id: str,
        manifest: list[dict[str, Any]],
        jobs_root: Path,
    ) -> None:
        self.job_id = job_id
        self.manifest = manifest
        self.input_root = (jobs_root / job_id / "input").resolve()
        self.cache_root = self.input_root / "evidence-sources"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._snapshots: dict[int, dict[str, Any]] = {}
        self._assets: dict[str, _SourceAsset] = {}
        self._source_bytes = sum(
            int(item.get("size") or 0)
            for item in manifest
            if item.get("source_kind") == "upload"
        )

    def _manifest_item(self, material_id: int) -> dict[str, Any]:
        if material_id <= 0 or material_id > len(self.manifest):
            raise EvidenceSourceUnavailable("材料编号不存在")
        item = self.manifest[material_id - 1]
        if not isinstance(item, dict):
            raise EvidenceSourceUnavailable("材料清单无效")
        return item

    def _snapshot(self, material_id: int, item: dict[str, Any]) -> dict[str, Any]:
        cached = self._snapshots.get(material_id)
        if cached is not None:
            return cached
        snapshot_name = str(item.get("snapshot_name") or "")
        path = (self.input_root / snapshot_name).resolve()
        if self.input_root not in path.parents or not path.is_file():
            raise EvidenceSourceUnavailable("知识库材料快照不存在")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise EvidenceSourceUnavailable("知识库材料快照损坏") from exc
        if not isinstance(value, dict):
            raise EvidenceSourceUnavailable("知识库材料快照格式无效")
        self._snapshots[material_id] = value
        return value

    def _download_asset(
        self,
        identity: str,
        metadata: dict[str, Any],
        *,
        file_name: str,
        source_kind: str,
    ) -> _SourceAsset:
        cached = self._assets.get(identity)
        if cached is not None:
            return cached
        bucket = str(metadata.get("bucket") or "")
        object_key = str(metadata.get("object_key") or "")
        if not bucket or not object_key:
            raise EvidenceSourceUnavailable("知识库原件没有可用的对象存储定位")
        try:
            content = storage_download(object_key, bucket)
        except Exception as exc:
            logger.warning(
                "drafting_lite evidence source download failed job_id=%s identity=%s type=%s",
                self.job_id,
                identity,
                type(exc).__name__,
            )
            raise EvidenceSourceUnavailable("知识库原件下载失败") from exc
        if not content:
            raise EvidenceSourceUnavailable("知识库原件内容为空")
        if self._source_bytes + len(content) > settings.drafting_lite_max_total_bytes:
            raise EvidenceSourceUnavailable("证据原件累计大小超过100MB限制")
        self._source_bytes += len(content)
        mime_type = str(metadata.get("mime_type") or "application/octet-stream")
        suffix = Path(file_name).suffix.lower() or _extension_for_mime(mime_type)
        local = self.cache_root / f"{hashlib.sha256(identity.encode()).hexdigest()[:20]}{suffix}"
        temporary = local.with_suffix(local.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(local)
        asset = _SourceAsset(
            identity=identity,
            path=local,
            file_name=file_name,
            mime_type=mime_type,
            source_kind=source_kind,
            sha256=_sha256(content),
        )
        self._assets[identity] = asset
        return asset

    def resolve(self, ref: EvidenceSourceRef) -> _SourceAsset:
        item = self._manifest_item(ref.material_id)
        if item.get("source_kind") != "knowledge":
            stored_name = str(ref.stored_name or item.get("stored_name") or "")
            path = (self.input_root / stored_name).resolve()
            if self.input_root not in path.parents or not path.is_file():
                raise EvidenceSourceUnavailable("上传原件不存在")
            content = path.read_bytes()
            expected = str(item.get("sha256") or "")
            digest = _sha256(content)
            if expected and digest != expected:
                raise EvidenceSourceUnavailable("上传原件哈希校验失败")
            identity = f"upload:{stored_name}:{digest}"
            cached = self._assets.get(identity)
            if cached is not None:
                return cached
            asset = _SourceAsset(
                identity=identity,
                path=path,
                file_name=str(item.get("name") or ref.file_name or path.name),
                mime_type=str(item.get("mime_type") or "application/octet-stream"),
                source_kind="upload",
                sha256=digest,
            )
            self._assets[identity] = asset
            return asset

        snapshot = self._snapshot(ref.material_id, item)
        document_id = int(snapshot.get("document_id") or ref.document_id or 0)
        if ref.image_id not in (None, ""):
            image_id = int(ref.image_id)
            image = next(
                (
                    value
                    for value in snapshot.get("images") or []
                    if int(value.get("image_id") or 0) == image_id
                ),
                None,
            )
            if image is None:
                raise EvidenceSourceUnavailable("知识库图片原件不存在")
            extension = _extension_for_mime(str(image.get("mime_type") or "")) or ".png"
            return self._download_asset(
                f"knowledge-image:{document_id}:{image_id}",
                image,
                file_name=f"图片{image_id}{extension}",
                source_kind="knowledge_image",
            )

        sources = [value for value in snapshot.get("sources") or [] if isinstance(value, dict)]
        primary_attachment = snapshot.get("primary_attachment")
        if not isinstance(primary_attachment, dict):
            primary_attachment = None
        selected: dict[str, Any] | None = None
        if ref.source_id not in (None, ""):
            selected = next(
                (
                    value
                    for value in sources
                    if int(value.get("source_id") or 0) == int(ref.source_id)
                ),
                None,
            )
            if selected is None:
                raise EvidenceSourceUnavailable("Chunk对应的知识库来源不存在")
        if selected is None:
            primary = [value for value in sources if bool(value.get("is_primary"))]
            if len(primary) == 1:
                selected = primary[0]
            elif primary_attachment is not None:
                selected = primary_attachment
            elif len(sources) == 1:
                selected = sources[0]
            else:
                raise EvidenceSourceUnavailable("知识库材料存在多个来源且无法确定原件")
        source_id = int(selected.get("source_id") or selected.get("attachment_id") or 0)
        file_name = str(selected.get("file_name") or selected.get("source_title") or ref.file_name)
        return self._download_asset(
            f"knowledge-attachment:{document_id}:{source_id}",
            selected,
            file_name=file_name,
            source_kind="knowledge_attachment",
        )


def _page_ranges(pages: list[int]) -> list[str]:
    if not pages:
        return []
    ranges: list[str] = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = page
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ranges


def _extract_pdf(content: bytes, refs: list[EvidenceSourceRef]) -> tuple[bytes, list[str], str, str, list[str]]:
    try:
        source = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise EvidenceSourceUnavailable("PDF原件损坏或无法打开") from exc
    try:
        raw_pages = [ref.page_no for ref in refs]
        pages = sorted({int(value) for value in raw_pages if value is not None})
        page_mapping_complete = bool(raw_pages) and all(value is not None for value in raw_pages)
        page_mapping_valid = bool(pages) and all(1 <= page <= source.page_count for page in pages)
        if page_mapping_complete and page_mapping_valid:
            output = fitz.open()
            try:
                for page in pages:
                    output.insert_pdf(source, from_page=page - 1, to_page=page - 1)
                payload = output.tobytes(garbage=4, deflate=True)
            finally:
                output.close()
            ranges = _page_ranges(pages)
            return payload, ranges, "pdf_page_subset", "exact_pages", []
        issues = []
        if pages and not page_mapping_valid:
            issues.append("source_page_out_of_range")
        else:
            issues.append("source_page_unavailable")
        return content, [], "pdf_full_source", "full_source", issues
    finally:
        source.close()


def _render_docx_to_pdf(content: bytes, file_name: str) -> bytes:
    response = httpx.post(
        f"{settings.drafting_lite_renderer_url.rstrip('/')}/render",
        headers={"x-renderer-token": settings.drafting_lite_renderer_token},
        files={"docx": (file_name, content, _WORD_MIME)},
        timeout=180,
    )
    response.raise_for_status()
    try:
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            for name in archive.namelist():
                _validate_zip_member(name)
            pdf = archive.read("draft.pdf")
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise EvidenceSourceUnavailable("Word转PDF服务返回结果无效") from exc
    try:
        document = fitz.open(stream=pdf, filetype="pdf")
        document.close()
    except Exception as exc:
        raise EvidenceSourceUnavailable("Word转换后的PDF无法打开") from exc
    return pdf


def _word_to_pdf(asset: _SourceAsset, content: bytes) -> bytes:
    extension = Path(asset.file_name).suffix.lower() or asset.path.suffix.lower()
    if extension == ".doc":
        response = httpx.post(
            f"{settings.drafting_lite_renderer_url.rstrip('/')}/convert-doc",
            headers={"x-renderer-token": settings.drafting_lite_renderer_token},
            files={"document": (asset.file_name, content, "application/msword")},
            timeout=180,
        )
        response.raise_for_status()
        content = response.content
        file_name = Path(asset.file_name).with_suffix(".docx").name
    else:
        file_name = asset.file_name
    return _render_docx_to_pdf(content, file_name)


def _normalize_asset(
    asset: _SourceAsset,
    refs: list[EvidenceSourceRef],
    conversion_cache: dict[str, bytes],
) -> tuple[bytes, str, str, list[str], str, list[str]]:
    content = asset.path.read_bytes()
    extension = (Path(asset.file_name).suffix or asset.path.suffix).lower()
    if content.startswith(b"%PDF-") or extension == ".pdf":
        payload, ranges, method, fallback, issues = _extract_pdf(content, refs)
        return payload, ".pdf", _PDF_MIME, ranges, method + ":" + fallback, issues
    if extension in {".doc", ".docx"}:
        cache_key = f"word:{asset.sha256}"
        try:
            pdf = conversion_cache.get(cache_key)
            if pdf is None:
                pdf = _word_to_pdf(asset, content)
                conversion_cache[cache_key] = pdf
        except Exception as exc:
            logger.warning(
                "drafting_lite word evidence conversion failed file=%s type=%s",
                asset.file_name,
                type(exc).__name__,
            )
            raise EvidenceSourceUnavailable("Word原件无法转换为PDF") from exc
        # DOCX解析没有稳定物理页码，完整转换版是唯一可审计的回退。
        return pdf, ".pdf", _PDF_MIME, [], "word_to_pdf:full_source", ["word_page_mapping_unavailable"]
    if extension in _IMAGE_EXTENSIONS or asset.mime_type.lower().startswith("image/"):
        try:
            image = Image.open(BytesIO(content))
            image.verify()
        except Exception as exc:
            raise EvidenceSourceUnavailable("图片原件损坏或无法打开") from exc
        if extension in {".jpg", ".jpeg", ".png"}:
            mime = "image/png" if extension == ".png" else "image/jpeg"
            return content, extension, mime, [], "image_original:original", []
        image = Image.open(BytesIO(content))
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue(), ".png", "image/png", [], "image_to_png:normalized", []
    raise EvidenceSourceUnavailable("原件格式不能规范化为照片或PDF")


def _missing_text(item: EvidenceItem, reasons: list[str]) -> str:
    unique = list(dict.fromkeys(reason for reason in reasons if reason))
    reason_text = "；".join(unique) or "没有可取得的证据原件"
    return (
        f"证据编号：证据{_chinese_number(item.sequence)}\r\n"
        f"证据名称：{item.name}\r\n"
        f"缺失原因：{reason_text}\r\n"
        "建议补充：请补充上传该证据的原始照片或PDF文件。\r\n"
    )


def _verify_package(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if not names or "000_证据目录.docx" not in names or "证据材料索引.json" not in names:
                raise ValueError("证据材料包缺少必要文件")
            for info in archive.infolist():
                _validate_zip_member(info.filename)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("证据材料包不得包含软链接")
            damaged = archive.testzip()
            if damaged:
                raise ValueError(f"证据材料包文件校验失败：{damaged}")
    except zipfile.BadZipFile as exc:
        raise ValueError("证据材料包不是有效ZIP") from exc


def render_evidence_package(
    job_id: str,
    cause_label: str,
    plaintiff_name: str,
    evidence_result: EvidenceDirectoryResult,
    evidence_directory_path: Path,
    manifest: list[dict[str, Any]],
    jobs_root: Path,
) -> tuple[Path, str, EvidenceMediaPackageResult, Path]:
    job_root = (jobs_root / job_id).resolve()
    output_root = (job_root / "output").resolve()
    if job_root not in output_root.parents:
        raise ValueError("证据材料包输出路径无效")
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root not in evidence_directory_path.resolve().parents or not evidence_directory_path.is_file():
        raise ValueError("证据目录产物不存在或路径无效")

    filename = f"{_safe_name(cause_label)}_{_safe_name(plaintiff_name, default='当事人')}_证据材料包.zip"
    output = output_root / filename
    registry = _SourceRegistry(job_id, manifest, jobs_root)
    conversion_cache: dict[str, bytes] = {}
    result_items: list[EvidencePackageItem] = []
    package_issues: list[str] = []
    packaged_bytes = evidence_directory_path.stat().st_size

    with tempfile.TemporaryDirectory(prefix="evidence-package-", dir=output_root) as temp_name:
        staging = Path(temp_name)
        shutil.copyfile(evidence_directory_path, staging / "000_证据目录.docx")
        evidence_items = list(evidence_result.items)
        if not evidence_items:
            empty_dir = staging / "001_未识别到可核验证据"
            empty_dir.mkdir()
            (empty_dir / "缺失说明.txt").write_text(
                "未识别到可核验证据，请补充上传证据照片或PDF文件。\r\n",
                encoding="utf-8-sig",
            )
            package_issues.append("no_verifiable_evidence_media")

        for item in evidence_items:
            folder_name = (
                f"{item.sequence:03d}_证据{_chinese_number(item.sequence)}_"
                f"{_safe_name(item.name, limit=60)}"
            )
            folder = staging / folder_name
            folder.mkdir()
            grouped: OrderedDict[str, tuple[_SourceAsset, list[EvidenceSourceRef]]] = OrderedDict()
            missing_reasons: list[str] = []
            for ref in item.source_refs:
                try:
                    asset = registry.resolve(ref)
                except EvidenceSourceUnavailable as exc:
                    missing_reasons.append(f"{ref.file_name}：{exc}")
                    continue
                if asset.identity not in grouped:
                    grouped[asset.identity] = (asset, [])
                grouped[asset.identity][1].append(ref)

            packaged_files: list[PackagedEvidenceFile] = []
            item_issues: list[str] = []
            for file_index, (asset, refs) in enumerate(grouped.values(), start=1):
                try:
                    payload, extension, media_type, ranges, combined_method, issues = _normalize_asset(
                        asset,
                        refs,
                        conversion_cache,
                    )
                except EvidenceSourceUnavailable as exc:
                    missing_reasons.append(f"{asset.file_name}：{exc}")
                    continue
                if packaged_bytes + len(payload) > settings.drafting_lite_max_total_bytes:
                    missing_reasons.append(f"{asset.file_name}：加入后将超过100MB证据包限制")
                    continue
                packaged_bytes += len(payload)
                method, fallback = combined_method.split(":", 1) if ":" in combined_method else (combined_method, "original")
                stem = _safe_name(Path(asset.file_name).stem, limit=48)
                page_label = f"_第{'、'.join(ranges)}页" if ranges else ("_完整" if fallback == "full_source" else "")
                local_name = f"{item.sequence:03d}-{file_index:02d}_{stem}{page_label}{extension}"
                local_path = folder / local_name
                local_path.write_bytes(payload)
                package_path = f"{folder_name}/{local_name}"
                packaged_files.append(
                    PackagedEvidenceFile(
                        package_path=package_path,
                        media_type=media_type,
                        original_file_name=asset.file_name,
                        original_sha256=asset.sha256,
                        output_sha256=_sha256(payload),
                        page_ranges=ranges,
                        transform_method=method,
                        fallback_level=fallback,
                        source_refs=[_public_ref(ref) for ref in refs],
                        validation_issues=issues,
                    )
                )
                item_issues.extend(issues)

            if missing_reasons:
                (folder / "缺失说明.txt").write_text(
                    _missing_text(item, missing_reasons),
                    encoding="utf-8-sig",
                )
                item_issues.extend(["evidence_source_unavailable"])
            if not packaged_files and not missing_reasons:
                missing_reasons.append("证据条目没有可解析的材料来源")
                (folder / "缺失说明.txt").write_text(
                    _missing_text(item, missing_reasons),
                    encoding="utf-8-sig",
                )
                item_issues.append("evidence_source_unavailable")
            result_items.append(
                EvidencePackageItem(
                    evidence_id=item.evidence_id,
                    sequence=item.sequence,
                    evidence_name=item.name,
                    packaged_files=packaged_files,
                    validation_issues=list(dict.fromkeys(item_issues)),
                )
            )

        aggregate_issues = list(
            dict.fromkeys(
                [
                    *package_issues,
                    *(
                        issue
                        for item in result_items
                        for issue in item.validation_issues
                    ),
                ]
            )
        )
        is_partial = bool(aggregate_issues)
        index_payload = {
            "version": SCHEMA_VERSION,
            "status": "partial" if is_partial else "generated",
            "items": [item.model_dump(mode="json") for item in result_items],
            "validation_issues": aggregate_issues,
        }
        (staging / "证据材料索引.json").write_text(
            json.dumps(index_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with tempfile.NamedTemporaryFile(
            suffix=".zip",
            prefix="evidence-package-",
            dir=output_root,
            delete=False,
        ) as handle:
            temporary_zip = Path(handle.name)
        try:
            with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(
                    (value for value in staging.rglob("*") if value.is_file()),
                    key=lambda value: value.relative_to(staging).as_posix(),
                ):
                    arcname = path.relative_to(staging).as_posix()
                    _validate_zip_member(arcname)
                    archive.write(path, arcname)
            _verify_package(temporary_zip)
            temporary_zip.replace(output)
        finally:
            temporary_zip.unlink(missing_ok=True)

    package_sha = _sha256(output.read_bytes())
    final_result = EvidenceMediaPackageResult(
        status="partial" if is_partial else "generated",
        items=result_items,
        validation_issues=aggregate_issues,
        package_filename=filename,
        package_sha256=package_sha,
    )
    audit_path = output_root / "evidence-package-audit.json"
    temporary_audit = audit_path.with_suffix(".tmp")
    temporary_audit.write_text(
        json.dumps(final_result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_audit.replace(audit_path)
    return output, filename, final_result, audit_path
