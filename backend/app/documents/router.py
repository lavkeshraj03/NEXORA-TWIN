from pathlib import PurePath
import time
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.businesses import access
from app.core.security import current_user, rate_limit
from app.core.config import get_settings
from app.data.imports import MAX_BYTES
from app.data.service import json_ready
from app.db.session import get_session
from app.documents.extraction import validate_upload
from app.documents.models import Document, DocumentChunk, DocumentVersion, RagEvaluation
from app.documents.pipeline import content_hash, enqueue
from app.documents.provider import ProviderError, get_provider
from app.documents.rag import ask, retrieve, visible_documents
from app.models import AuditLog, User
from app.schemas import Input

router = APIRouter(prefix="/businesses/{business_id}", tags=["Document intelligence"])


def version_out(version):
    return json_ready({name: getattr(version, name) for name in ("id", "document_id", "version", "filename", "status", "error", "chunk_count", "embedding_model", "embedding_dimensions", "usage", "created_at", "updated_at")})


def owned_document(db, business_id, document_id, role):
    document = db.scalar(select(Document).where(*visible_documents(business_id, role), Document.id == document_id))
    if document is None:
        raise HTTPException(404, "Document not found")
    return document


@router.get("/documents")
def list_documents(business_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_session)):
    _, membership = access(db, user, business_id, "documents:read")
    documents = db.scalars(select(Document).where(*visible_documents(business_id, membership.role)).order_by(Document.created_at.desc(), Document.id).limit(limit).offset(offset)).all()
    # Fetch at most 20 * 5 versions in one tenant-scoped query, not one per document.
    grouped = {document.id: [] for document in documents}
    if grouped:
        versions = db.scalars(select(DocumentVersion).where(DocumentVersion.business_id == business_id, DocumentVersion.document_id.in_(grouped)).order_by(DocumentVersion.version.desc())).all()
        for version in versions:
            grouped[version.document_id].append(version)
    output = []
    for document in documents:
        versions = grouped[document.id]
        output.append({"id": str(document.id), "title": document.title, "visibility": document.visibility, "active_version": document.active_version, "versions": [version_out(version) for version in versions]})
    return output


@router.post("/documents", status_code=202)
async def upload_document(business_id: UUID, request: Request, filename: str = Query(min_length=1, max_length=200), title: str = Query(min_length=1, max_length=160), visibility: Literal["team", "administrators"] = "team", document_id: UUID | None = None, user: User = Depends(current_user), db: Session = Depends(get_session)):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, "Document exceeds 2 MiB")
        raw.extend(chunk)

    def store():
        access(db, user, business_id, "documents:write", lock=True)
        rate_limit(f"document-upload:{business_id}:{user.id}", 30, 3600)
        try:
            validate_upload(filename, bytes(raw))
        except ValueError as error:
            raise HTTPException(422, str(error))
        if document_id:
            document = owned_document(db, business_id, document_id, "owner")
            versions = db.scalars(select(DocumentVersion).where(DocumentVersion.business_id == business_id, DocumentVersion.document_id == document.id).order_by(DocumentVersion.version.desc())).all()
            digest = content_hash(bytes(raw))
            duplicate = next((version for version in versions if version.content_hash == digest), None)
            if duplicate:
                return version_out(duplicate)
            if len(versions) >= 5:
                raise HTTPException(422, "A document supports at most five versions")
            number = versions[0].version + 1
        else:
            if db.scalar(select(func.count()).select_from(Document).where(Document.business_id == business_id)) >= 20:
                raise HTTPException(422, "This release supports at most 20 documents per business")
            document = Document(business_id=business_id, title=title, visibility=visibility)
            db.add(document)
            db.flush()
            number, digest = 1, content_hash(bytes(raw))
        version = DocumentVersion(business_id=business_id, document_id=document.id, version=number, filename=PurePath(filename).name, content_hash=digest, raw=bytes(raw), status="queued")
        db.add(version)
        db.add(AuditLog(business_id=business_id, user_id=user.id, event="document.uploaded", target_id=str(document.id)))
        db.commit()
        queue_version(db, version)
        return version_out(version)
    return await run_in_threadpool(store)


def queue_version(db, version):
    try:
        enqueue(version.id)
    except Exception:
        version.status = "failed"
        version.error = "Ingestion queue is unavailable. Retry after Redis/worker recovery."
        db.commit()


@router.post("/documents/{document_id}/versions/{version_id}/reindex", status_code=202)
def reindex(business_id: UUID, document_id: UUID, version_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "documents:write", lock=True)
    owned_document(db, business_id, document_id, "owner")
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id, DocumentVersion.business_id == business_id, DocumentVersion.document_id == document_id))
    if version is None:
        raise HTTPException(404, "Document version not found")
    if version.status in {"queued", "extracting", "indexing"} and version.updated_at > datetime.now(timezone.utc) - timedelta(minutes=5):
        raise HTTPException(409, "This version is already processing")
    rate_limit(f"document-reindex:{business_id}:{user.id}", 30, 3600)
    version.status, version.error = "queued", None
    db.add(AuditLog(business_id=business_id, user_id=user.id, event="document.reindex_requested", target_id=str(document_id)))
    db.commit()
    queue_version(db, version)
    return version_out(version)


