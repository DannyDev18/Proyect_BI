# backend/app/repositories/replenishment_config_repository.py
"""Acceso a datos de la configuración editable del motor de Reabastecimiento
(docs/features/plan_reabastecimiento_inteligente.md §6.3). Sin bitácora compartida con
`comision_config_auditoria` en esta fase (su `CHECK` de tablas válidas es un catálogo
cerrado que no incluye estas dos tablas nuevas -- ampliarlo es una migración propia,
diferida; `actualizado_por`/`actualizado_en` en cada fila ya dan trazabilidad básica de
quién/cuándo, aunque no el valor anterior)."""
from sqlalchemy.orm import Session

from app.models.replenishment_config import ReabastecimientoLeadTime, ReabastecimientoPolitica


class ReplenishmentConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Política de nivel de servicio por clase ABC ─────────────────────────────────
    def get_politica(self) -> list[ReabastecimientoPolitica]:
        return self.db.query(ReabastecimientoPolitica).order_by(ReabastecimientoPolitica.clase_abc).all()

    def get_niveles_servicio(self) -> dict[str, float]:
        """`{clase_abc: nivel_servicio}` -- forma que consume el motor puro directamente."""
        return {p.clase_abc: float(p.nivel_servicio) for p in self.get_politica()}

    def update_politica(self, clase_abc: str, nivel_servicio: float, usuario_id: int | None) -> ReabastecimientoPolitica:
        fila = self.db.query(ReabastecimientoPolitica).filter(ReabastecimientoPolitica.clase_abc == clase_abc).first()
        if fila is None:
            raise ValueError(f"Clase ABC desconocida: {clase_abc}")
        fila.nivel_servicio = nivel_servicio
        fila.actualizado_por = usuario_id
        self.db.commit()
        self.db.refresh(fila)
        return fila

    # ── Lead time por producto/categoría/proveedor ──────────────────────────────────
    def get_lead_times(self) -> list[ReabastecimientoLeadTime]:
        return self.db.query(ReabastecimientoLeadTime).order_by(ReabastecimientoLeadTime.id).all()

    def get_lead_times_resolucion(self) -> dict[str, dict[str, float]]:
        """3 diccionarios (`producto`/`categoria`/`proveedor` -> días) para que el
        servicio resuelva cada fila del catálogo con `replenishment_engine.
        resolver_lead_time` sin una consulta por SKU."""
        filas = self.get_lead_times()
        resultado: dict[str, dict[str, float]] = {"producto": {}, "categoria": {}, "proveedor": {}}
        for f in filas:
            if f.producto:
                resultado["producto"][f.producto] = float(f.dias)
            elif f.categoria:
                resultado["categoria"][f.categoria] = float(f.dias)
            elif f.proveedor:
                resultado["proveedor"][f.proveedor] = float(f.dias)
        return resultado

    def upsert_lead_time(
        self, dias: float, usuario_id: int | None,
        producto: str | None = None, categoria: str | None = None, proveedor: str | None = None,
    ) -> ReabastecimientoLeadTime:
        query = self.db.query(ReabastecimientoLeadTime)
        if producto:
            query = query.filter(ReabastecimientoLeadTime.producto == producto)
        elif categoria:
            query = query.filter(ReabastecimientoLeadTime.categoria == categoria)
        elif proveedor:
            query = query.filter(ReabastecimientoLeadTime.proveedor == proveedor)
        else:
            raise ValueError("Debe especificarse exactamente uno de producto/categoria/proveedor.")
        fila = query.first()
        if fila is None:
            fila = ReabastecimientoLeadTime(producto=producto, categoria=categoria, proveedor=proveedor)
            self.db.add(fila)
        fila.dias = dias
        fila.actualizado_por = usuario_id
        self.db.commit()
        self.db.refresh(fila)
        return fila

    def delete_lead_time(self, lead_time_id: int) -> None:
        fila = self.db.query(ReabastecimientoLeadTime).filter(ReabastecimientoLeadTime.id == lead_time_id).first()
        if fila is None:
            raise ValueError(f"Configuración de lead time no encontrada: id={lead_time_id}")
        self.db.delete(fila)
        self.db.commit()
