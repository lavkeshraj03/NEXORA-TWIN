from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import DateTime,ForeignKey,Index,String,func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.db.session import Base


class GeneratedReport(Base):
    __tablename__="generated_reports"
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    business_id:Mapped[UUID]=mapped_column(ForeignKey("businesses.id",ondelete="CASCADE"),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"))
    captured_role:Mapped[str]=mapped_column(String(16))
    name:Mapped[str]=mapped_column(String(100))
    kind:Mapped[str]=mapped_column(String(24))
    implementation_version:Mapped[str]=mapped_column(String(24),default="1")
    payload:Mapped[dict]=mapped_column(JSONB)
    content_hash:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(Index("reports_tenant_user_created","business_id","user_id","created_at"),)
