# backend/app/database/base.py
# Importa todos los modelos para que SQLAlchemy registre su metadata. Necesario para
# que Alembic (backend/alembic/, docs/features/plan_migraciones_esquema_public.md) vea
# los 13 modelos al comparar Base.metadata -- única fuente de verdad del esquema public.
from app.database.session import Base  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.usuario_almacen import UsuarioAlmacen  # noqa: F401
from app.models.goal import Goal  # noqa: F401
from app.models.meta_config import MetaConfigParametro  # noqa: F401
from app.models.meta_config_modulo import MetaConfigModulo  # noqa: F401
from app.models.recommendation_event import RecommendationEvent  # noqa: F401
from app.models.gestion_cartera_evento import GestionCarteraEvento  # noqa: F401
from app.models.commission_config import (  # noqa: F401
    ComisionMatrizCategoria, ComisionFactorCredito, ComisionConfigVendedor, ComisionLiquidacion,
    ComisionConfigAuditoria, ComisionTramoCobranza, ComisionFormula, ComisionFormulaComponente,
    ComisionTramoCumplimiento,
)
from app.models.notification import Notification  # noqa: F401
from app.models.login_intento_fallido import LoginIntentoFallido  # noqa: F401
from app.models.ml_model_run import MLModelRun  # noqa: F401
from app.models.token_revocado import TokenRevocado  # noqa: F401
from app.models.replenishment_config import ReabastecimientoPolitica, ReabastecimientoLeadTime  # noqa: F401
from app.models.replenishment_proposal import PropuestaCompra, PropuestaCompraLinea  # noqa: F401
