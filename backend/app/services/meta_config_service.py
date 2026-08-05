# backend/app/services/meta_config_service.py
"""Servicio de configuración editable del motor de metas v2
(docs/features/plan_motor_metas_configurable.md §5.5). Valida rangos razonables antes
de escribir -- el gerente edita PARÁMETROS de una fórmula fija, y esos parámetros deben
mantenerse dentro de límites que no rompan la banda de alcanzabilidad ni el propósito de
cada uno (ej. nada de `banda_alcanzabilidad_max = 5.0`, que anularía el guardarraíl que
esta misma fase introduce)."""
from app.core.exceptions import ValidationError
from app.models.meta_config import MetaConfigParametro
from app.repositories.meta_config_repository import MetaConfigRepository
from app.services.goal_calculation_engine import DEFAULT_PARAMETROS, MetaMotorParametros

# Rango [mínimo, máximo] aceptado por clave -- evita que un valor fuera de sentido común
# (tipeo, o un intento de desactivar el guardarraíl) se guarde sin control.
RANGOS_VALIDOS: dict[str, tuple[float, float]] = {
    "ventana_meses": (6, 60),
    "ventana_referencia_outliers": (4, 36),
    "iqr_multiplicador": (0.5, 3.0),
    "min_anios_estacional": (1, 5),
    "meses_tendencia_reciente": (2, 12),
    "factor_tendencia_min": (0.5, 1.0),
    "factor_tendencia_max": (1.0, 2.0),
    "cv_alto": (0.1, 2.0),
    "peso_estabilidad_min": (0.0, 1.0),
    "banda_alcanzabilidad_min": (0.5, 1.0),
    "banda_alcanzabilidad_max": (1.0, 2.0),
    "meses_referencia_alcanzable": (2, 24),
    "meses_minimos_para_iqr": (2, 12),
}


class MetaConfigService:
    def __init__(self, repo: MetaConfigRepository):
        self.repo = repo

    def get_parametros_configurables(self) -> list[MetaConfigParametro]:
        return self.repo.get_all()

    def get_motor_parametros(self) -> MetaMotorParametros:
        """Construye `MetaMotorParametros` a partir de la configuración persistida --
        cualquier clave ausente cae al default de la dataclass (entorno sin la semilla
        aplicada, o una clave nueva agregada después de esta versión)."""
        valores = self.repo.get_valores()
        campos = {}
        for campo in DEFAULT_PARAMETROS.__dataclass_fields__:
            if campo in valores:
                bruto = valores[campo]
                tipo = type(getattr(DEFAULT_PARAMETROS, campo))
                campos[campo] = tipo(bruto)
        return MetaMotorParametros(**campos)

    def update_parametro(self, clave: str, valor: float, usuario_id: int | None) -> MetaConfigParametro:
        if clave not in RANGOS_VALIDOS:
            raise ValidationError(f"Parámetro de configuración de metas desconocido: {clave}")
        minimo, maximo = RANGOS_VALIDOS[clave]
        if not (minimo <= valor <= maximo):
            raise ValidationError(
                f"El valor de '{clave}' debe estar entre {minimo} y {maximo} (recibido: {valor})."
            )
        try:
            return self.repo.update_valor(clave, valor, usuario_id)
        except ValueError as e:
            raise ValidationError(str(e)) from e

    def get_auditoria(self, limit: int = 100):
        return self.repo.get_auditoria(limit=limit)
