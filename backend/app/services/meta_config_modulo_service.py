# backend/app/services/meta_config_modulo_service.py
"""Servicio de configuración modular del motor de metas v3 (docs/features/
plan_motor_metas_v3_y_comisiones_unificadas.md §9/§18, Fase 6): valida contra el
catálogo cerrado de `goal_pipeline_stages.ETAPAS_CATALOGO` (nunca un método inexistente o
declarado-pero-no-implementado) y traduce la configuración persistida a las estructuras
que consume el motor real -- `MetaMotorParametros` (E1/E2/E3/E4/E5/E10, delegadas en
`IQRGoalCalculationEngine`, ya probado) y `PipelineConfigV3` (E6-E9/E11/E13/E15/E16,
`goal_pipeline_stages.py`)."""
from app.core.exceptions import ValidationError
from app.models.meta_config_modulo import MetaConfigModulo
from app.repositories.meta_config_modulo_repository import MetaConfigModuloRepository
from app.services.goal_calculation_engine import DEFAULT_PARAMETROS, MetaMotorParametros
from app.services.goal_pipeline_stages import ETAPAS_CATALOGO, PipelineConfigV3, metodo_implementado

# Rango [mínimo, máximo] aceptado por parámetro numérico conocido -- mismo criterio que
# `meta_config_service.RANGOS_VALIDOS` (auditoría 46): nunca un valor que anule un
# guardarraíl (ej. `banda_alcanzabilidad_max=5.0`) se guarde sin control.
RANGOS_PARAMETROS: dict[str, tuple[float, float]] = {
    "k": (0.5, 3.0), "ventana_referencia": (4, 36), "meses_minimos_para_iqr": (2, 12),
    "min_anios_estacional": (1, 5),
    "ventana": (2, 12), "factor_tendencia_min": (0.5, 1.0), "factor_tendencia_max": (1.0, 2.0),
    "cv_alto": (0.1, 2.0), "peso_estabilidad_min": (0.0, 1.0),
    "umbral_nuevo_meses": (1, 12), "umbral_maduro_meses": (12, 60), "peso_benchmark_intermedio": (0.0, 1.0),
    "crecimiento_pct": (-50.0, 100.0),
    "externo": (0.5, 2.0), "interno": (0.5, 2.0),
    "holgura": (1.0, 2.0),
    "banda_alcanzabilidad_min": (0.5, 1.0), "banda_alcanzabilidad_max": (1.0, 2.0), "meses_referencia_alcanzable": (2, 24),
    "multiplo": (1, 10000),
    "min": (0.5, 1.0), "max": (1.0, 2.0),
    "peso": (0.0, 1.0),
    "umbral_cv": (0.1, 2.0), "factor_reduccion": (0.0, 1.0),
}


