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
from app.services.commission_engine import COMPONENTES_FORMULA, PERFIL_EXTERNO, PERFIL_INTERNO, PERFIL_JEFE_AGENCIA


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

    def eliminar_regla_categoria(self, regla_id: int, usuario_id: int) -> dict:
        r = self.commission_config_repo.desactivar_regla_categoria(regla_id)
        resultado = {
            "id": r.id, "clase": r.clase, "subclase": r.subclase, "grupo": r.grupo,
            "tasa_pct": float(r.tasa_pct), "base": r.base, "factor_estrategico": float(r.factor_estrategico),
            "vigente_desde": r.vigente_desde, "vigente_hasta": r.vigente_hasta,
        }
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_matriz_categorias", accion="eliminar",
            detalle={k: str(v) for k, v in resultado.items()},
        )
        return resultado

    # ── Factores de crédito ─────────────────────────────────────────────────────
    def get_factores_credito(self) -> list[dict]:
        return [
            {
                "id": f.id, "dias_desde": f.dias_desde, "dias_hasta": f.dias_hasta,
                "factor": float(f.factor),
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
                "factor": float(f.factor),
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
                "fecha_ingreso": v.fecha_ingreso, "activo": v.activo, "agencia": v.agencia,
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
        agencia: str | None = None,
    ) -> dict:
        # RN (auditoría 44): 'jefe_agencia' SIN agencia deja el componente
        # 'contado_agencia' en 0 silenciosamente (ver CommissionService); se exige aquí
        # para no dejar pasar un error de captura del formulario sin avisar.
        if tipo == PERFIL_JEFE_AGENCIA and not agencia:
            raise ValidationError("El perfil 'jefe_agencia' requiere indicar la agencia (establ).")
        v = self.commission_config_repo.upsert_config_vendedor(
            vendedor_origen, tipo, factor_tipo, fecha_ingreso, agencia=agencia,
        )
        resultado = {
            "id_vendedor_origen": v.id_vendedor_origen, "tipo": v.tipo, "factor_tipo": float(v.factor_tipo),
            "fecha_ingreso": v.fecha_ingreso, "activo": v.activo, "agencia": v.agencia,
        }
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_config_vendedor", accion="upsert",
            detalle={k: str(v) for k, v in resultado.items()},
        )
        return resultado

    # ── Tramos de comisión sobre COBROS (auditoría 44 §2.1) ──────────────────────
    _PERFILES_TRAMO = (PERFIL_EXTERNO, PERFIL_INTERNO, PERFIL_JEFE_AGENCIA)

    def get_todos_tramos_cobranza(self) -> dict:
        vigentes = self.commission_config_repo.get_todos_tramos_cobranza_vigentes()
        por_perfil: dict[str, list[dict]] = {p: [] for p in self._PERFILES_TRAMO}
        for t in vigentes:
            por_perfil.setdefault(t.perfil, []).append({
                "id": t.id, "perfil": t.perfil, "dias_hasta": t.dias_hasta, "tasa_pct": float(t.tasa_pct),
                "vigente_desde": t.vigente_desde, "vigente_hasta": t.vigente_hasta,
            })
        return por_perfil

    def replace_tramos_cobranza(self, perfil: str, tramos: list[dict], usuario_id: int | None = None) -> list[dict]:
        """Valida que los tramos entrantes tengan techos crecientes y sin duplicados
        antes de reemplazar -- `resolver_tramo_cobranza` resuelve por el primer tramo que
        cubre `dias_cobro` en orden de `dias_hasta`; techos duplicados o desordenados
        dejarían un tramo inalcanzable sin que la UI lo advierta."""
        self._validar_tramos_cobranza(tramos)
        nuevos = self.commission_config_repo.replace_tramos_cobranza(perfil, tramos, creado_por=usuario_id)
        resultado = [
            {
                "id": t.id, "perfil": t.perfil, "dias_hasta": t.dias_hasta, "tasa_pct": float(t.tasa_pct),
                "vigente_desde": t.vigente_desde, "vigente_hasta": t.vigente_hasta,
            }
            for t in nuevos
        ]
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_tramos_cobranza", accion="replace",
            detalle={"perfil": perfil, "tramos": [{k: str(v) for k, v in t.items()} for t in resultado]},
        )
        return resultado

    @staticmethod
    def _validar_tramos_cobranza(tramos: list[dict]) -> None:
        techos = [t.get("dias_hasta") for t in tramos]
        if len(techos) != len(set(techos)):
            raise ValidationError("Hay tramos de cobranza con el mismo 'dias_hasta' -- cada techo debe ser único.")
        finitos = sorted(t for t in techos if t is not None)
        if finitos and any(a >= b for a, b in zip(finitos, finitos[1:])):
            raise ValidationError("Los tramos con 'dias_hasta' finito deben ser estrictamente crecientes.")

    # ── Tramos de cumplimiento (auditoría 45) ────────────────────────────────────
    # La semilla usa un solo juego de tramos GENÉRICOS (`perfil=None`) -- la
    # diferenciación por perfil externo/interno/jefe_agencia queda descartada
    # explícitamente en esta fase (§5.3 del plan); la columna existe en el modelo
    # para admitirla a futuro sin migración nueva, pero el panel solo edita los
    # genéricos, que son los que el simulador y el cálculo real resuelven hoy.
    def get_tramos_cumplimiento(self) -> list[dict]:
        return [
            {
                "id": t.id, "pct_desde": float(t.pct_desde),
                "pct_hasta": (float(t.pct_hasta) if t.pct_hasta is not None else None),
                "multiplicador": float(t.multiplicador), "etiqueta": t.etiqueta,
                "bono_fijo": float(t.bono_fijo),
                "vigente_desde": t.vigente_desde, "vigente_hasta": t.vigente_hasta,
            }
            for t in self.commission_config_repo.get_tramos_cumplimiento_vigentes(None)
        ]

    def replace_tramos_cumplimiento(self, tramos: list[dict], usuario_id: int | None = None) -> list[dict]:
        """Valida que los tramos entrantes cubran `[0, ∞)` sin huecos ni solapes antes
        de reemplazar -- `resolver_tramo_cumplimiento` resuelve por el primer tramo que
        cubre el % de cumplimiento; un hueco dejaría a un vendedor sin multiplicador
        resoluble en ese rango."""
        self._validar_tramos_cumplimiento(tramos)
        nuevos = self.commission_config_repo.replace_tramos_cumplimiento(None, tramos, creado_por=usuario_id)
        resultado = [
            {
                "id": t.id, "pct_desde": float(t.pct_desde),
                "pct_hasta": (float(t.pct_hasta) if t.pct_hasta is not None else None),
                "multiplicador": float(t.multiplicador), "etiqueta": t.etiqueta,
                "bono_fijo": float(t.bono_fijo),
                "vigente_desde": t.vigente_desde, "vigente_hasta": t.vigente_hasta,
            }
            for t in nuevos
        ]
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_tramos_cumplimiento", accion="replace",
            detalle={"tramos": [{k: str(v) for k, v in t.items()} for t in resultado]},
        )
        return resultado

    @staticmethod
    def _validar_tramos_cumplimiento(tramos: list[dict]) -> None:
        if not tramos:
            raise ValidationError("Se requiere al menos un tramo de cumplimiento.")
        for t in tramos:
            if float(t["multiplicador"]) < 0:
                raise ValidationError(f"El multiplicador del tramo {t.get('etiqueta', '')!r} no puede ser negativo.")
            if float(t.get("bono_fijo", 0.0)) < 0:
                raise ValidationError(f"El bono fijo del tramo {t.get('etiqueta', '')!r} no puede ser negativo.")
            if float(t["pct_desde"]) < 0:
                raise ValidationError(f"El tramo {t.get('etiqueta', '')!r} tiene 'pct_desde' negativo.")
            pct_hasta = t.get("pct_hasta")
            if pct_hasta is not None and float(pct_hasta) <= float(t["pct_desde"]):
                raise ValidationError(
                    f"El tramo {t.get('etiqueta', '')!r} tiene 'pct_hasta' <= 'pct_desde'."
                )

        ordenados = sorted(tramos, key=lambda t: float(t["pct_desde"]))
        if float(ordenados[0]["pct_desde"]) != 0.0:
            raise ValidationError("Los tramos de cumplimiento deben cubrir desde 0% -- falta el tramo inicial.")
        abiertos = [t for t in ordenados if t.get("pct_hasta") is None]
        if len(abiertos) != 1 or ordenados[-1].get("pct_hasta") is not None:
            raise ValidationError(
                "Debe existir exactamente un tramo final sin 'pct_hasta' (sin tope superior), "
                "y debe ser el de mayor 'pct_desde'."
            )
        for actual, siguiente in zip(ordenados, ordenados[1:]):
            if float(actual["pct_hasta"]) != float(siguiente["pct_desde"]):
                raise ValidationError(
                    f"Hay un hueco o solape entre los tramos {actual.get('etiqueta', '')!r} "
                    f"(hasta {actual['pct_hasta']}) y {siguiente.get('etiqueta', '')!r} "
                    f"(desde {siguiente['pct_desde']}) -- deben ser contiguos."
                )

    # ── Fórmula de comisión (auditoría 44 §2.2) ──────────────────────────────────
    def get_formulas(self) -> dict:
        formulas = self.commission_config_repo.get_todas_las_formulas()
        return {
            "formulas": [
                {
                    "id": f.id, "clave": f.clave, "nombre": f.nombre, "activa": f.activa,
                    "componentes": [
                        {
                            "id": c.id, "orden": c.orden, "componente": c.componente,
                            "operador": c.operador, "activo": c.activo, "parametros": c.parametros,
                        }
                        for c in componentes
                    ],
                }
                for f, componentes in formulas
            ],
            "catalogo_componentes": sorted(COMPONENTES_FORMULA),
        }

    def reemplazar_componentes_formula(
        self, formula_id: int, componentes: list[dict], usuario_id: int | None = None,
    ) -> list[dict]:
        self._validar_componentes_formula(componentes)
        nuevos = self.commission_config_repo.reemplazar_componentes_formula(formula_id, componentes)
        resultado = [
            {
                "id": c.id, "orden": c.orden, "componente": c.componente,
                "operador": c.operador, "activo": c.activo, "parametros": c.parametros,
            }
            for c in nuevos
        ]
        self.commission_config_repo.log_cambio_config(
            usuario_id=usuario_id, tabla="comision_formula", accion="reemplazar_componentes",
            detalle={"formula_id": formula_id, "componentes": [{k: str(v) for k, v in c.items()} for c in resultado]},
        )
        return resultado

    @staticmethod
    def _validar_componentes_formula(componentes: list[dict]) -> None:
        """Catálogo cerrado (R-4 del plan): NUNCA se acepta una clave de componente fuera
        de `COMPONENTES_FORMULA` -- esto es lo que impide que la "fórmula editable" se
        convierta en una superficie de ejecución de código arbitrario."""
        if not componentes:
            raise ValidationError("Una fórmula necesita al menos un componente.")
        for c in componentes:
            if c["componente"] not in COMPONENTES_FORMULA:
                raise ValidationError(
                    f"Componente de fórmula desconocido: {c['componente']!r}. "
                    f"Catálogo válido: {sorted(COMPONENTES_FORMULA)}."
                )
        ordenes = [c["orden"] for c in componentes]
        if len(ordenes) != len(set(ordenes)):
            raise ValidationError("Hay componentes de la fórmula con el mismo 'orden'.")
        activos = [c for c in componentes if c.get("activo", True)]
        tiene_base = any(
            c["componente"] in ("base_lineas_venta", "base_cobranza", "contado_agencia") for c in activos
        )
        if not tiene_base:
            raise ValidationError(
                "La fórmula necesita al menos un componente base activo "
                "(base_lineas_venta, base_cobranza o contado_agencia)."
            )

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
