from __future__ import annotations

import json
from pathlib import Path
import zipfile

import httpx


def render_docx(
    renderer_url: str,
    renderer_token: str,
    docx_path: str | Path,
) -> tuple[Path, dict]:
    source = Path(docx_path)
    response = httpx.post(
        f"{renderer_url.rstrip('/')}/render",
        headers={"x-renderer-token": renderer_token},
        files={
            "docx": (
                source.name,
                source.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        timeout=180,
    )
    response.raise_for_status()
    bundle = source.parent / "render-result.zip"
    bundle.write_bytes(response.content)
    with zipfile.ZipFile(bundle) as archive:
        archive.extract("draft.pdf", source.parent)
        report = json.loads(archive.read("render-report.json"))
        for member in archive.namelist():
            if member.startswith("pages/") and member.endswith(".png"):
                archive.extract(member, source.parent)
    return source.parent / "draft.pdf", report
