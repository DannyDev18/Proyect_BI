# backend/app/repositories/commission_config_repository.py
"""Acceso a datos de configuración del sistema de Comisiones Variables (docs/features/
plan_integracion_comisiones_variables.md §3.3). CRUD de las tablas `public.comision_*`
con vigencias -- nunca se edita una fila vigente, se cierra (`vigente_hasta`) y se
inserta una nueva, para preservar historial de liquidaciones ya calculadas."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.commission_config import (
    ComisionConfigAuditoria, ComisionConfigVendedor, ComisionFactorCredito, ComisionFormula,
    ComisionFormulaComponente, ComisionLiquidacion, ComisionMatrizCategoria, ComisionTramoCobranza,
)
from app.models.user import User
from app.services.commission_engine import RangoCredito, ReglaCategoria, TramoCobranza


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

    def desactivar_regla_categoria(self, regla_id: int) -> ComisionMatrizCategoria:
        """Baja real de una regla: cierra su vigencia sin insertar una nueva (a
        diferencia de `upsert_regla_categoria`, que siempre reemplaza) -- la clase/
        subclase queda sin regla propia y cae al comodín `('*', NULL)` si existe.
        Nunca DELETE físico: las liquidaciones ya congeladas que consultaron esta
        regla por fecha histórica deben seguir viéndola."""
        regla = self.db.query(ComisionMatrizCategoria).filter(ComisionMatrizCategoria.id == regla_id).first()
        if regla is None:
            raise NotFoundError(f"No existe una regla de categoría con id={regla_id}.")
        if regla.vigente_hasta is not None:
            raise ConflictError(f"La regla id={regla_id} ya no está vigente (se cerró el {regla.vigente_hasta}).")

        regla.vigente_hasta = datetime.date.today() - datetime.timedelta(days=1)
        self.db.commit()
        self.db.refresh(regla)
        return regla

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
                vigente_desde=hoy,
            )
            for f in factores
        ]
        self.db.add_all(nuevas)
        self.db.commit()
        for n in nuevas:
            self.db.refresh(n)
        return nuevas

    # ── Configuración por vendedor (tipo externo/interno, brecha B1) ───────────
    def get_config_vendedor(
        self, vendedor_origen: str, fecha: datetime.date | None = None,
    ) -> ComisionConfigVendedor | None:
        """Resuelve por vigencia (C-3, docs/features/plan_correcciones_pendientes.md;
        auditoría 35 H4): sin `fecha` devuelve la configuración vigente hoy; pasando la
        fecha de cierre de un período (`fecha_referencia_periodo`) devuelve el tipo/
        factor con el que ese período se calculó, sin importar cambios posteriores."""
        fecha = fecha or datetime.date.today()
        return (
            self.db.query(ComisionConfigVendedor)
            .filter(
                ComisionConfigVendedor.id_vendedor_origen == vendedor_origen,
                ComisionConfigVendedor.vigente_desde <= fecha,
                (ComisionConfigVendedor.vigente_hasta.is_(None)) | (ComisionConfigVendedor.vigente_hasta >= fecha),
            )
            .first()
        )

    def get_all_config_vendedores(self) -> list[ComisionConfigVendedor]:
        """Solo las configuraciones vigentes hoy (`vigente_hasta IS NULL`) -- el listado
        de gerencia no debe mostrar historial cerrado."""
        return (
            self.db.query(ComisionConfigVendedor)
            .filter(ComisionConfigVendedor.vigente_hasta.is_(None))
            .order_by(ComisionConfigVendedor.id_vendedor_origen)
            .all()
        )

    def upsert_config_vendedor(
        self, vendedor_origen: str, tipo: str, factor_tipo: float, fecha_ingreso: datetime.date | None,
        agencia: str | None = None,
    ) -> ComisionConfigVendedor:
        """Cierra la vigencia activa del vendedor si existe, e inserta la nueva -- nunca
        hace UPDATE de una fila vigente (mismo patrón que `upsert_regla_categoria`),
        para preservar lo que las liquidaciones ya congeladas usaron al calcularse.

        `agencia` (auditoría 44): solo tiene sentido para el perfil `jefe_agencia`
        (componente `contado_agencia` de la fórmula); se acepta para cualquier perfil sin
        validar aquí -- la validación de negocio (perfil-agencia coherente) vive en el
        servicio, no en el repositorio."""
        hoy = datetime.date.today()
        activa = (
            self.db.query(ComisionConfigVendedor)
            .filter(
                ComisionConfigVendedor.id_vendedor_origen == vendedor_origen,
                ComisionConfigVendedor.vigente_hasta.is_(None),
            )
            .first()
        )
        if activa:
            activa.vigente_hasta = hoy - datetime.timedelta(days=1)

        nuevo = ComisionConfigVendedor(
            id_vendedor_origen=vendedor_origen, tipo=tipo, factor_tipo=factor_tipo,
            fecha_ingreso=fecha_ingreso, agencia=agencia, vigente_desde=hoy,
        )
        self.db.add(nuevo)
        self.db.commit()
        self.db.refresh(nuevo)
        return nuevo

    # ── Tramos de comisión sobre cobros (auditoría 44, RN-CM8/RN-CM9) ───────────
    def get_tramos_cobranza_vigentes(
        self, perfil: str, fecha: datetime.date | None = None,
    ) -> list[ComisionTramoCobranza]:
        fecha = fecha or datetime.date.today()
        return (
            self.db.query(ComisionTramoCobranza)
            .filter(
                ComisionTramoCobranza.perfil == perfil,
                ComisionTramoCobranza.vigente_desde <= fecha,
                (ComisionTramoCobranza.vigente_hasta.is_(None)) | (ComisionTramoCobranza.vigente_hasta >= fecha),
            )
            .order_by(ComisionTramoCobranza.dias_hasta.asc().nulls_last())
            .all()
        )

    def get_todos_tramos_cobranza_vigentes(self, fecha: datetime.date | None = None) -> list[ComisionTramoCobranza]:
        """Los 3 perfiles a la vez -- para el panel de configuración de gerencia."""
        fecha = fecha or datetime.date.today()
        return (
            self.db.query(ComisionTramoCobranza)
            .filter(
                ComisionTramoCobranza.vigente_desde <= fecha,
                (ComisionTramoCobranza.vigente_hasta.is_(None)) | (ComisionTramoCobranza.vigente_hasta >= fecha),
            )
            .order_by(ComisionTramoCobranza.perfil, ComisionTramoCobranza.dias_hasta.asc().nulls_last())
            .all()
        )

    def get_tramos_cobranza_as_rangos(self, perfil: str, fecha: datetime.date | None = None) -> list[TramoCobranza]:
        return [
            TramoCobranza(dias_hasta=t.dias_hasta, tasa_pct=float(t.tasa_pct))
            for t in self.get_tramos_cobranza_vigentes(perfil, fecha)
        ]

    def replace_tramos_cobranza(self, perfil: str, tramos: list[dict], creado_por: int | None) -> list[ComisionTramoCobranza]:
        """Reemplaza los tramos vigentes de UN perfil (edición atómica desde el panel):
        cierra las filas vigentes de ese perfil e inserta las nuevas -- mismo patrón que
        `replace_factores_credito`. Los otros perfiles no se tocan."""
        hoy = datetime.date.today()
        vigentes = self.get_tramos_cobranza_vigentes(perfil, hoy)
        for t in vigentes:
            t.vigente_hasta = hoy - datetime.timedelta(days=1)

        nuevos = [
            ComisionTramoCobranza(
                perfil=perfil, dias_hasta=t.get("dias_hasta"), tasa_pct=t["tasa_pct"],
                vigente_desde=hoy, creado_por=creado_por,
            )
            for t in tramos
        ]
        self.db.add_all(nuevos)
        self.db.commit()
        for n in nuevos:
            self.db.refresh(n)
        return nuevos

    # ── Fórmula de comisión (auditoría 44: estructura editable, no quemada en código) ──
    def get_formula_activa(self) -> tuple[ComisionFormula, list[ComisionFormulaComponente]] | None:
        formula = self.db.query(ComisionFormula).filter(ComisionFormula.activa.is_(True)).first()
        if formula is None:
            return None
        componentes = (
            self.db.query(ComisionFormulaComponente)
            .filter(ComisionFormulaComponente.formula_id == formula.id, ComisionFormulaComponente.activo.is_(True))
            .order_by(ComisionFormulaComponente.orden)
            .all()
        )
        return formula, componentes

    def get_todas_las_formulas(self) -> list[tuple[ComisionFormula, list[ComisionFormulaComponente]]]:
        formulas = self.db.query(ComisionFormula).order_by(ComisionFormula.clave).all()
        resultado = []
        for f in formulas:
            componentes = (
                self.db.query(ComisionFormulaComponente)
                .filter(ComisionFormulaComponente.formula_id == f.id)
                .order_by(ComisionFormulaComponente.orden)
                .all()
            )
            resultado.append((f, componentes))
        return resultado

    def reemplazar_componentes_formula(
        self, formula_id: int, componentes: list[dict],
    ) -> list[ComisionFormulaComponente]:
        """Reemplaza TODA la tubería de una fórmula (borra los pasos existentes e
        inserta los nuevos) -- a diferencia de la matriz de categorías o los tramos de
        cobranza, una fórmula no tiene "historial de vigencia" propio: es la definición
        estructural vigente en el momento en que se calcula cada mes en curso; los
        períodos ya cerrados quedan protegidos por el snapshot congelado de
        `comision_liquidaciones` (salvaguarda 6), no por vigencia de la fórmula misma."""
        formula = self.db.query(ComisionFormula).filter(ComisionFormula.id == formula_id).first()
        if formula is None:
            raise NotFoundError(f"No existe una fórmula con id={formula_id}.")

        self.db.query(ComisionFormulaComponente).filter(
            ComisionFormulaComponente.formula_id == formula_id
        ).delete(synchronize_session=False)

        nuevos = [
            ComisionFormulaComponente(
                formula_id=formula_id, orden=c["orden"], componente=c["componente"],
                operador=c["operador"], activo=c.get("activo", True), parametros=c.get("parametros") or {},
            )
            for c in componentes
        ]
        self.db.add_all(nuevos)
        self.db.commit()
        for n in nuevos:
            self.db.refresh(n)
        return nuevos

    # ── Snapshots de liquidación (piloto en sombra / cierre oficial) ───────────
    def get_liquidacion(
        self, anio: int, mes: int, vendedor_origen: str, esquema: str, modo: str,
    ) -> ComisionLiquidacion | None:
        """Snapshot ya congelado para este período/vendedor/esquema/modo, si existe
        (docs/auditoria/35_actualizacion_modulo_metas.md, H2: inmutabilidad real de
        liquidaciones oficiales -- el llamador debe devolverlo tal cual, sin recalcular)."""
        return (
            self.db.query(ComisionLiquidacion)
            .filter(
                ComisionLiquidacion.anio == anio, ComisionLiquidacion.mes == mes,
                ComisionLiquidacion.id_vendedor_origen == vendedor_origen,
                ComisionLiquidacion.esquema == esquema, ComisionLiquidacion.modo == modo,
            )
            .first()
        )

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

    # ── Bitácora de cambios de configuración (Fase 2 ítem 2, plan_actualizacion_
    # modulo_metas_comisiones.md §3) ─────────────────────────────────────────────
    def log_cambio_config(self, usuario_id: int | None, tabla: str, accion: str, detalle: dict) -> None:
        """Append-only: se llama DESPUÉS de cada upsert/replace exitoso de matriz de
        categorías, factores de crédito o config de vendedor -- nunca se actualiza ni
        se borra una fila de esta tabla."""
        self.db.add(ComisionConfigAuditoria(
            usuario_id=usuario_id, tabla=tabla, accion=accion, detalle_json=detalle,
        ))
        self.db.commit()

    def get_auditoria(self, limit: int = 100) -> list[tuple[ComisionConfigAuditoria, str | None]]:
        """Devuelve cada entrada junto al nombre del usuario que hizo el cambio (LEFT
        JOIN: un usuario luego eliminado no debe tumbar la lectura del historial)."""
        rows = (
            self.db.query(ComisionConfigAuditoria, User.nombre)
            .outerjoin(User, ComisionConfigAuditoria.usuario_id == User.id)
            .order_by(ComisionConfigAuditoria.fecha_creacion.desc())
            .limit(limit)
            .all()
        )
        return [(entrada, nombre) for entrada, nombre in rows]
