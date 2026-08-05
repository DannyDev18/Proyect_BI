# backend/app/repositories/replenishment_proposal_repository.py
"""Acceso a datos de propuestas de compra persistidas (F9, docs/features/plan_
reabastecimiento_inteligente.md §6.3/§8). Volumen bajo esperado (una propuesta por
sesión de planificación de compras, no una por request) -- se lista completa y se
pagina en memoria, mismo patrón que el resto del módulo."""
from sqlalchemy.orm import Session, joinedload

from app.models.replenishment_proposal import PropuestaCompra, PropuestaCompraLinea


class ReplenishmentProposalRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(
        self, usuario_id: int | None, filtros_origen: dict, horizonte_dias: float,
        lineas: list[dict],
    ) -> PropuestaCompra:
        total = round(sum(line["costo_total"] for line in lineas), 2)
        propuesta = PropuestaCompra(
            estado="borrador", usuario_id=usuario_id, filtros_origen=filtros_origen,
            horizonte_dias=horizonte_dias, total=total,
        )
        propuesta.lineas = [
            PropuestaCompraLinea(
                codart=line["codart"], nombre=line["nombre"], cantidad=line["cantidad"],
                costo_unitario=line["costo_unitario"], costo_total=line["costo_total"],
                justificacion=line["justificacion"],
            )
            for line in lineas
        ]
        self.db.add(propuesta)
        self.db.commit()
        self.db.refresh(propuesta)
        return propuesta

    def listar(self) -> list[PropuestaCompra]:
        return (
            self.db.query(PropuestaCompra)
            .order_by(PropuestaCompra.creado_en.desc())
            .all()
        )

    def get(self, propuesta_id: int) -> PropuestaCompra | None:
        return (
            self.db.query(PropuestaCompra)
            .options(joinedload(PropuestaCompra.lineas))
            .filter(PropuestaCompra.id == propuesta_id)
            .first()
        )

    def actualizar_estado(self, propuesta_id: int, estado: str) -> PropuestaCompra | None:
        propuesta = self.get(propuesta_id)
        if propuesta is None:
            return None
        propuesta.estado = estado
        self.db.commit()
        self.db.refresh(propuesta)
        return propuesta
