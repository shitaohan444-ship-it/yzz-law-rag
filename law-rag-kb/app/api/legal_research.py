from __future__ import annotations

from datetime import date
import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, PositiveInt

from app.core.authorization import authorized_doc_ids
from app.core.security import Principal, require_service_principal
from app.rag import retrieve

router = APIRouter(prefix="/legal-research", tags=["legal-research"])


class LegalResearchRequest(BaseModel):
    issue: str = Field(min_length=1, max_length=2000)
    document_ids: list[PositiveInt] = Field(min_length=1, max_length=200)
    category_ids: list[PositiveInt] | None = Field(None, max_length=100)
    knowledge_types: list[str] | None = Field(None, max_length=20)
    case_id_scope: PositiveInt | None = None
    effective_on: date | None = None
    effectivity_status: str = Field(default="active", max_length=20)
    cause_code: str | None = Field(None, max_length=80)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.3, ge=0, le=1)


class AuthorityCard(BaseModel):
    legal_name: str
    article_number: str | None
    verified_text: str
    effective_status: str
    effective_on: date | None
    document_id: int
    chunk_id: str
    content_hash: str
    retrieval_score: float
    applicable_issue: str
    citation_section: str = "document.legal_basis"


class LegalResearchResponse(BaseModel):
    issue: str
    cards: list[AuthorityCard]


@router.post("/search", response_model=LegalResearchResponse)
def search_legal_authorities(
    req: LegalResearchRequest,
    principal: Annotated[Principal, Depends(require_service_principal)],
) -> LegalResearchResponse:
    allowed = authorized_doc_ids(
        principal,
        list(req.document_ids),
        case_id_scope=req.case_id_scope,
        category_ids=list(req.category_ids) if req.category_ids else None,
        knowledge_types=req.knowledge_types,
        effective_on=req.effective_on,
        effectivity_status=req.effectivity_status,
        cause_code=req.cause_code,
    )
    hits = retrieve.search(
        req.issue,
        doc_ids=allowed,
        top_k=req.top_k,
        min_score=req.min_score,
    )
    return LegalResearchResponse(
        issue=req.issue,
        cards=[
            AuthorityCard(
                legal_name=hit.doc_title or hit.source,
                article_number=hit.article_no,
                verified_text=hit.text,
                effective_status=req.effectivity_status,
                effective_on=req.effective_on,
                document_id=hit.doc_id,
                chunk_id=hit.chunk_id,
                content_hash=hashlib.sha256(hit.text.encode("utf-8")).hexdigest(),
                retrieval_score=hit.score,
                applicable_issue=req.issue,
            )
            for hit in hits
        ],
    )
