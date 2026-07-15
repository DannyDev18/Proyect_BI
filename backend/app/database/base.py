# backend/app/database/base.py
# Importa todos los modelos para que SQLAlchemy registre su metadata.
# Necesario para Base.metadata.create_all(bind=engine) en el lifespan de main.py.
from app.database.session import Base  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.goal import Goal  # noqa: F401
from app.models.recommendation_event import RecommendationEvent  # noqa: F401
from app.models.gestion_cartera_evento import GestionCarteraEvento  # noqa: F401
from app.models.commission_config import (  # noqa: F401
    ComisionMatrizCategoria, ComisionFactorCredito, ComisionConfigVendedor, ComisionLiquidacion,
)
from app.models.notification import Notification  # noqa: F401
