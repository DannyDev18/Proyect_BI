# backend/tests/unit/test_replenishment_service.py
"""F5 (docs/features/plan_reabastecimiento_inteligente.md §6.4): `get_explicacion` debe
devolver exactamente la fila que la lista completa produciría para ese `codart` (misma
clasificación ABC, calculada sobre TODO el catálogo filtrado) -- nunca recalculada en
aislamiento, que le daría una clase distinta."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.inventory.service import ReplenishmentService


def _producto(codart, valor_consumo, stock_actual=10.0, meses_con_venta=12, unidades_mensuales=None):
    return {
        "codart": codart,
        "nombre": f"Producto {codart}",
        "categoria": "CAT1",
        "stock_actual": stock_actual,
        "costo_unitario": 5.0,
        "valor_consumo": valor_consumo,
        "meses_con_venta": meses_con_venta,
        "unidades_mensuales": unidades_mensuales or [10.0] * meses_con_venta,
    }


@pytest.fixture
def service():
    warehouse_repo = MagicMock()
    config_repo = MagicMock()
    config_repo.get_niveles_servicio.return_value = {"A": 0.975, "B": 0.95, "C": 0.90}
    config_repo.get_lead_times_resolucion.return_value = {"producto": {}, "categoria": {}, "proveedor": {}}
    proposal_repo = MagicMock()
    svc = ReplenishmentService(warehouse_repo, config_repo, proposal_repo)
    return svc, warehouse_repo


def test_get_explicacion_devuelve_la_fila_del_codart_pedido(service):
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [
        _producto("A1", valor_consumo=100000.0),
        _producto("B1", valor_consumo=100.0),
    ]

    fila = svc.get_explicacion("B1")

    assert fila["codart"] == "B1"
    assert fila["nombre"] == "Producto B1"


def test_get_explicacion_codart_inexistente_lanza_not_found(service):
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [_producto("A1", valor_consumo=100000.0)]

    with pytest.raises(NotFoundError):
        svc.get_explicacion("NO-EXISTE")


def test_get_explicacion_no_propaga_post_filtros_de_riesgo_o_clasificacion(service):
    """Aunque el llamador pase `riesgo`/`clase_abc` (parámetros válidos de la lista),
    `get_explicacion` los ignora -- filtrarlos podría excluir el propio artículo pedido
    de la lista intermedia antes de encontrarlo."""
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [_producto("A1", valor_consumo=100000.0)]

    fila = svc.get_explicacion("A1", riesgo="critico", clase_abc="C", solo_criticos=True)

    assert fila["codart"] == "A1"


def test_simular_no_modifica_la_configuracion_persistida(service):
    """F8: `simular` nunca debe llamar a ningún método de escritura del repositorio de
    configuración -- es de solo lectura por diseño."""
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [_producto("A1", valor_consumo=1000.0)]

    svc.simular(niveles_servicio={"A": 0.99, "B": 0.95, "C": 0.85}, lead_time_default_dias=15)

    config_repo = svc.config_repo
    config_repo.update_politica.assert_not_called()
    config_repo.upsert_lead_time.assert_not_called()
    config_repo.delete_lead_time.assert_not_called()


def test_simular_con_lead_time_mayor_reduce_o_iguala_la_cobertura_relativa_al_reorden(service):
    """Un lead time mayor exige más stock de seguridad -> el punto de reorden sube ->
    con el mismo stock actual, más artículos caen en riesgo (el resumen simulado nunca
    debería mostrar MENOS riesgo que el actual con un lead time mayor)."""
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [
        _producto(f"P{i}", valor_consumo=1000.0, stock_actual=50.0, meses_con_venta=12,
                   unidades_mensuales=[30.0] * 12)
        for i in range(5)
    ]

    resultado = svc.simular(lead_time_default_dias=60)

    assert resultado["resumen_simulado"]["productos_riesgo_critico"] >= resultado["resumen_actual"]["productos_riesgo_critico"]
    assert resultado["parametros_simulados"]["lead_time_default_dias"] == 60


def test_get_alertas_detecta_cambio_brusco_y_tendencia_decreciente(service):
    """F7 (§7.4): un artículo con un pico reciente muy por encima de su media histórica
    y otro con caída sostenida de 3 meses deben aparecer en `get_alertas`; uno estable
    no debe generar ninguna alerta."""
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [
        _producto("PICO", valor_consumo=100.0, meses_con_venta=6, unidades_mensuales=[10, 10, 10, 10, 10, 200]),
        _producto("BAJA", valor_consumo=100.0, meses_con_venta=6, unidades_mensuales=[10, 10, 10, 30, 20, 10]),
        _producto("ESTABLE", valor_consumo=100.0, meses_con_venta=6, unidades_mensuales=[10, 11, 9, 10, 10, 10]),
    ]

    alertas = svc.get_alertas()

    codarts_cambio = {a["codart"] for a in alertas if a["tipo"] == "cambio_brusco_demanda"}
    codarts_tendencia = {a["codart"] for a in alertas if a["tipo"] == "tendencia_decreciente"}
    assert "PICO" in codarts_cambio
    assert "BAJA" in codarts_tendencia
    assert "ESTABLE" not in codarts_cambio
    assert "ESTABLE" not in codarts_tendencia


def test_get_alertas_respeta_el_limite_por_tipo(service):
    svc, warehouse_repo = service
    productos = [
        _producto(f"P{i}", valor_consumo=100.0, meses_con_venta=6, unidades_mensuales=[10, 10, 10, 10, 10, 200])
        for i in range(10)
    ]
    warehouse_repo.get_metricas_reabastecimiento.return_value = productos

    alertas = svc.get_alertas(limite_por_tipo=3)

    assert len([a for a in alertas if a["tipo"] == "cambio_brusco_demanda"]) == 3


def test_get_explicacion_misma_clase_abc_que_la_lista_completa(service):
    """La clase ABC de B1 depende de TODO el catálogo (curva de Pareto) -- debe
    coincidir con la que produce `get_lista_reabastecimiento`, no una calculada en
    aislamiento con B1 como único artículo (que lo volvería clase A trivialmente)."""
    svc, warehouse_repo = service
    productos = [_producto("A1", valor_consumo=100000.0), _producto("B1", valor_consumo=100.0)]
    warehouse_repo.get_metricas_reabastecimiento.return_value = productos

    lista = svc.get_lista_reabastecimiento()
    fila_b1_en_lista = next(f for f in lista if f["codart"] == "B1")

    fila_explicacion = svc.get_explicacion("B1")

    assert fila_explicacion["clase_abc"] == fila_b1_en_lista["clase_abc"]


# ── F9: propuestas de compra persistidas ──────────────────────────────────────────
def test_crear_propuesta_solo_incluye_lineas_con_cantidad_sugerida_positiva(service):
    svc, warehouse_repo = service
    warehouse_repo.get_metricas_reabastecimiento.return_value = [
        _producto("CRITICO", valor_consumo=1000.0, stock_actual=0.0, meses_con_venta=12, unidades_mensuales=[30.0] * 12),
        _producto("SOBRADO", valor_consumo=1000.0, stock_actual=100000.0, meses_con_venta=12, unidades_mensuales=[1.0] * 12),
    ]
    proposal_repo = svc.proposal_repo
    proposal_repo.crear.return_value = "PROPUESTA_CREADA"

    resultado = svc.crear_propuesta(usuario_id=7, horizonte_dias=30)

    assert resultado == "PROPUESTA_CREADA"
    proposal_repo.crear.assert_called_once()
    _, args, kwargs = proposal_repo.crear.mock_calls[0]
    usuario_id, filtros_origen, horizonte, lineas = args
    assert usuario_id == 7
    assert horizonte == 30
    codarts = {line["codart"] for line in lineas}
    assert "CRITICO" in codarts
    assert "SOBRADO" not in codarts


def test_decidir_propuesta_aprobar_transiciona_desde_borrador(service):
    svc, _ = service
    propuesta = MagicMock(estado="borrador")
    svc.proposal_repo.get.return_value = propuesta
    svc.proposal_repo.actualizar_estado.return_value = MagicMock(estado="aprobada")

    resultado = svc.decidir_propuesta(1, "aprobar")

    svc.proposal_repo.actualizar_estado.assert_called_once_with(1, "aprobada")
    assert resultado.estado == "aprobada"


def test_decidir_propuesta_ya_decidida_lanza_error(service):
    svc, _ = service
    propuesta = MagicMock(estado="aprobada")
    svc.proposal_repo.get.return_value = propuesta

    with pytest.raises(ValidationError):
        svc.decidir_propuesta(1, "rechazar")

    svc.proposal_repo.actualizar_estado.assert_not_called()


def test_decidir_propuesta_accion_invalida_lanza_error(service):
    svc, _ = service
    with pytest.raises(ValidationError):
        svc.decidir_propuesta(1, "no-es-una-accion-valida")


def test_decidir_propuesta_inexistente_lanza_not_found(service):
    svc, _ = service
    svc.proposal_repo.get.return_value = None

    with pytest.raises(NotFoundError):
        svc.decidir_propuesta(999, "aprobar")


# ── D-6 (auditoría 52, Fase 4 de docs/features/plan_modulo_inventario_reabastecimiento
# .md): memoización de la evaluación completa del catálogo dentro de la misma instancia
# de servicio -- guarda de rendimiento, mismo patrón que los tests de `call_count == 1`
# de `test_commission_simulation_service.py`. ───────────────────────────────────────────
class TestMemoizacionCatalogo:
    def test_resumen_y_alertas_con_los_mismos_filtros_comparten_una_sola_evaluacion(self, service):
        svc, warehouse_repo = service
        warehouse_repo.get_metricas_reabastecimiento.return_value = [
            _producto("A1", valor_consumo=100000.0),
            _producto("B1", valor_consumo=100.0),
        ]

        svc.get_resumen()
        svc.get_alertas()
        svc.get_explicacion("A1")

        assert warehouse_repo.get_metricas_reabastecimiento.call_count == 1

    def test_filtros_distintos_no_comparten_cache(self, service):
        svc, warehouse_repo = service
        warehouse_repo.get_metricas_reabastecimiento.return_value = [_producto("A1", valor_consumo=100000.0)]

        svc.get_resumen(almacen="01")
        svc.get_resumen(almacen="02")

        assert warehouse_repo.get_metricas_reabastecimiento.call_count == 2

    def test_simular_recalcula_exactamente_dos_veces_actual_y_simulado(self, service):
        """Irreducible por diseño (§4 del plan): son dos cálculos distintos (config
        real vigente vs. hipotética del simulador), no una repetición redundante."""
        svc, warehouse_repo = service
        warehouse_repo.get_metricas_reabastecimiento.return_value = [_producto("A1", valor_consumo=100000.0)]

        svc.simular(niveles_servicio={"A": 0.99, "B": 0.97, "C": 0.95}, lead_time_default_dias=10)

        assert warehouse_repo.get_metricas_reabastecimiento.call_count == 2

    def test_post_filtros_no_mutan_la_lista_cacheada(self, service):
        """`get_lista_reabastecimiento` con `solo_criticos=True` no debe alterar lo que
        una llamada posterior sin filtros ve -- ambas comparten la misma evaluación
        cacheada por `_evaluar_catalogo`."""
        svc, warehouse_repo = service
        warehouse_repo.get_metricas_reabastecimiento.return_value = [
            _producto("A1", valor_consumo=100000.0, stock_actual=0.0),  # crítico
            _producto("B1", valor_consumo=100.0, stock_actual=999.0, meses_con_venta=0, unidades_mensuales=[]),
        ]

        filtrada = svc.get_lista_reabastecimiento(solo_criticos=True)
        completa = svc.get_lista_reabastecimiento()

        assert len(filtrada) <= len(completa)
        assert len(completa) == 2
        assert warehouse_repo.get_metricas_reabastecimiento.call_count == 1
