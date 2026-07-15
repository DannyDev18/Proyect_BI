# backend/app/repositories/commission_config_repository.py
"""Acceso a datos de configuración del sistema de Comisiones Variables (docs/features/
plan_integracion_comisiones_variables.md §3.3). CRUD de las tablas `public.comision_*`
con vigencias -- nunca se edita una fila vigente, se cierra (`vigente_hasta`) y se
inserta una nueva, para preservar historial de liquidaciones ya calculadas."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.models.commission_config import (
    ComisionConfigVendedor, ComisionFactorCredito, ComisionLiquidacion, ComisionMatrizCategoria,
)
from app.services.commission_engine import RangoCredito, ReglaCategoria


class CommissionConfigRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Matriz de categorías ────────────────────────────────────────────────────
    def get_matriz_vigente(self, fecha: datetime.date | None = None) -> list[ComisionMatrizCategoria]:
        fecha = fecha or datetime.date.today()
        return (
            self.db.query(ComisionMatrizCategoria)
            .filter(
                ComisionMatrizCategoria.vigente_desde <= fecha,
                (ComisionMatrizCategoria.vigente_hasta.is_(None)) | (ComisionMatrizCategoria.vigente_hasta >= fecha),
            )
            .order_by(ComisionMatrizCategoria.clase, ComisionMatrizCategoria.subclase)
            .all()
        )

    def get_matriz_as_reglas(self, fecha: datetime.date | None = None) -> list[ReglaCategoria]:
        return [
            ReglaCategoria(
                clase=r.clase, subclase=r.subclase, grupo=r.grupo, tasa_pct=float(r.tasa_pct),
                base=r.base, factor_estrategico=float(r.factor_estrategico),
            )
            for r in self.get_matriz_vigente(fecha)
        ]

    def upsert_regla_categoria(
        self, clase: str, subclase: str | None, grupo: str, tasa_pct: float, base: str,
        factor_estrategico: float, creado_por: int | None,
    ) -> ComisionMatrizCategoria:
        """Cierra la vigencia de la regla activa para (clase, subclase) si existe, e
        inserta la nueva -- nunca hace UPDATE de una fila vigente (preserva historial)."""
        hoy = datetime.date.today()
        activa = (
            self.db.query(ComisionMatrizCategoria)
            .filter(
                ComisionMatrizCategoria.clase == clase, ComisionMatrizCategoria.subclase == subclase,
                ComisionMatrizCategoria.vigente_hasta.is_(None),
            )
            .first()
        )
        if activa:
            activa.vigente_hasta = hoy - datetime.timedelta(days=1)

        nueva = ComisionMatrizCategoria(
            clase=clase, subclase=subclase, grupo=grupo, tasa_pct=tasa_pct, base=base,
            factor_estrategico=factor_estrategico, vigente_desde=hoy, creado_por=creado_por,
        )
        self.db.add(nueva)
        self.db.commit()
        self.db.refresh(nueva)
        return nueva

    # ── Factores de crédito ─────────────────────────────────────────────────────
    def get_factores_credito_vigentes(self, fecha: datetime.date | None = None) -> list[ComisionFactorCredito]:
        fecha = fecha or datetime.date.today()
        return (
            self.db.query(ComisionFactorCredito)
            .filter(
                ComisionFactorCredito.vigente_desde <= fecha,
                (ComisionFactorCredito.vigente_hasta.is_(None)) | (ComisionFactorCredito.vigente_hasta >= fecha),
            )
            .order_by(ComisionFactorCredito.dias_desde)
            .all()
        )

    def get_factores_credito_as_rangos(self, fecha: datetime.date | None = None) -> list[RangoCredito]:
        return [
            RangoCredito(dias_desde=f.dias_desde, dias_hasta=f.dias_hasta, factor=float(f.factor))
            for f in self.get_factores_credito_vigentes(fecha)
        ]

    def replace_factores_credito(self, factores: list[dict]) -> list[ComisionFactorCredito]:
        """Reemplaza la matriz de crédito vigente completa (edición atómica desde el
        panel de gerencia): cierra todas las filas vigentes e inserta las nuevas."""
        hoy = datetime.date.today()
        vigentes = self.get_factores_credito_vigentes(hoy)
        for f in vigentes:
            f.vigente_hasta = hoy - datetime.timedelta(days=1)

        nuevas = [
            ComisionFactorCredito(
                dias_desde=f["dias_desde"], dias_hasta=f.get("dias_hasta"), factor=f["factor"],
                pct_al_facturar=f.get("pct_al_facturar", 100.0), vigente_desde=hoy,
            )
            for f in factores
        ]
        self.db.add_all(nuevas)
        self.db.commit()
        for n in nuevas:
            self.db.refresh(n)
        return nuevas

    # ── Configuración por vendedor (tipo externo/interno, brecha B1) ───────────
    def get_config_vendedor(self, vendedor_origen: str) -> ComisionConfigVendedor | None:
        return (
            self.db.query(ComisionConfigVendedor)
            .filter(ComisionConfigVendedor.id_vendedor_origen == vendedor_origen)
            .first()
        )

    def get_all_config_vendedores(self) -> list[ComisionConfigVendedor]:
        return self.db.query(ComisionConfigVendedor).order_by(ComisionConfigVendedor.id_vendedor_origen).all()

    def upsert_config_vendedor(
        self, vendedor_origen: str, tipo: str, factor_tipo: float, fecha_ingreso: datetime.date | None,
    ) -> ComisionConfigVendedor:
        existente = self.get_config_vendedor(vendedor_origen)
        if existente:
            existente.tipo = tipo
            existente.factor_tipo = factor_tipo
            existente.fecha_ingreso = fecha_ingreso
            self.db.commit()
            self.db.refresh(existente)
            return existente

        nuevo = ComisionConfigVendedor(
            id_vendedor_origen=vendedor_origen, tipo=tipo, factor_tipo=factor_tipo, fecha_ingreso=fecha_ingreso,
        )
        self.db.add(nuevo)
        self.db.commit()
        self.db.refresh(nuevo)
        return nuevo

    # ── Snapshots de liquidación (piloto en sombra / cierre oficial) ───────────
    def save_liquidacion(
        self, anio: int, mes: int, vendedor_origen: str, esquema: str, modo: str,
        comision_total: float, detalle_json: dict,
    ) -> ComisionLiquidacion:
        existente = (
            self.db.query(ComisionLiquidacion)
            .filter(
                ComisionLiquidacion.anio == anio, ComisionLiquidacion.mes == mes,
                ComisionLiquidacion.id_vendedor_origen == vendedor_origen,
                ComisionLiquidacion.esquema == esquema, ComisionLiquidacion.modo == modo,
            )
            .first()
        )
        if existente:
            existente.comision_total = comision_total
            existente.detalle_json = detalle_json
            self.db.commit()
            self.db.refresh(existente)
            return existente

        nuevo = ComisionLiquidacion(
            anio=anio, mes=mes, id_vendedor_origen=vendedor_origen, esquema=esquema, modo=modo,
            comision_total=comision_total, detalle_json=detalle_json,
        )
        self.db.add(nuevo)
        self.db.commit()
        self.db.refresh(nuevo)
        return nuevo
