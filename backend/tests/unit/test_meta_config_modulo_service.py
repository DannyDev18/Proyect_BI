# backend/tests/unit/test_meta_config_modulo_service.py
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.services.goal_pipeline_stages import ETAPAS_CATALOGO
from app.services.meta_config_modulo_service import RANGOS_PARAMETROS, MetaConfigModuloService


def _modulo(etapa, metodo, activo, parametros):
    m = MagicMock()
    m.etapa, m.metodo, m.activo, m.parametros = etapa, metodo, activo, parametros
    return m


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return MetaConfigModuloService(repo)


def test_update_modulo_etapa_desconocida_lanza_validation_error(service):
    with pytest.raises(ValidationError):
        service.update_modulo("E99_inexistente", "algo", True, {}, usuario_id=1)


def test_update_modulo_metodo_no_implementado_lanza_validation_error(service):
    with pytest.raises(ValidationError):
        service.update_modulo("E1_limpieza", "isolation_forest", True, {}, usuario_id=1)


def test_update_modulo_desactivar_no_exige_metodo_implementado(service, repo):
    """Desactivar una etapa nunca debe fallar por el método -- solo se valida la
    implementación cuando se intenta ACTIVAR."""
    repo.update_modulo.return_value = _modulo("E9_capacidad", None, False, {})
    service.update_modulo("E9_capacidad", None, False, {}, usuario_id=1)
    repo.update_modulo.assert_called_once()


def test_update_modulo_parametro_fuera_de_rango_lanza_validation_error(service):
    with pytest.raises(ValidationError):
        service.update_modulo("E10_restricciones", "banda", True, {"banda_alcanzabilidad_max": 5.0}, usuario_id=1)


def test_update_modulo_valido_delega_en_el_repo(service, repo):
    repo.update_modulo.return_value = _modulo("E1_limpieza", "tukey", True, {"k": 1.5})
    resultado = service.update_modulo("E1_limpieza", "tukey", True, {"k": 1.5}, usuario_id=1)
    assert resultado.metodo == "tukey"
    repo.update_modulo.assert_called_once_with("E1_limpieza", "tukey", True, {"k": 1.5}, 1)


def test_rangos_de_validacion_coinciden_con_el_esquema_del_formulario_dinamico():
    """`RANGOS_PARAMETROS` (autoridad de VALIDACIÓN del backend) y `ETAPAS_CATALOGO[...
    ]["parametros"]` (autoridad de PRESENTACIÓN del formulario dinámico del frontend)
    deben describir el mismo rango para cada clave -- si divergen, el formulario permite
    un valor que el backend luego rechaza (o viceversa)."""
    for info in ETAPAS_CATALOGO.values():
        for parametro in info["parametros"]:
            rango = RANGOS_PARAMETROS.get(parametro["clave"])
            assert rango is not None, f"'{parametro['clave']}' sin rango de validación en RANGOS_PARAMETROS"
            assert rango == (parametro["min"], parametro["max"]), (
                f"'{parametro['clave']}': RANGOS_PARAMETROS={rango} != catálogo=({parametro['min']}, {parametro['max']})"
            )


def test_get_pipeline_config_con_repo_vacio_usa_defaults_seguros(service, repo):
    """Sin ninguna fila (entorno sin la migración `0014` aplicada), el pipeline debe
    degradar a los defaults del motor v2 -- nunca romper la generación de metas."""
    repo.get_all.return_value = []
    motor_parametros, pipeline = service.get_pipeline_config()
    assert motor_parametros.iqr_multiplicador == pytest.approx(1.5)
    assert pipeline.aplicar_banda is True
    assert pipeline.estrategia_activa is False
    assert pipeline.capacidad_activa is False


def test_get_pipeline_config_mapea_valores_configurados(service, repo):
    repo.get_all.return_value = [
        _modulo("E1_limpieza", "tukey", True, {"k": 2.0, "ventana_referencia": 6, "meses_minimos_para_iqr": 3}),
        _modulo("E6_madurez", "mezcla_gradual", True, {"umbral_nuevo_meses": 3, "umbral_maduro_meses": 12, "peso_benchmark_intermedio": 0.5}),
        _modulo("E7_estrategia", "crecimiento_pct", True, {"crecimiento_pct": 5.0}),
        _modulo("E8_tipo_vendedor", "tabla", True, {"externo": 1.20, "interno": 0.90}),
        _modulo("E11_redondeo", "arriba", True, {"multiplo": 500}),
    ]
    motor_parametros, pipeline = service.get_pipeline_config()

    assert motor_parametros.iqr_multiplicador == pytest.approx(2.0)
    assert motor_parametros.ventana_referencia_outliers == 6
    assert pipeline.umbral_nuevo_meses == 3
    assert pipeline.peso_propio_intermedio == pytest.approx(0.5)  # 1 - 0.5
    assert pipeline.estrategia_activa is True
    assert pipeline.crecimiento_pct == pytest.approx(5.0)
    assert pipeline.factores_tipo_vendedor == {"externo": 1.20, "interno": 0.90}
    assert pipeline.redondeo_multiplo == 500
    assert pipeline.redondeo_modo == "arriba"
    assert pipeline.config_snapshot["E1_limpieza"]["metodo"] == "tukey"
