from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import fitz
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from lxml import etree
from starlette.background import BackgroundTask

app = FastAPI(title="legal-document-renderer", docs_url=None, redoc_url=None)
TOKEN = os.getenv("LEGAL_DRAFTING_RENDERER_TOKEN", "")
W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _authorize(value: str | None) -> None:
    if not TOKEN or value != TOKEN:
        raise HTTPException(status_code=401, detail="renderer service token invalid")


def _run(command: list[str], timeout: int = 120) -> str:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {output[-2000:]}")
    return output


def _visible_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return "".join(root.xpath("//w:t/text()", namespaces=W_NS))


def _requested_docx_fonts(path: Path) -> list[str]:
    fonts: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            try:
                root = etree.fromstring(archive.read(name))
            except etree.XMLSyntaxError:
                continue
            for node in root.xpath("//w:rFonts", namespaces=W_NS):
                for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
                    value = node.get(W + attribute)
                    if value and not value.startswith("+"):
                        fonts.add(value.strip())
    return sorted(fonts, key=str.casefold)


def _font_report(docx_path: Path, pdf_path: Path) -> dict:
    inventory_lines = _run(["fc-list", ":", "family"], timeout=30).splitlines()
    available = {
        alias.strip().casefold()
        for line in inventory_lines
        for alias in line.split(",")
        if alias.strip()
    }
    requested = _requested_docx_fonts(docx_path)
    unavailable = [font for font in requested if font.casefold() not in available]
    return {
        "requested_docx_fonts": requested,
        "font_inventory": inventory_lines[:500],
        "unavailable_requested_fonts": unavailable,
        "font_substitution_detected": bool(unavailable),
        "pdf_fonts": _run(["pdffonts", str(pdf_path)], timeout=30).splitlines()[:500],
    }


def _pdf_report(pdf_path: Path) -> dict:
    document = fitz.open(pdf_path)
    try:
        page_text_lengths = [len(page.get_text().strip()) for page in document]
        blank_pages = [index + 1 for index, length in enumerate(page_text_lengths) if length == 0]
        return {
            "page_count": document.page_count,
            "blank_pages": blank_pages,
            "page_text_lengths": page_text_lengths,
        }
    finally:
        document.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/render")
async def render(
    docx: UploadFile = File(...),
    x_renderer_token: str | None = Header(default=None),
):
    _authorize(x_renderer_token)
    content = await docx.read()
    if not content.startswith(b"PK") or len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="invalid DOCX")
    job_root = Path(tempfile.mkdtemp(prefix="legal-render-"))
    source = job_root / "draft.docx"
    source.write_bytes(content)
    try:
        office_output = _run(
            [
                "soffice",
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                str(job_root),
                str(source),
            ]
        )
        pdf = job_root / "draft.pdf"
        if not pdf.exists():
            raise RuntimeError(f"LibreOffice did not create PDF: {office_output}")
        pages_dir = job_root / "pages"
        pages_dir.mkdir()
        _run(["pdftoppm", "-png", "-r", "120", str(pdf), str(pages_dir / "page")])
        visible_text = _visible_docx_text(source)
        report = {
            "renderer": "libreoffice",
            "docx_sha256": hashlib.sha256(content).hexdigest(),
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "residual_placeholders": [
                marker
                for marker in ("{pic_qmPath}", "{{", "待替换占位符")
                if marker in visible_text
            ],
            "office_output": office_output[-1000:],
            **_font_report(source, pdf),
            **_pdf_report(pdf),
        }
        report_path = job_root / "render-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle = job_root / "render-result.zip"
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(pdf, "draft.pdf")
            archive.write(report_path, "render-report.json")
            for page in sorted(pages_dir.glob("*.png")):
                archive.write(page, f"pages/{page.name}")
        return FileResponse(
            bundle,
            media_type="application/zip",
            filename="render-result.zip",
            background=BackgroundTask(shutil.rmtree, job_root, ignore_errors=True),
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=422, detail=str(exc)[:4000]) from exc


@app.post("/convert-doc")
async def convert_doc(
    document: UploadFile = File(...),
    x_renderer_token: str | None = Header(default=None),
):
    """在隔离的 LibreOffice 容器中把旧版二进制 DOC 转成 DOCX。"""
    _authorize(x_renderer_token)
    content = await document.read()
    if not content.startswith(bytes.fromhex("D0CF11E0")) or len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="invalid legacy DOC")
    job_root = Path(tempfile.mkdtemp(prefix="legal-doc-convert-"))
    source = job_root / "source.doc"
    source.write_bytes(content)
    try:
        office_output = _run(
            [
                "soffice",
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to",
                "docx",
                "--outdir",
                str(job_root),
                str(source),
            ]
        )
        converted = job_root / "source.docx"
        if not converted.exists():
            raise RuntimeError(f"LibreOffice did not create DOCX: {office_output}")
        return FileResponse(
            converted,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="converted.docx",
            background=BackgroundTask(shutil.rmtree, job_root, ignore_errors=True),
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(job_root, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)[:4000]) from exc
