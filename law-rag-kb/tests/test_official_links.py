from app.rag.prompt import build_prompt, build_refs
from app.rag.retrieve import SearchHit


def test_official_url_is_structured_but_never_added_to_llm_prompt() -> None:
    external_id = "0123456789abcdef0123456789abcdef"
    hit = SearchHit(
        chunk_id="1:m:0000",
        doc_id=1,
        doc_title="某法律",
        source="法律",
        chunk_idx=0,
        text="第一条 测试内容。",
        score=0.9,
        official_link={
            "provider": "npc_flk",
            "source_name": "国家法律法规数据库",
            "label": "官网最新版",
            "url": f"https://flk.npc.gov.cn/detail?id={external_id}",
        },
        official_external_id=external_id,
    )

    prompt, used = build_prompt("测试问题", [hit], max_chars=1000)
    refs = build_refs(used)

    assert "flk.npc.gov.cn" not in prompt
    assert refs[0]["official_link"]["label"] == "官网最新版"
    assert refs[0]["official_regulation_id"] == external_id


def test_missing_mapping_remains_null_and_backward_compatible() -> None:
    hit = SearchHit(
        chunk_id="2:m:0000",
        doc_id=2,
        doc_title="普通资料",
        source="资料",
        chunk_idx=0,
        text="测试内容。",
        score=0.8,
    )
    refs = build_refs([hit])
    assert refs[0]["official_link"] is None
    assert refs[0]["official_regulation_id"] is None
