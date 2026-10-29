import time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select

from app.documents.models import Document, DocumentChunk, DocumentVersion, RagConversation
from app.documents.provider import ProviderError, get_provider

INSUFFICIENT = "The available documents do not establish the answer."


def visible_documents(business_id, role):
    conditions = [Document.business_id == business_id]
    if role not in {"owner", "administrator"}:
        conditions.append(Document.visibility == "team")
    return conditions


def retrieve(db, business_id, role, question, document_ids=None, provider=None):
    provider = provider or get_provider()
    if not provider.embeddings_configured:
        raise ProviderError("Configure the server-side embedding provider and index documents before searching")
    vectors, usage = provider.embed_query(question)
    vector = vectors[0]
    conditions = visible_documents(business_id, role) + [
        DocumentVersion.business_id == business_id,
        DocumentChunk.business_id == business_id,
        DocumentVersion.status == "ready",
        DocumentVersion.version == Document.active_version,
        DocumentVersion.embedding_identity == provider.identity,
        DocumentVersion.embedding_dimensions == len(vector),
        DocumentChunk.embedding.is_not(None),
    ]
    if document_ids:
        conditions.append(Document.id.in_(document_ids))
    base = select(DocumentChunk, DocumentVersion, Document).join(DocumentVersion, (DocumentChunk.version_id == DocumentVersion.id) & (DocumentChunk.business_id == DocumentVersion.business_id)).join(Document, (DocumentVersion.document_id == Document.id) & (DocumentVersion.business_id == Document.business_id)).where(*conditions)
    distance = DocumentChunk.embedding.cosine_distance(vector)
    semantic = db.execute(base.add_columns(distance.label("distance")).where(distance < 0.65).order_by(distance, DocumentChunk.id).limit(20)).all()
    lexical_query = func.plainto_tsquery("english", question)
    search_vector = func.to_tsvector("english", DocumentChunk.content)
    lexical = db.execute(base.where(search_vector.op("@@")(lexical_query)).order_by(func.ts_rank_cd(search_vector, lexical_query).desc(), DocumentChunk.id).limit(20)).all()
    scores, rows = {}, {}
    for ranking in [semantic, lexical]:
        for rank, row in enumerate(ranking, 1):
            chunk, version, document = row[:3]
            scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (60 + rank)
            rows[chunk.id] = (chunk, version, document)
    results, seen = [], set()
    for chunk_id in sorted(scores, key=lambda key: (-scores[key], str(key))):
        chunk, version, document = rows[chunk_id]
        normalized = " ".join(chunk.content.split())
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append({"chunk_id": str(chunk.id), "document_id": str(document.id), "title": document.title, "version": version.version, "page": chunk.page, "section": chunk.section, "kind": chunk.kind, "excerpt": chunk.content, "relevance": round(scores[chunk.id], 6)})
        if len(results) == 5:
            break
    return results, usage


def validate_citations(answer, sources):
    if answer["insufficient"]:
        return INSUFFICIENT, []
    lookup = {source["chunk_id"]: source for source in sources}
    citations, seen = [], set()
    if not 1 <= len(answer["citations"]) <= 5:
        raise ProviderError("AI answer lacked valid supporting citations")
    for item in answer["citations"]:
        if not isinstance(item, dict):
            raise ProviderError("AI answer contained an invalid citation")
        source = lookup.get(item.get("chunk_id"))
        quote = item.get("quote")
        if source is None or not isinstance(quote, str) or not 10 <= len(quote) <= 1200 or quote not in source["excerpt"]:
            raise ProviderError("AI answer cited evidence that was not retrieved; no answer was saved")
        if source["chunk_id"] not in seen:
            citations.append(source | {"excerpt": quote})
            seen.add(source["chunk_id"])
    return answer["answer"], citations


def ask(db, business_id, role, user_id, question, document_ids=None, conversation_id=None):
    started = time.perf_counter()
    conversation = None
    previous = []
    if conversation_id:
        conversation = db.scalar(select(RagConversation).where(RagConversation.id == conversation_id, RagConversation.business_id == business_id, RagConversation.user_id == user_id).with_for_update())
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        if len(conversation.turns) >= 20:
            raise HTTPException(422, "Start a new conversation after 20 questions")
        previous = [turn["question"] for turn in conversation.turns[-3:]]
    provider = get_provider()
    if not provider.chat_configured:
        raise ProviderError("Configure the server-side chat provider to enable grounded answers")
    # Prior questions are context only; prior answers are never reused as evidence.
    retrieval_query = " ".join(previous[-1:] + [question])[-2000:]
    sources, usage = retrieve(db, business_id, role, retrieval_query, document_ids)
    if sources:
        generated, chat_usage = provider.answer(question, sources, previous)
        answer, citations = validate_citations(generated, sources)
        usage = usage | {"chat": chat_usage}
    else:
        answer, citations = INSUFFICIENT, []
    if conversation is None:
        conversation = RagConversation(business_id=business_id, user_id=user_id, turns=[])
        db.add(conversation)
    result = {"question": question, "answer": answer, "citations": citations, "insufficient": not bool(citations), "relevance_definition": "Reciprocal-rank fusion score, not a confidence probability", "limitations": ["Generated claims require review against the cited excerpts; citation validation does not prove every claim.", "Only the current indexed document versions visible to your role are searched."], "usage": usage, "estimated_cost": None, "latency_ms": round((time.perf_counter() - started) * 1000)}
    conversation.turns = conversation.turns + [result]
    db.flush()
    result = result | {"conversation_id": str(conversation.id)}
    return result
