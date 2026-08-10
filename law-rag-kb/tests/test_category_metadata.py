from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ingest import service
from app.rag import retrieve
from app.rag.category_resolver import (
    CategoryContext,
    OfficialLink,
    resolve_document_categories,
)


def test_resolve_document_categories_returns_recursive_path_context() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "doc_id": 35,
            "doc_title": "最新文档标题",
            "category_id": 13,
            "category_name": "技术部",
            "path": ["律所工作资料", "技术部"],
            "path_ids": [3, 13],
            "effective_sensitive": False,
        }
    ]
    context_manager = MagicMock()
    context_manager.__enter__.return_value = session
    context_manager.__exit__.return_value = False

    with patch("app.rag.category_resolver.SessionLocal", return_value=context_manager):
        result = resolve_document_categories([35, 35])

    assert result[35].name == "技术部"
    assert result[35].doc_title == "最新文档标题"
    assert result[35].path == ["律所工作资料", "技术部"]
    assert result[35].path_ids == [3, 13]
    assert result[35].official_link is None


def test_resolve_document_categories_adds_one_valid_official_link_join() -> None:
    external_id = "0123456789abcdef0123456789abcdef"
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "doc_id": 35,
            "doc_title": "某法律",
            "category_id": 8,
            "category_name": "法律",
            "path": ["法律法规", "法律"],
            "path_ids": [1, 8],
            "effective_sensitive": False,
            "official_provider": "npc_flk",
            "official_external_id": external_id,
            "official_url": f"https://flk.npc.gov.cn/detail?id={external_id}",
        }
    ]
    context_manager = MagicMock()
    context_manager.__enter__.return_value = session
    context_manager.__exit__.return_value = False

    with (
        patch("app.rag.category_resolver.SessionLocal", return_value=context_manager),
        patch("app.rag.category_resolver.settings.rag_official_links_enabled", True),
    ):
        result = resolve_document_categories([35])

    assert result[35].official_link is not None
    assert result[35].official_link.label == "官网最新版"
    sql = str(session.execute.call_args.args[0])
    assert "kb_document_regulation_link" in sql
    assert session.execute.call_count == 1


def test_invalid_official_url_is_not_returned() -> None:
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "doc_id": 35,
            "doc_title": "某法律",
            "category_id": 8,
            "category_name": "法律",
            "path": ["法律法规", "法律"],
            "path_ids": [1, 8],
            "effective_sensitive": False,
            "official_provider": "npc_flk",
            "official_external_id": "0123456789abcdef0123456789abcdef",
            "official_url": "javascript:alert(1)",
        }
    ]
    context_manager = MagicMock()
    context_manager.__enter__.return_value = session
    context_manager.__exit__.return_value = False
    with (
        patch("app.rag.category_resolver.SessionLocal", return_value=context_manager),
        patch("app.rag.category_resolver.settings.rag_official_links_enabled", True),
    ):
        result = resolve_document_categories([35])
    assert result[35].official_link is None


def test_new_chunk_metadata_contains_category_id_and_full_path() -> None:
    chunk = SimpleNamespace(
        stable_id="35:m:0000",
        idx=0,
        text="测试正文",
        article_no=None,
        chapter=None,
        content_type="markdown",
        image_id=None,
        page_no=None,
        image_category=None,
    )
    row = {
        "doc_title": "测试文档",
        "doc_type": "技术部",
        "legal_category": "技术部",
        "category_id": 13,
        "category_name": "技术部",
        "category_path": ["律所工作资料", "技术部"],
        "source_type": None,
        "biz_type": None,
        "biz_id": None,
        "case_id": None,
        "dossier_no": None,
        "permission_level": "public",
    }

    records = service._build_records(35, row, [chunk], [[0.1]], [{1: 0.5}])

    assert records[0]["source"] == "技术部"
    assert records[0]["meta"]["category_id"] == 13
    assert records[0]["meta"]["category_path"] == ["律所工作资料", "技术部"]


def test_search_hydrates_latest_document_title_without_reembedding() -> None:
    recall = retrieve._RecallHit(
        chunk_id="35:m:0000",
        doc_id=35,
        chunk_idx=0,
        source="旧分类",
        text="测试正文",
        meta={"doc_title": "旧文档标题"},
        distance=0.8,
    )
    context = CategoryContext(
        doc_title="最新文档标题",
        category_id=13,
        name="技术部",
        path=["律所工作资料", "技术部"],
        path_ids=[3, 13],
        effective_sensitive=False,
        official_link=OfficialLink(
            provider="npc_flk",
            source_name="国家法律法规数据库",
            label="官网最新版",
            url="https://flk.npc.gov.cn/detail?id=0123456789abcdef0123456789abcdef",
            external_id="0123456789abcdef0123456789abcdef",
        ),
    )

    with (
        patch.object(retrieve, "hybrid_recall", return_value=[recall]),
        patch.object(retrieve.reranker, "rerank", return_value=[0.9]),
        patch.object(retrieve, "resolve_document_categories", return_value={35: context}),
        patch.object(retrieve.settings, "rerank_min_score", 0.0),
    ):
        hits = retrieve.search("测试问题", top_k=1)

    assert hits[0].doc_title == "最新文档标题"
    assert hits[0].text == "测试正文"
    assert hits[0].official_link == {
        "provider": "npc_flk",
        "source_name": "国家法律法规数据库",
        "label": "官网最新版",
        "url": "https://flk.npc.gov.cn/detail?id=0123456789abcdef0123456789abcdef",
    }