class MetaConfigModuloService:
    def __init__(self, repo: MetaConfigModuloRepository):
        self.repo = repo

    @staticmethod
    def get_catalogo() -> dict:
        return ETAPAS_CATALOGO

    def get_modulos(self) -> list[MetaConfigModulo]:
        return self.repo.get_all()

    def update_modulo(self, etapa: str, metodo: str | None, activo: bool, parametros: dict, usuario_id: int | None) -> MetaConfigModulo:
        if etapa not in ETAPAS_CATALOGO:
            raise ValidationError(f"Etapa de configuración de metas desconocida: {etapa}")
        if activo:
            ok, motivo = metodo_implementado(etapa, metodo)
            if not ok:
                raise ValidationError(f"No se puede activar la etapa '{etapa}': {motivo}")
        for clave, valor in (parametros or {}).items():
            rango = RANGOS_PARAMETROS.get(clave)
            if rango is None or not isinstance(valor, (int, float)):
                continue
            minimo, maximo = rango
            if not (minimo <= valor <= maximo):
                raise ValidationError(f"El parámetro '{clave}' de la etapa '{etapa}' debe estar entre {minimo} y {maximo} (recibido: {valor}).")
        try:
            return self.repo.update_modulo(etapa, metodo, activo, parametros or {}, usuario_id)
        except ValueError as e:
            raise ValidationError(str(e)) from e

    def get_auditoria(self, limit: int = 100):
        return self.repo.get_auditoria(limit=limit)

    # ── Traducción a las estructuras que consume el motor ──────────────────────────────
    def get_pipeline_config(self) -> tuple[MetaMotorParametros, PipelineConfigV3]:
        """Une E1-E5/E10 (parámetros de `IQRGoalCalculationEngine`, ya probado) con
        E6-E9/E11/E13/E15/E16 (`PipelineConfigV3`) en una sola resolución por request
        (mismo patrón de pre-resolución que `CommissionSimulationService`)."""
        modulos = {m.etapa: m for m in self.repo.get_all()}
        campos_motor: dict = {}
        snapshot: dict = {}

        def p(etapa: str, clave: str, default):
            m = modulos.get(etapa)
            if m is None:
                return default
            return (m.parametros or {}).get(clave, default)

        def activo(etapa: str, default: bool = True) -> bool:
            m = modulos.get(etapa)
            return bool(m.activo) if m is not None else default

        for etapa, m in modulos.items():
            snapshot[etapa] = {"metodo": m.metodo, "activo": m.activo, "parametros": m.parametros}

        campos_motor["ventana_referencia_outliers"] = int(p("E1_limpieza", "ventana_referencia", DEFAULT_PARAMETROS.ventana_referencia_outliers))
        campos_motor["iqr_multiplicador"] = float(p("E1_limpieza", "k", DEFAULT_PARAMETROS.iqr_multiplicador))
        campos_motor["meses_minimos_para_iqr"] = int(p("E1_limpieza", "meses_minimos_para_iqr", DEFAULT_PARAMETROS.meses_minimos_para_iqr))
        campos_motor["min_anios_estacional"] = int(p("E3_estacionalidad", "min_anios_estacional", DEFAULT_PARAMETROS.min_anios_estacional))
        campos_motor["meses_tendencia_reciente"] = int(p("E4_tendencia", "ventana", DEFAULT_PARAMETROS.meses_tendencia_reciente))
        campos_motor["factor_tendencia_min"] = float(p("E4_tendencia", "factor_tendencia_min", DEFAULT_PARAMETROS.factor_tendencia_min))
        campos_motor["factor_tendencia_max"] = float(p("E4_tendencia", "factor_tendencia_max", DEFAULT_PARAMETROS.factor_tendencia_max))
        campos_motor["cv_alto"] = float(p("E5_estabilidad", "cv_alto", DEFAULT_PARAMETROS.cv_alto))
        campos_motor["peso_estabilidad_min"] = float(p("E5_estabilidad", "peso_estabilidad_min", DEFAULT_PARAMETROS.peso_estabilidad_min))
        campos_motor["banda_alcanzabilidad_min"] = float(p("E10_restricciones", "banda_alcanzabilidad_min", DEFAULT_PARAMETROS.banda_alcanzabilidad_min))
        campos_motor["banda_alcanzabilidad_max"] = float(p("E10_restricciones", "banda_alcanzabilidad_max", DEFAULT_PARAMETROS.banda_alcanzabilidad_max))
        campos_motor["meses_referencia_alcanzable"] = int(p("E10_restricciones", "meses_referencia_alcanzable", DEFAULT_PARAMETROS.meses_referencia_alcanzable))
        motor_parametros = MetaMotorParametros(**campos_motor)

        pipeline = PipelineConfigV3(
            aplicar_limpieza=activo("E1_limpieza"),
            aplicar_estacionalidad=activo("E3_estacionalidad"),
            aplicar_tendencia=activo("E4_tendencia"),
            aplicar_estabilidad=activo("E5_estabilidad"),
            aplicar_banda=activo("E10_restricciones"),
            umbral_nuevo_meses=int(p("E6_madurez", "umbral_nuevo_meses", 6)),
            umbral_maduro_meses=int(p("E6_madurez", "umbral_maduro_meses", 24)),
            peso_propio_intermedio=1.0 - float(p("E6_madurez", "peso_benchmark_intermedio", 0.20)),
            estrategia_activa=activo("E7_estrategia", default=False),
            crecimiento_pct=float(p("E7_estrategia", "crecimiento_pct", 0.0)),
            factores_tipo_vendedor={
                "externo": float(p("E8_tipo_vendedor", "externo", 1.10)),
                "interno": float(p("E8_tipo_vendedor", "interno", 0.95)),
            },
            capacidad_activa=activo("E9_capacidad", default=False),
            capacidad_holgura=float(p("E9_capacidad", "holgura", 1.10)),
            redondeo_multiplo=int(p("E11_redondeo", "multiplo", 100)),
            redondeo_modo=modulos["E11_redondeo"].metodo if "E11_redondeo" in modulos and modulos["E11_redondeo"].metodo else "cercano",
            cartera_activa=activo("E13_cartera", default=False),
            cartera_factor_min=float(p("E13_cartera", "min", 0.85)),
            cartera_factor_max=float(p("E13_cartera", "max", 1.15)),
            cumplimiento_activo=activo("E15_cumplimiento", default=False),
            cumplimiento_peso=float(p("E15_cumplimiento", "peso", 0.2)),
            volatilidad_activa=activo("E16_volatilidad", default=False),
            volatilidad_umbral_cv=float(p("E16_volatilidad", "umbral_cv", 0.40)),
            volatilidad_factor_reduccion=float(p("E16_volatilidad", "factor_reduccion", 0.5)),
            config_snapshot=snapshot,
        )
        return motor_parametros, pipeline
