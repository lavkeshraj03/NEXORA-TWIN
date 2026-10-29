from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Investigation(Base):
    __tablename__ = "analyst_investigations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    captured_role: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="running")
    request_id: Mapped[str] = mapped_column(String(36))
    implementation_version: Mapped[str] = mapped_column(String(24), default="1")
    chat_model: Mapped[str] = mapped_column(String(200))
    parameters: Mapped[dict] = mapped_column(JSONB)
    inputs: Mapped[dict] = mapped_column(JSONB)
    input_hash: Mapped[str] = mapped_column(String(64))
    plan: Mapped[dict] = mapped_column(JSONB, default=dict)
    executions: Mapped[list] = mapped_column(JSONB, default=list)
    response: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','partial','failed')", name="analyst_status_valid"),
        CheckConstraint("length(input_hash) = 64", name="analyst_input_hash_valid"),
        Index("analyst_tenant_user_created", "business_id", "user_id", "created_at"),
    )
