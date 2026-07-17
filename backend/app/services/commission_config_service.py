# backend/app/services/commission_config_service.py
"""Configuración del sistema de Comisiones Variables expuesta a gerencia (docs/features/
plan_integracion_comisiones_variables.md §3.5): CRUD de matriz de categorías, factores
de crédito y tipo de vendedor, más los reportes de solo lectura de las Fases 1/2
(perfil de margen por categoría, líneas sin costo)."""
from __future__ import annotations

from app.core.exceptions import ValidationError
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.goal_repository import GoalRepository


class CommissionConfigService:
    def __init__(
        self, commission_config_repo: CommissionConfigRepository, goal_repo: GoalRepository,
        catalog_repo: CatalogRepository,
    ):
        self.commission_config_repo = commission_config_repo
        self.goal_repo = goal_repo
        self.catalog_repo = catalog_repo

    # ── Matriz de categorías ────────────────────────────────────────────────────
    def get_matriz(self) -> list[dict]:
        return [
            {
                "id": r.id, "clase": r.clase, "subclase": r.subclase, "grupo": r.grupo,
                "tasa_pct": float(r.tasa_pct), "base": r.base, "factor_estrategico": float(r.factor_estrategico),
                "vigente_desde": r.vigente_desde, "vigente_hasta": r.vigente_hasta,
            }
            for r in self.commission_config_repo.get_matriz_vigente()
        ]

    def upsert_regla_categoria(
        self, clase: str, subclase: str | None, grupo: str, tasa_pct: float, base: str,
        factor_estrategico: float, creado_por: int,
    ) -> dict:
        r = self.commission_config_repo.upsert_regla_categoria(
            clase=clase, subclase=subclase, grupo=grupo, tasa_pct=tasa_pct, base=base,
            factor_estrategico=factor_estrategico, creado_por=creado_por,
        )
        resultado = {
            "id": r.id, "clase": r.clase, "subclase": r.subclase, "grupo": r.grupo,
            "tasa_pct": float(r.tasa_pct), "base": r.base, "factor_estrategico": float(r.factor_estrategico),
            "vigente_desde": r.vigente_desde, "vigente_hasta": r.vigente_hasta,
        }
        self.commission_config_repo.log_cambio_config(
            usuario_id=creado_por, tabla="comision_matriz_categorias", accion="upsert",
            detalle={k: str(v) for k, v in resultado.items()},
        )
        return resultado

    # ── Factores de crédito ─────────────────────────────────────────────────────
    def get_factores_credito(self) -> list[dict]:
        return [
            {
                "id": f.id, "dias_desde": f.dias_desde, "dias_hasta": f.dias_hasta,
                "factor": float(f.factor), "pct_al_facturar": float(f.pct_al_facturar),
                "vigente_desde": f.vigente_desde, "vigente_hasta": f.vigente_hasta,
            }
            for f in self.commission_config_repo.get_factores_credito_vigentes()
        ]

    def replace_factores_credito(self, factores: list[dict], usuario_id: int | None = None) -> list[dict]:
        """Valida que los rangos entrantes no se solapen antes de reemplazar la matriz
        vigente (auditoría 34, H-9): `commission_engine._factor_credito` resuelve por el
        primer rango que matchea en orden de lista -- rangos solapados dan un resultado
        que depende del orden de lectura de la BD, no de una regla de negocio explícita."""
        self._validar_rangos_credito_sin_solape(factores)
        nuevos = self.commission_config_repo.replace_factores_credito(factores)
        resultado = [
            {
                "id": f.id, "dias_desde": f.dias_desde, "dias_hasta": f.dias_hasta,
                "factor": float(f.factor), "pct_al_facturar": float(f.pct_al_facturar),
                "vigente_desde": f.vigente_desde, "vigente_hasta": f.vigente_hasta,
            }
            for f in nuevos
        ]
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_factores_credito", accion="replace",
            detalle={"factores": [{k: str(v) for k, v in f.items()} for f in resultado]},
        )
        return resultado

    # ── Configuración por vendedor (tipo externo/interno) ───────────────────────
    def get_config_vendedores(self) -> list[dict]:
        """`nombre_vendedor` se enriquece con UNA sola consulta por lote a
        `edw.dim_vendedor` (no una consulta por fila) para no colapsar el backend
        cuando la lista de vendedores configurados crezca."""
        configs = self.commission_config_repo.get_all_config_vendedores()
        nombres = self.catalog_repo.get_vendedores_info([v.id_vendedor_origen for v in configs])
        return [
            {
                "id_vendedor_origen": v.id_vendedor_origen, "nombre_vendedor": nombres.get(v.id_vendedor_origen),
                "tipo": v.tipo, "factor_tipo": float(v.factor_tipo),
                "fecha_ingreso": v.fecha_ingreso, "activo": v.activo,
            }
            for v in configs
        ]

    # ── Búsqueda inteligente (autocomplete, sin N+1) ────────────────────────────
    def search_vendedores(self, q: str, limit: int = 10) -> list[dict]:
        return self.catalog_repo.search_vendedores(q, limit)

    def search_clases_producto(self, q: str, limit: int = 10) -> list[dict]:
        return self.catalog_repo.search_clases_producto(q, limit)

    def upsert_config_vendedor(
        self, vendedor_origen: str, tipo: str, factor_tipo: float, fecha_ingreso, usuario_id: int | None = None,
    ) -> dict:
        v = self.commission_config_repo.upsert_config_vendedor(vendedor_origen, tipo, factor_tipo, fecha_ingreso)
        resultado = {
            "id_vendedor_origen": v.id_vendedor_origen, "tipo": v.tipo, "factor_tipo": float(v.factor_tipo),
            "fecha_ingreso": v.fecha_ingreso, "activo": v.activo,
        }
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_config_vendedor", accion="upsert",
            detalle={k: str(v) for k, v in resultado.items()},
        )
        return resultado

    @staticmethod
    def _validar_rangos_credito_sin_solape(factores: list[dict]) -> None:
        rangos = sorted(
            ((f["dias_desde"], f.get("dias_hasta")) for f in factores), key=lambda r: r[0],
        )
        for (desde_a, hasta_a), (desde_b, hasta_b) in zip(rangos, rangos[1:]):
            fin_a = hasta_a if hasta_a is not None else float("inf")
            if desde_b <= fin_a:
                raise ValidationError(
                    f"Los rangos de crédito se solapan: [{desde_a}, {hasta_a if hasta_a is not None else '∞'}] "
                    f"y [{desde_b}, {hasta_b if hasta_b is not None else '∞'}]."
                )

    # ── Reportes de solo lectura (Fase 1 / salvaguarda 2) ───────────────────────
    def get_perfil_categorias(self, meses: int = 24) -> list[dict]:
        return self.goal_repo.get_margin_profile_by_category(meses)

    def get_lineas_sin_costo(self, anio: int, mes: int) -> list[dict]:
        return self.goal_repo.get_lines_without_cost(anio, mes)

    # ── Bitácora de cambios (Fase 2 ítem 2, plan_actualizacion_modulo_metas_comisiones.md §3) ──
    def get_auditoria(self, limit: int = 100) -> list[dict]:
        return [
            {
                "id": a.id, "usuario_id": a.usuario_id, "usuario_nombre": nombre,
                "tabla": a.tabla, "accion": a.accion,
                "detalle_json": a.detalle_json, "fecha_creacion": a.fecha_creacion,
            }
            for a, nombre in self.commission_config_repo.get_auditoria(limit)
        ]
