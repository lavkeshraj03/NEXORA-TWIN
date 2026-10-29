from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    business_id: Mapped[UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    baseline_snapshot_id: Mapped[UUID] = mapped_column()
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(100))
    implementation_version: Mapped[str] = mapped_column(String(24), default="1")
    baseline_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "baseline_snapshot_id"], ["twin_snapshots.business_id", "twin_snapshots.id"], name="fk_simulation_tenant_snapshot", ondelete="CASCADE"),
        Index("simulation_runs_tenant_created", "business_id", "created_at"),
    )
