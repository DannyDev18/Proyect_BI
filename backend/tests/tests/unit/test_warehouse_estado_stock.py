# backend/tests/unit/test_warehouse_estado_stock.py
"""Fase 6.1 (H-2/RN-B11, docs/features/plan_correcciones_integrales_sistema.md):
un artículo con stock > 0 y CERO salidas caía en "Seguro" (el peor caso de sobre-stock
posible, nunca detectado) porque `_dias_inventario` devuelve `None` sin salidas y la
rama de "Exceso" es matemáticamente inalcanzable con `dias_inv=None`. `_enriquecer_
producto` es una función pura (no toca repos/BD) -- se testea con `WarehouseService`
instanciado con mocks vacíos, mismo patrón que test_warehouse_prediccion_compras.py."""
from unittest.mock import MagicMock

from app.services.warehouse_service import (
    ESTADO_EXCESO, ESTADO_INMOVILIZADO, ESTADO_SEGURO, WarehouseService,
)


def _service() -> WarehouseService:
    return WarehouseService(MagicMock(), MagicMock(), MagicMock())


def _row(**overrides) -> dict:
    base = {
        "codart": "ART-1", "nombre": "Producto de prueba", "categoria": "GEN",
        "stock_actual": 100.0, "valor_inventario": 500.0, "costo_unitario": 5.0,
        "punto_reorden_config": 0.0, "salidas_periodo": 0.0, "salidas_periodo_anterior": 0.0,
    }
    base.update(overrides)
    # La ventana de 90 días es un superconjunto de la de 30 (misma garantía que el SQL
    # real: FILTER con un rango más amplio nunca puede ser menor) -- por defecto igual a
    # `salidas_periodo` salvo que el test la override explícitamente.
    base.setdefault("salidas_ventana_inmovilizado", base["salidas_periodo"])
    return base


def test_stock_sin_salidas_es_inmovilizado_no_seguro():
    """Caso H-2 (Consignación Verónica Sánchez): stock > 0, 0 uds/día -- antes caía en
    "Seguro" y el reporte de exceso jamás lo mostraba."""
    resultado = _service()._enriquecer_producto(_row())
    assert resultado["estado"] == ESTADO_INMOVILIZADO
    assert resultado["estado"] != ESTADO_SEGURO


def test_stock_sin_salidas_recientes_pero_con_ventana_amplia_no_es_inmovilizado():
    """Si SÍ hubo salidas dentro de la ventana de 90 días (aunque no en los últimos 30),
    no debe marcarse Inmovilizado -- evita falsos positivos por estacionalidad."""
    resultado = _service()._enriquecer_producto(
        _row(salidas_periodo=0.0, salidas_ventana_inmovilizado=12.0)
    )
    assert resultado["estado"] != ESTADO_INMOVILIZADO


def test_stock_cero_sin_salidas_no_es_inmovilizado():
    """Inmovilizado exige stock > 0 -- un artículo agotado sin salidas no es "capital
    parado", es simplemente un artículo sin stock ni movimiento."""
    resultado = _service()._enriquecer_producto(_row(stock_actual=0.0, valor_inventario=0.0))
    assert resultado["estado"] != ESTADO_INMOVILIZADO


def test_exceso_sigue_funcionando_con_salidas_bajas_pero_no_nulas():
    """Un artículo que SÍ vende, solo que muy lento (dias_inventario > BODEGA_DIAS_EXCESO),
    sigue clasificando como "Exceso", no "Inmovilizado" -- son estados distintos a propósito."""
    resultado = _service()._enriquecer_producto(
        _row(stock_actual=1000.0, salidas_periodo=1.0, salidas_ventana_inmovilizado=3.0)
    )
    assert resultado["estado"] == ESTADO_EXCESO


def test_dias_inventario_baja_confianza_marca_salida_marginal():
    """Caso "El Rey": salida_diaria muy baja pero no cero -- "0 días de stock" no debe
    leerse como la misma urgencia que un artículo de alta rotación."""
    resultado = _service()._enriquecer_producto(_row(stock_actual=1.0, salidas_periodo=3.0))  # 0.1 uds/día
    assert resultado["dias_inventario_baja_confianza"] is True


def test_dias_inventario_baja_confianza_falso_con_salida_alta():
    resultado = _service()._enriquecer_producto(_row(stock_actual=100.0, salidas_periodo=300.0))  # 10 uds/día
    assert resultado["dias_inventario_baja_confianza"] is False
