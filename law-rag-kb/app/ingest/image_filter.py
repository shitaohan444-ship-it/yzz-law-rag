"""图片去重与无效图片预筛；法律相关小图不按尺寸直接删除。"""
from dataclasses import replace
from io import BytesIO

from PIL import Image, ImageStat, UnidentifiedImageError

from app.ingest.document import ImageAnalysis, ImageAsset


def deduplicate(images: list[ImageAsset]) -> list[ImageAsset]:
    """按内容哈希合并同一文档内重复图片，并累计页码。"""
    by_hash: dict[str, ImageAsset] = {}
    for image in images:
        existing = by_hash.get(image.sha256)
        if existing is None:
            by_hash[image.sha256] = image
            continue
        pages = sorted(set(existing.page_numbers + image.page_numbers))
        nearby = existing.nearby_text or image.nearby_text
        by_hash[image.sha256] = replace(existing, page_numbers=pages, nearby_text=nearby)
    return sorted(by_hash.values(), key=lambda image: image.image_index)


def prefilter(image: ImageAsset) -> ImageAnalysis | None:
    """无效/全透明/纯色图返回 filtered；其它图片返回 None，交给 VL。"""
    if not image.content:
        return _filtered(image, "empty_image")
    try:
        with Image.open(BytesIO(image.content)) as opened:
            opened.load()
            if "A" in opened.getbands():
                alpha = opened.getchannel("A")
                if alpha.getbbox() is None:
                    return _filtered(image, "fully_transparent")
            rgb = opened.convert("RGB")
            extrema = rgb.getextrema()
            if all(high - low <= 2 for low, high in extrema):
                stat = ImageStat.Stat(rgb)
                if max(stat.stddev) <= 1.0:
                    return _filtered(image, "solid_color")
    except (UnidentifiedImageError, OSError, ValueError):
        return _filtered(image, "invalid_image")
    return None


def _filtered(image: ImageAsset, reason: str) -> ImageAnalysis:
    return ImageAnalysis(
        asset=image,
        status="filtered",
        category="separator",
        keep_for_rag=False,
        filter_reason=reason,
        confidence=1.0,
    )
