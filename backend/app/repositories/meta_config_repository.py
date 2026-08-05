# backend/app/repositories/meta_config_repository.py
"""Acceso a datos de la configuración editable del motor de metas v2
(docs/features/plan_motor_metas_configurable.md §5.5). Ver docstring de
`app/models/meta_config.py` para la diferencia deliberada con las tablas de vigencia de
Comisiones Variables (aquí no hace falta vigencia histórica)."""
from sqlalchemy.orm import Session

from app.models.commission_config import ComisionConfigAuditoria
from app.models.meta_config import MetaConfigParametro
from app.models.user import User


class MetaConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[MetaConfigParametro]:
        return self.db.query(MetaConfigParametro).order_by(MetaConfigParametro.clave).all()

    def get_valores(self) -> dict[str, float]:
        """Mapa `clave -> valor` listo para construir `MetaMotorParametros` -- si una
        clave no está configurada (entorno sin la migración semilla aplicada, o una
        clave nueva agregada después), el llamador cae al default de
        `MetaMotorParametros`, nunca a un `KeyError`."""
        return {p.clave: float(p.valor) for p in self.get_all()}

    def update_valor(self, clave: str, valor: float, usuario_id: int | None) -> MetaConfigParametro:
        parametro = self.db.query(MetaConfigParametro).filter(MetaConfigParametro.clave == clave).first()
        if parametro is None:
            raise ValueError(f"Parámetro de configuración de metas desconocido: {clave}")
        anterior = float(parametro.valor)
        parametro.valor = valor
        parametro.actualizado_por = usuario_id
        self.db.add(ComisionConfigAuditoria(
            usuario_id=usuario_id, tabla="metas_config_parametros", accion="UPDATE",
            detalle_json={"clave": clave, "valor_anterior": anterior, "valor_nuevo": valor},
        ))
        self.db.commit()
        self.db.refresh(parametro)
        return parametro

    def get_auditoria(self, limit: int = 100) -> list[tuple[ComisionConfigAuditoria, str | None]]:
        rows = (
            self.db.query(ComisionConfigAuditoria, User.nombre)
            .outerjoin(User, ComisionConfigAuditoria.usuario_id == User.id)
            .filter(ComisionConfigAuditoria.tabla == "metas_config_parametros")
            .order_by(ComisionConfigAuditoria.fecha_creacion.desc())
            .limit(limit)
            .all()
        )
        return [(entrada, nombre) for entrada, nombre in rows]
