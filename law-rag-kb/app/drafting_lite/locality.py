from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

_PROVINCES = {
    "北京":"北京市","天津":"天津市","河北":"河北省","山西":"山西省",
    "内蒙古":"内蒙古自治区","辽宁":"辽宁省","吉林":"吉林省",
    "黑龙江":"黑龙江省","上海":"上海市","江苏":"江苏省","浙江":"浙江省",
    "安徽":"安徽省","福建":"福建省","江西":"江西省","山东":"山东省",
    "河南":"河南省","湖北":"湖北省","湖南":"湖南省","广东":"广东省",
    "广西":"广西壮族自治区","海南":"海南省","重庆":"重庆市",
    "四川":"四川省","贵州":"贵州省","云南":"云南省","西藏":"西藏自治区",
    "陕西":"陕西省","甘肃":"甘肃省","青海":"青海省",
    "宁夏":"宁夏回族自治区","新疆":"新疆维吾尔自治区",
    "香港":"香港特别行政区","澳门":"澳门特别行政区","台湾":"台湾省",
}
_REGION_RE = re.compile(r"([\u4e00-\u9fff]{2,8}?)(?:市|自治州|地区|盟|县|区)")
_REGION_NOISE = {
    "城市","市区","地区","自治区","行政区","开发区","工业区","城区",
    "新区","矿区",
}
_LOCAL_MARKERS = (
    "地方性法规","地方政府规章","地方司法文件","地方规范性文件",
)
_NATIONAL_TITLES = (
    "中华人民共和国","最高人民法院","最高人民检察院","国务院",
    "全国人民代表大会",
)
_CONNECTION_FIELDS = (
    "jurisdiction","infringement_place","accident","subject.summary",
    "delivery.summary","registration.summary","labor.performance","injury_date",
)
_CONNECTION_TEXT = (
    "合同履行地","事故发生地","侵权行为地","侵权结果地","房屋所在地",
    "不动产所在地","工作地点","用人单位所在地","约定管辖","管辖法院",
)
_ADDRESS_SUFFIXES = (
    ".address",".current_address",".organization_address",
    ".organization_registration_address",
)


@dataclass(frozen=True)
class LocalityContext:
    party_regions: dict[str, frozenset[str]] = field(default_factory=dict)
    shared_party_regions: frozenset[str] = frozenset()
    case_connection_regions: frozenset[str] = frozenset()
    applicable_regions: frozenset[str] = frozenset()
    evidence_fields: tuple[str, ...] = ()

    def audit_dict(self) -> dict[str, Any]:
        return {
            "party_regions": {
                role: sorted(regions)
                for role, regions in self.party_regions.items()
            },
            "shared_party_regions": sorted(self.shared_party_regions),
            "case_connection_regions": sorted(self.case_connection_regions),
            "applicable_regions": sorted(self.applicable_regions),
            "evidence_fields": list(self.evidence_fields),
        }


def extract_regions(value: Any) -> set[str]:
    text = str(value or "")
    regions: set[str] = set()
    scrubbed = text
    for canonical, full_name in _PROVINCES.items():
        if full_name in text or canonical in text:
            regions.add(canonical)
            scrubbed = scrubbed.replace(full_name, " ").replace(canonical, " ")
    for match in _REGION_RE.finditer(scrubbed):
        name = match.group(1).strip()
        if name and name not in _REGION_NOISE:
            regions.add(name)
    return regions


