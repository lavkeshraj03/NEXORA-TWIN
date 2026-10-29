from alembic import context
from app.core.config import get_settings
from app.db.session import Base, get_engine
from app import models  # Register mapped tables for migration comparison.
from app.data import models as data_models
from app.documents import models as document_models
from app.ml import models as ml_models
from app.twin import models as twin_models
from app.simulation import models as simulation_models
from app.analyst import models as analyst_models
from app.graph import models as graph_models
from app.reports import models as report_models

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=get_settings().database_url.get_secret_value(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