@router.get("/documents/{document_id}/versions/{version_id}/chunks")
def preview_chunks(business_id: UUID, document_id: UUID, version_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(get_session)):
    _, membership = access(db, user, business_id, "documents:read")
    owned_document(db, business_id, document_id, membership.role)
    version = db.scalar(select(DocumentVersion.id).where(DocumentVersion.business_id == business_id, DocumentVersion.document_id == document_id, DocumentVersion.id == version_id))
    if version is None:
        raise HTTPException(404, "Document version not found")
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.business_id == business_id, DocumentChunk.version_id == version_id).order_by(DocumentChunk.ordinal).limit(limit).offset(offset)).all()
    return [{"id": str(chunk.id), "ordinal": chunk.ordinal, "content": chunk.content, "page": chunk.page, "section": chunk.section, "kind": chunk.kind} for chunk in chunks]


@router.get("/rag/status")
def provider_status(business_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_session)):
    access(db, user, business_id, "documents:read")
    provider = get_provider()
    evaluation = db.scalar(select(RagEvaluation).where(RagEvaluation.business_id == business_id).order_by(RagEvaluation.created_at.desc()).limit(1))
    return {"embeddings_configured": provider.embeddings_configured, "chat_configured": provider.chat_configured, "provider_health": provider.health_status(), "evaluation": json_ready(evaluation.metrics) if evaluation else None, "ocr": "Configured" if get_settings().ocr_url else "Not configured", "malware_scanner": "Signature/format checks only; no antivirus service"}


class QuestionInput(Input):
    question: str = Field(min_length=3, max_length=1500)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    conversation_id: UUID | None = None


class EvaluationCase(Input):
    question: str = Field(min_length=3, max_length=1000)
    expected_document_ids: list[UUID] = Field(min_length=1, max_length=5)
    expected_answer: str = Field(min_length=1, max_length=500)


class EvaluationInput(Input):
    cases: list[EvaluationCase] = Field(min_length=1, max_length=10)


@router.post("/rag/evaluate")
def evaluate(business_id: UUID, data: EvaluationInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    _, membership = access(db, user, business_id, "documents:write", lock=True)
    rate_limit(f"rag-evaluate:{business_id}:{user.id}", 5, 3600)
    started = time.perf_counter()
    recalls, precisions, ranks, reference_matches, citation_count = [], [], [], [], 0
    try:
        for case in data.cases:
            for document_id in case.expected_document_ids:
                owned_document(db, business_id, document_id, membership.role)
            result = ask(db, business_id, membership.role, user.id, case.question)
            sources, _ = retrieve(db, business_id, membership.role, case.question)
            expected = {str(value) for value in case.expected_document_ids}
            ranked = list(dict.fromkeys(source["document_id"] for source in sources))
            relevant = expected.intersection(ranked)
            recalls.append(len(relevant) / len(expected))
            precisions.append(len(relevant) / len(ranked) if ranked else 0)
            ranks.append(next((1 / rank for rank, value in enumerate(ranked, 1) if value in expected), 0))
            reference_matches.append(int(case.expected_answer.casefold() in result["answer"].casefold()))
            citation_count += len(result["citations"])
        mean = lambda values: round(sum(values) / len(values), 4)
        metrics = {"cases": len(data.cases), "document_recall_at_5_chunks": mean(recalls), "document_precision_at_5_chunks": mean(precisions), "mean_reciprocal_rank": mean(ranks), "validated_citations": citation_count, "citation_integrity": 1.0 if citation_count else None, "answer_reference_substring_match": mean(reference_matches), "answer_faithfulness": "Not evaluated — requires human review", "answer_relevance": "Not evaluated — requires human review", "latency_ms": round((time.perf_counter() - started) * 1000), "embedding_model": get_provider().embedding_model, "chat_model": get_provider().chat_model, "scope": "Curated cases submitted by the operator; not a general quality guarantee"}
        db.add(RagEvaluation(business_id=business_id, user_id=user.id, metrics=metrics))
        db.add(AuditLog(business_id=business_id, user_id=user.id, event="rag.evaluation_completed"))
        db.commit()
        return metrics
    except ProviderError as error:
        raise HTTPException(503, str(error))


@router.post("/rag/search")
def search(business_id: UUID, data: QuestionInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    _, membership = access(db, user, business_id, "documents:read", lock=True)
    rate_limit(f"rag-search:{business_id}:{user.id}", 60, 3600)
    try:
        sources, usage = retrieve(db, business_id, membership.role, data.question, data.document_ids)
        return {"sources": sources, "usage": usage, "definition": "Hybrid vector/English full-text reciprocal-rank fusion; scores are not probabilities"}
    except ProviderError as error:
        raise HTTPException(503, str(error))


@router.post("/rag/ask")
def question(business_id: UUID, data: QuestionInput, user: User = Depends(current_user), db: Session = Depends(get_session)):
    _, membership = access(db, user, business_id, "documents:read", lock=True)
    rate_limit(f"rag-ask:{business_id}:{user.id}", 30, 3600)
    try:
        result = ask(db, business_id, membership.role, user.id, data.question, data.document_ids, data.conversation_id)
        db.add(AuditLog(business_id=business_id, user_id=user.id, event="rag.question_answered"))
        db.commit()
        return result
    except ProviderError as error:
        raise HTTPException(503, str(error))
