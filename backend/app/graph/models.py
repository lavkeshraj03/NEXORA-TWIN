from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import DateTime,ForeignKey,ForeignKeyConstraint,Index,String,UniqueConstraint,func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.db.session import Base


class GraphBuild(Base):
    __tablename__="graph_builds"
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    business_id:Mapped[UUID]=mapped_column(ForeignKey("businesses.id",ondelete="CASCADE"),index=True)
    created_by:Mapped[UUID|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"))
    implementation_version:Mapped[str]=mapped_column(String(24),default="1")
    source_hash:Mapped[str]=mapped_column(String(64))
    manifest:Mapped[dict]=mapped_column(JSONB)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint("business_id","id",name="uq_graph_build_tenant"),)


class KnowledgeNode(Base):
    __tablename__="knowledge_nodes"
    id:Mapped[UUID]=mapped_column(primary_key=True)
    business_id:Mapped[UUID]=mapped_column(ForeignKey("businesses.id",ondelete="CASCADE"),index=True)
    build_id:Mapped[UUID]=mapped_column()
    kind:Mapped[str]=mapped_column(String(24))
    source_key:Mapped[str]=mapped_column(String(100))
    label:Mapped[str]=mapped_column(String(260))
    source:Mapped[dict]=mapped_column(JSONB)
    document_id:Mapped[UUID|None]=mapped_column()
    visibility:Mapped[str]=mapped_column(String(24),default="team")
    __table_args__=(
        ForeignKeyConstraint(["business_id","build_id"],["graph_builds.business_id","graph_builds.id"],ondelete="CASCADE",name="fk_node_tenant_build"),
        UniqueConstraint("business_id","build_id","id",name="uq_graph_node_tenant"),
        UniqueConstraint("build_id","source_key",name="uq_graph_node_source"),
        Index("graph_nodes_tenant_kind","business_id","build_id","kind"),
    )


class KnowledgeEdge(Base):
    __tablename__="knowledge_edges"
    id:Mapped[UUID]=mapped_column(primary_key=True)
    business_id:Mapped[UUID]=mapped_column(ForeignKey("businesses.id",ondelete="CASCADE"),index=True)
    build_id:Mapped[UUID]=mapped_column()
    source_id:Mapped[UUID]=mapped_column()
    target_id:Mapped[UUID]=mapped_column()
    relationship:Mapped[str]=mapped_column(String(40))
    provenance:Mapped[dict]=mapped_column(JSONB)
    __table_args__=(
        ForeignKeyConstraint(["business_id","build_id"],["graph_builds.business_id","graph_builds.id"],ondelete="CASCADE",name="fk_edge_tenant_build"),
        ForeignKeyConstraint(["business_id","build_id","source_id"],["knowledge_nodes.business_id","knowledge_nodes.build_id","knowledge_nodes.id"],ondelete="CASCADE",name="fk_edge_tenant_source"),
        ForeignKeyConstraint(["business_id","build_id","target_id"],["knowledge_nodes.business_id","knowledge_nodes.build_id","knowledge_nodes.id"],ondelete="CASCADE",name="fk_edge_tenant_target"),
        Index("graph_edges_tenant_build","business_id","build_id"),
    )
