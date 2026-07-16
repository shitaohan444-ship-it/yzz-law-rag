"""文档解析、清洗、VL 和切片之间共享的结构化数据类型。"""
from dataclasses import dataclass, field
import hashlib


@dataclass(frozen=True)
class TextBlock:
    text: str
    page_no: int | None
    order: int
    kind: str = "paragraph"


@dataclass(frozen=True)
class ContentNode:
    """源文件中的有序内容节点。

    kind 为 text/markdown/table/image；图片节点通过 image_sha256 引用 ImageAsset，
    从而允许同一张去重图片在源文档的多个位置出现。
    """

    kind: str
    order: int
    text: str = ""
    page_no: int | None = None
    image_sha256: str | None = None


@dataclass(frozen=True)
class ImageAsset:
    content: bytes
    page_no: int | None
    page_numbers: list[int]
    image_index: int
    width: int | None
    height: int | None
    mime_type: str
    extension: str
    nearby_text: str = ""
    is_page_scan: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class ParsedDocument:
    text_blocks: list[TextBlock] = field(default_factory=list)
    images: list[ImageAsset] = field(default_factory=list)
    nodes: list[ContentNode] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(
            block.text.strip() for block in self.text_blocks if block.text.strip()
        ).strip()


@dataclass(frozen=True)
class ImageAnalysis:
    asset: ImageAsset
    status: str
    category: str | None = None
    keep_for_rag: bool = True
    filter_reason: str | None = None
    confidence: float | None = None
    description: str = ""
    extracted_text: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error_message: str | None = None

    @property
    def searchable_text(self) -> str:
        parts = [self.description.strip(), self.extracted_text.strip()]
        return "\n".join(part for part in parts if part).strip()
