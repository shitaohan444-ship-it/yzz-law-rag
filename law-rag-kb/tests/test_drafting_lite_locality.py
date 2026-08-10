from __future__ import annotations

from app.drafting_lite import locality


SOURCE = [{"source_type": "material", "file_name": "材料.pdf", "page_no": 1}]


def _party_fields(
    plaintiff: str,
    defendant: str,
) -> tuple[dict, dict]:
    fields = {
        "party.plaintiff.address": plaintiff,
        "party.defendant.address": defendant,
    }
    return fields, {field_id: SOURCE for field_id in fields}


def test_shared_province_allows_only_shared_level_local_rule():
    fields, provenance = _party_fields(
        "广东省深圳市南山区科技园1号",
        "广东省广州市天河区体育路2号",
    )
    context = locality.build_locality_context(fields, provenance)

    assert context.shared_party_regions == frozenset({"广东"})
    assert "深圳" not in context.applicable_regions
    allowed, audit = locality.authority_applicable(
        {"legal_name": "广东省劳动保障监察条例"},
        context,
    )
    assert allowed
    assert audit["matched_regions"] == ["广东"]

    city_allowed, city_audit = locality.authority_applicable(
        {"legal_name": "深圳市员工工资支付条例"},
        context,
    )
    assert not city_allowed
    assert city_audit["locality_match"] == "local_authority_region_mismatch"


def test_one_partys_region_never_selects_local_rule_by_itself():
    fields, provenance = _party_fields(
        "广东省深圳市南山区科技园1号",
        "江苏省南京市鼓楼区中山路2号",
    )
    context = locality.build_locality_context(fields, provenance)

    assert context.applicable_regions == frozenset()
    allowed, audit = locality.authority_applicable(
        {"legal_name": "广东省房屋租赁管理办法"},
        context,
    )

    assert not allowed
    assert audit["locality_match"] == "case_locality_unverified"


def test_verified_case_connection_can_select_matching_local_rule():
    fields, provenance = _party_fields(
        "广东省深圳市南山区科技园1号",
        "江苏省南京市鼓楼区中山路2号",
    )
    fields["traffic.accident.summary"] = (
        "事故发生地：上海市浦东新区世纪大道100号"
    )
    provenance["traffic.accident.summary"] = SOURCE
    context = locality.build_locality_context(fields, provenance)

    assert "上海" in context.case_connection_regions
    allowed, audit = locality.authority_applicable(
        {"legal_name": "上海市道路交通事故处理若干规定"},
        context,
    )

    assert allowed
    assert audit["matched_regions"] == ["上海"]
    assert "traffic.accident.summary" in audit["locality_evidence_fields"]


def test_unverified_case_place_does_not_create_locality_connection():
    fields, provenance = _party_fields(
        "广东省深圳市南山区科技园1号",
        "江苏省南京市鼓楼区中山路2号",
    )
    fields["trademark.infringement_place"] = "北京市朝阳区"
    context = locality.build_locality_context(fields, provenance)

    assert context.case_connection_regions == frozenset()
    allowed, _ = locality.authority_applicable(
        {"legal_name": "北京市知识产权保护条例"},
        context,
    )
    assert not allowed


def test_national_law_is_always_available_and_not_misread_as_city_rule():
    context = locality.LocalityContext()
    for title in (
        "中华人民共和国民法典",
        "中华人民共和国城市房地产管理法",
        "最高人民法院关于审理民间借贷案件适用法律若干问题的规定",
    ):
        allowed, audit = locality.authority_applicable(
            {"legal_name": title},
            context,
        )
        assert allowed, title
        assert audit["jurisdiction_scope"] == "national"


def test_local_category_without_identifiable_region_is_rejected():
    context = locality.LocalityContext(
        applicable_regions=frozenset({"广东"})
    )
    allowed, audit = locality.authority_applicable(
        {
            "legal_name": "房屋租赁实施办法",
            "category_path": ["法律法规", "地方性法规"],
        },
        context,
    )

    assert not allowed
    assert audit["locality_match"] == "local_authority_region_unknown"


def test_card_filter_keeps_national_and_matching_local_only():
    fields, provenance = _party_fields(
        "广东省深圳市南山区科技园1号",
        "广东省广州市天河区体育路2号",
    )
    cards = [
        {"legal_name": "中华人民共和国民法典", "chunk_id": "national"},
        {"legal_name": "广东省劳动保障监察条例", "chunk_id": "guangdong"},
        {"legal_name": "北京市劳动合同规定", "chunk_id": "beijing"},
    ]

    accepted, rejected, context = locality.filter_authority_cards(
        cards,
        fields,
        provenance,
    )

    assert [item["chunk_id"] for item in accepted] == [
        "national",
        "guangdong",
    ]
    assert [item["chunk_id"] for item in rejected] == ["beijing"]
    assert context.shared_party_regions == frozenset({"广东"})


def test_multiple_parties_must_all_share_region_before_address_only_match():
    fields = {
        "_party_records": {
            "plaintiff": [
                {"address": "广东省深圳市南山区"},
                {"address": "北京市朝阳区"},
            ],
            "defendant": [{"address": "广东省广州市天河区"}],
        }
    }

    context = locality.build_locality_context(fields, {})

    assert context.applicable_regions == frozenset()
    allowed, _ = locality.authority_applicable(
        {"legal_name": "广东省劳动保障监察条例"},
        context,
    )
    assert not allowed


def test_research_agent_queries_case_region_and_filters_wrong_local_law(
    monkeypatch,
):
    from app.drafting_lite import research_agent
    from app.rag import retrieve

    class FakeScalars:
        @staticmethod
        def all():
            return [1]

    class FakeResult:
        @staticmethod
        def scalars():
            return FakeScalars()

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        @staticmethod
        def execute(statement):
            return FakeResult()

    class Hit:
        def __init__(self, chunk_id, title, body):
            self.chunk_id = chunk_id
            self.doc_title = title
            self.source = "法律法规"
            self.text = body
            self.article_no = "第一条"
            self.doc_id = 1
            self.score = 0.9
            self.category_path = ["法律法规"]

    hits = [
        Hit(
            "national",
            "中华人民共和国民法典",
            "借款人应当返还借款，借款合同依法成立。",
        ),
        Hit(
            "guangdong",
            "广东省高级人民法院民间借贷审理指引",
            "民间借贷案件中借款人应当返还借款。",
        ),
        Hit(
            "beijing",
            "北京市高级人民法院民间借贷审理指引",
            "民间借贷案件中借款人应当返还借款。",
        ),
    ]
    queries = []

    def fake_search(query, **kwargs):
        queries.append(query)
        return hits

    monkeypatch.setattr(research_agent, "SessionLocal", FakeDb)
    monkeypatch.setattr(retrieve, "search", fake_search)
    monkeypatch.setattr(
        "app.core.authorization.authorized_doc_ids",
        lambda *args, **kwargs: [1],
    )
    fields, provenance = _party_fields(
        "广东省深圳市南山区科技园1号",
        "广东省广州市天河区体育路2号",
    )
    warnings = []

    cards = research_agent.retrieve_authorities(
        "private_lending",
        warnings,
        fields=fields,
        provenance=provenance,
    )

    assert {item["chunk_id"] for item in cards} == {"national", "guangdong"}
    assert next(
        item for item in cards if item["chunk_id"] == "guangdong"
    )["matched_regions"] == ["广东"]
    assert any(query.startswith("广东 ") for query in queries)
    assert any("北京市高级人民法院" in warning for warning in warnings)
