import hashlib
from uuid import UUID

from redis import Redis
from rq import Queue
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.documents.extraction import chunk_sections, extract
from app.documents.models import Document, DocumentChunk, DocumentVersion
from app.documents.provider import ProviderError, get_provider
from app.models import Business


def enqueue(version_id: UUID):
    with Redis.from_url(get_settings().redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2) as connection:
        Queue("nexora", connection=connection).enqueue(process_version, str(version_id), job_timeout=180, result_ttl=3600, failure_ttl=86400)


def process_version(version_id: str):
    """Version rows are the durable ingestion status, independent of RQ result expiry."""
    version_id = UUID(version_id)
    with Session(get_engine(), expire_on_commit=False) as db:
        version = db.get(DocumentVersion, version_id)
        if version is None:
            return
        # Serialize processing/re-index and membership changes for this business.
        db.scalar(select(Business).where(Business.id == version.business_id).with_for_update())
        db.refresh(version)
        if version.status not in {"queued", "failed", "awaiting_configuration"}:
            return
        try:
            version.status, version.error = "extracting", None
            db.flush()
            settings = get_settings()
            pieces = chunk_sections(extract(version.filename, version.raw), settings.document_chunk_size, settings.document_chunk_overlap)
            db.execute(delete(DocumentChunk).where(DocumentChunk.business_id == version.business_id, DocumentChunk.version_id == version.id))
            chunks = [DocumentChunk(business_id=version.business_id, version_id=version.id, ordinal=index, content=piece.text, page=piece.page, section=piece.heading, kind=piece.kind) for index, piece in enumerate(pieces)]
            db.add_all(chunks)
            version.chunk_count = len(chunks)
            provider = get_provider()
            if not provider.embeddings_configured:
                version.status = "awaiting_configuration"
                version.error = "Text extracted. Configure the server-side embedding provider, then re-index."
            else:
                version.status = "indexing"
                vectors, usage = provider.embed([chunk.content for chunk in chunks])
                for chunk, vector in zip(chunks, vectors, strict=True):
                    chunk.embedding = vector
                version.embedding_model = provider.embedding_model
                version.embedding_identity = provider.identity
                version.embedding_dimensions = len(vectors[0])
                version.usage = usage
                version.status = "ready"
                document = db.get(Document, version.document_id)
                if version.version >= document.active_version:
                    document.active_version = version.version
                # Old versions remain auditable; retrieval selects only the active version.
            db.commit()
        except Exception as error:
            db.rollback()
            version = db.get(DocumentVersion, version_id)
            version.status = "failed"
            version.error = str(error)[:300] if isinstance(error, (ValueError, ProviderError)) else "Document processing failed; check format and retry"
            db.commit()


def content_hash(raw):
    return hashlib.sha256(raw).hexdigest()