def build_locality_context(
    fields: dict[str, Any] | None,
    provenance: dict[str, list[dict[str, Any]]] | None,
) -> LocalityContext:
    values, sources = fields or {}, provenance or {}
    party_regions: dict[str, set[str]] = {
        "plaintiff": set(), "defendant": set(),
    }
    party_record_regions: dict[str, list[set[str]]] = {
        "plaintiff": [], "defendant": [],
    }
    evidence_fields: set[str] = set()
    for field_id, value in values.items():
        if (
            not field_id.startswith("party.")
            or not field_id.endswith(_ADDRESS_SUFFIXES)
            or not sources.get(field_id)
        ):
            continue
        parts = field_id.split(".")
        if len(parts) < 3 or parts[1] not in party_regions:
            continue
        regions = extract_regions(value)
        if regions:
            party_regions[parts[1]].update(regions)
            evidence_fields.add(field_id)

    # 公共投影器只会把具有合格来源的多主体字段放入该记录。
    records = values.get("_party_records")
    if isinstance(records, dict):
        for role in ("plaintiff", "defendant"):
            for record in records.get(role) or []:
                if not isinstance(record, dict):
                    continue
                record_regions: set[str] = set()
                for suffix in (
                    "address","current_address","organization_address",
                    "organization_registration_address",
                ):
                    regions = extract_regions(record.get(suffix))
                    if regions:
                        record_regions.update(regions)
                        party_regions[role].update(regions)
                        evidence_fields.add(f"_party_records.{role}.{suffix}")
                if record_regions:
                    party_record_regions[role].append(record_regions)

    case_regions: set[str] = set()
    for field_id, value in values.items():
        if field_id.startswith("party.") or not sources.get(field_id):
            continue
        rendered = str(value or "")
        if not (
            any(marker in field_id for marker in _CONNECTION_FIELDS)
            or any(marker in rendered for marker in _CONNECTION_TEXT)
        ):
            continue
        regions = extract_regions(rendered)
        if regions:
            case_regions.update(regions)
            evidence_fields.add(field_id)

    for role in ("plaintiff", "defendant"):
        if not party_record_regions[role] and party_regions[role]:
            party_record_regions[role].append(set(party_regions[role]))
    all_party_regions = [
        *party_record_regions["plaintiff"],
        *party_record_regions["defendant"],
    ]
    shared = (
        set.intersection(*all_party_regions)
        if party_record_regions["plaintiff"]
        and party_record_regions["defendant"]
        and all_party_regions
        else set()
    )
    applicable = shared | case_regions
    return LocalityContext(
        party_regions={
            role: frozenset(regions)
            for role, regions in party_regions.items() if regions
        },
        shared_party_regions=frozenset(shared),
        case_connection_regions=frozenset(case_regions),
        applicable_regions=frozenset(applicable),
        evidence_fields=tuple(sorted(evidence_fields)),
    )


def _metadata_regions(value: Any) -> set[str]:
    items = value if isinstance(value, list) else (
        [] if value in (None, "") else [value]
    )
    result: set[str] = set()
    for item in items:
        extracted = extract_regions(item)
        result.update(extracted or {str(item).strip()})
    return {item for item in result if item}


def authority_locality(authority: Any) -> tuple[str, set[str]]:
    getter = authority.get if isinstance(authority, dict) else (
        lambda key, default=None: getattr(authority, key, default)
    )
    scope = str(getter("jurisdiction_scope", "") or "").strip().lower()
    explicit = _metadata_regions(getter("jurisdiction_regions", None))
    title = str(
        getter("legal_name", None) or getter("doc_title", None) or ""
    )
    source = str(getter("source", "") or "")
    path = getter("category_path", None)
    category = (
        " ".join(str(item) for item in path)
        if isinstance(path, list) else str(path or "")
    )
    national_title = title.startswith(_NATIONAL_TITLES)
    inferred = (
        set() if national_title
        else extract_regions(f"{title}\n{source}\n{category}")
    )
    regions = explicit or inferred
    local_marker = any(
        marker in category or marker in source for marker in _LOCAL_MARKERS
    )
    if scope == "national" or national_title:
        return "national", set()
    if scope == "local" or regions or local_marker:
        return "local", regions
    return "national", set()


def authority_applicable(
    authority: Any,
    context: LocalityContext,
) -> tuple[bool, dict[str, Any]]:
    scope, regions = authority_locality(authority)
    if scope == "national":
        return True, {
            "jurisdiction_scope": "national",
            "jurisdiction_regions": [],
            "locality_match": "national_authority",
            "locality_evidence_fields": [],
        }
    matched = regions & set(context.applicable_regions)
    if not regions:
        reason = "local_authority_region_unknown"
    elif not context.applicable_regions:
        reason = "case_locality_unverified"
    elif not matched:
        reason = "local_authority_region_mismatch"
    else:
        reason = "verified_locality_match"
    return bool(matched), {
        "jurisdiction_scope": "local",
        "jurisdiction_regions": sorted(regions),
        "locality_match": reason,
        "matched_regions": sorted(matched),
        "locality_evidence_fields": list(context.evidence_fields),
    }


def filter_authority_cards(
    cards: list[dict[str, Any]],
    fields: dict[str, Any] | None,
    provenance: dict[str, list[dict[str, Any]]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], LocalityContext]:
    context = build_locality_context(fields, provenance)
    accepted, rejected = [], []
    for card in cards:
        allowed, audit = authority_applicable(card, context)
        enriched = {**card, **audit}
        (accepted if allowed else rejected).append(enriched)
    return accepted, rejected, context
