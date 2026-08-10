from __future__ import annotations

from typing import Any, TypedDict


class LegalDraftingState(TypedDict, total=False):
    run_id: str
    thread_id: str
    snapshot: dict[str, Any]
    schema_path: str
    template_source_path: str
    normalized_template_path: str
    material_texts: list[dict[str, Any]]
    pre_extracted_elements: dict[str, Any]
    pre_extracted_provenance: dict[str, list[dict[str, Any]]]
    extraction_warnings: list[str]
    element_candidates: dict[str, list[dict[str, Any]]]
    resolved_elements: dict[str, Any]
    provenance: dict[str, list[dict[str, Any]]]
    missing_elements: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    legal_issues: list[str]
    authority_cards: list[dict[str, Any]]
    writing_plan: str
    drafted_claims: str
    drafted_facts: str
    drafted_legal_basis: str
    drafted_evidence: str
    document_sections: dict[str, str]
    review_issues: list[dict[str, Any]]
    review_round: int
    rewrite_count_by_section: dict[str, int]
    structured_document: dict[str, Any]
    docx_path: str
    render_report: dict[str, Any]
    status: str
    current_node: str
    progress: int
    warnings: list[str]
