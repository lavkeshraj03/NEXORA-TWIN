from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    visibility: Mapped[str] = mapped_column(String(24), default="team")
    active_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("business_id", "id", name="uq_document_tenant"), CheckConstraint("visibility IN ('team','administrators')", name="document_visibility_valid"))


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column()
    filename: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    raw: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error: Mapped[str | None] = mapped_column(String(300))
    chunk_count: Mapped[int] = mapped_column(default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_identity: Mapped[str | None] = mapped_column(String(64))
    embedding_dimensions: Mapped[int | None] = mapped_column()
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "document_id"], ["documents.business_id", "documents.id"], ondelete="CASCADE", name="fk_version_tenant_document"),
        UniqueConstraint("business_id", "document_id", "version", name="uq_document_version"),
        UniqueConstraint("business_id", "id", name="uq_version_tenant"),
        CheckConstraint("status IN ('queued','extracting','indexing','ready','awaiting_configuration','failed')", name="document_status_valid"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[UUID] = mapped_column()
    ordinal: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column()
    section: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    embedding: Mapped[list | None] = mapped_column(Vector())
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "version_id"], ["document_versions.business_id", "document_versions.id"], ondelete="CASCADE", name="fk_chunk_tenant_version"),
        UniqueConstraint("business_id", "version_id", "ordinal", name="uq_chunk_ordinal"),
        Index("chunks_tenant_version", "business_id", "version_id"),
    )


class RagConversation(Base):
    __tablename__ = "rag_conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    turns: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagEvaluation(Base):
    __tablename__ = "rag_evaluations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    metrics: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
