# backend/app/repositories/meta_config_modulo_repository.py
"""Acceso a datos de la configuración modular del motor de metas v3 (docs/features/
plan_motor_metas_v3_y_comisiones_unificadas.md §9, Fase 6). Ver docstring de
`app/models/meta_config_modulo.py` para el porqué de no tener vigencia histórica."""
from sqlalchemy.orm import Session

from app.models.commission_config import ComisionConfigAuditoria
from app.models.meta_config_modulo import MetaConfigModulo
from app.models.user import User


class MetaConfigModuloRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[MetaConfigModulo]:
        return self.db.query(MetaConfigModulo).order_by(MetaConfigModulo.orden).all()

    def get_by_etapa(self, etapa: str) -> MetaConfigModulo | None:
        return self.db.query(MetaConfigModulo).filter(MetaConfigModulo.etapa == etapa).first()

    def update_modulo(
        self, etapa: str, metodo: str | None, activo: bool, parametros: dict, usuario_id: int | None,
    ) -> MetaConfigModulo:
        modulo = self.get_by_etapa(etapa)
        if modulo is None:
            raise ValueError(f"Etapa de configuración de metas desconocida: {etapa}")
        anterior = {"metodo": modulo.metodo, "activo": modulo.activo, "parametros": modulo.parametros}
        modulo.metodo = metodo
        modulo.activo = activo
        modulo.parametros = parametros
        modulo.actualizado_por = usuario_id
        self.db.add(ComisionConfigAuditoria(
            usuario_id=usuario_id, tabla="metas_config_modulos", accion="UPDATE",
            detalle_json={
                "etapa": etapa, "anterior": anterior,
                "nuevo": {"metodo": metodo, "activo": activo, "parametros": parametros},
            },
        ))
        self.db.commit()
        self.db.refresh(modulo)
        return modulo

    def get_auditoria(self, limit: int = 100) -> list[tuple[ComisionConfigAuditoria, str | None]]:
        rows = (
            self.db.query(ComisionConfigAuditoria, User.nombre)
            .outerjoin(User, ComisionConfigAuditoria.usuario_id == User.id)
            .filter(ComisionConfigAuditoria.tabla == "metas_config_modulos")
            .order_by(ComisionConfigAuditoria.fecha_creacion.desc())
            .limit(limit)
            .all()
        )
        return [(entrada, nombre) for entrada, nombre in rows]
