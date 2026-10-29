from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    task: Mapped[str] = mapped_column(String(16))
    product_id: Mapped[UUID | None] = mapped_column()
    data_scope: Mapped[str] = mapped_column(String(8))
    algorithm: Mapped[str] = mapped_column(String(40))
    implementation_version: Mapped[str] = mapped_column(String(24), default="1")
    dataset_hash: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSONB)
    dataset: Mapped[dict] = mapped_column(JSONB)
    artifact: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "product_id"], ["products.business_id", "products.id"], name="fk_model_tenant_product"),
        CheckConstraint("task IN ('sales','demand','churn')", name="model_task_valid"),
        CheckConstraint("data_scope IN ('real','demo')", name="model_scope_valid"),
        Index("model_runs_tenant_created", "business_id", "created_at"),
        Index("uq_active_model", "business_id", "task", "data_scope", "product_id", unique=True, postgresql_where=active.is_(True), postgresql_nulls_not_distinct=True),
    )
