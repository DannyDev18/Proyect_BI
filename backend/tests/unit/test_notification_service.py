# backend/tests/unit/test_notification_service.py
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.schemas.pagination import PaginationParams
from app.services.notification_service import NotificationService


def _user(
    rol: str, user_id: int = 1, sucursal: str | None = None, codalm: str | None = None,
    id_vendedor_origen: str | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.sucursal = sucursal
    user.codalm = codalm
    user.id_vendedor_origen = id_vendedor_origen
    user.role = MagicMock()
    user.role.nombre = rol
    return user


@pytest.fixture
def notification_repo():
    repo = MagicMock()
    repo.get_activas_por_rol.return_value = []
    return repo


@pytest.fixture
def warehouse_service():
    ws = MagicMock()
    ws.get_notificaciones.return_value = []
    ws.model_loader.keys.return_value = ["sales_rf", "demand_rf"]
    ws.model_loader.is_loaded.return_value = True
    return ws


@pytest.fixture
def prediction_service():
    ps = MagicMock()
    ps.get_sales_forecast.return_value = {"metricas": {"crecimiento_esperado": 0.0}}
    return ps


@pytest.fixture
def cartera360_service():
    cs = MagicMock()
    cs.get_lista_trabajo.return_value = []
    return cs


@pytest.fixture
def service(notification_repo, warehouse_service, prediction_service, cartera360_service):
    return NotificationService(notification_repo, warehouse_service, prediction_service, cartera360_service)


# ── Generador calculado: bodega ──────────────────────────────────────────────
def test_get_notificaciones_bodega_mapea_formato_unificado(service, warehouse_service):
    warehouse_service.get_notificaciones.return_value = [
        {"tipo": "stock_critico", "prioridad": "alta", "mensaje": "⚠️ crítico", "codart": "A1", "accion_url": "/bodega/stock-reorden"},
    ]

    resultado = service.get_notificaciones(_user("bodega", codalm="ALM01"))

    assert len(resultado) == 1
    assert resultado[0].tipo_evento == "stock_critico"
    assert resultado[0].titulo == "Stock crítico"
    assert resultado[0].accion_url == "/bodega/stock-reorden"
    assert resultado[0].persistida is False
    assert resultado[0].leida is False


def test_get_notificaciones_bodega_generador_caido_no_tumba_la_campana(service, warehouse_service, notification_repo):
    warehouse_service.get_notificaciones.side_effect = RuntimeError("EDW caído")
    notification_repo.get_activas_por_rol.return_value = []

    resultado = service.get_notificaciones(_user("bodega"))

    assert resultado == []  # RN-N4: degradación con gracia, no propaga la excepción


# ── Generador calculado: administrador (salud de modelos) ───────────────────
def test_get_notificaciones_admin_sin_faltantes_no_genera_alerta(service, warehouse_service):
    resultado = service.get_notificaciones(_user("administrador"))
    assert resultado == []


def test_get_notificaciones_admin_reporta_modelos_no_cargados(service, warehouse_service):
    warehouse_service.model_loader.is_loaded.side_effect = lambda key: key != "demand_rf"

    resultado = service.get_notificaciones(_user("administrador"))

    assert len(resultado) == 1
    assert resultado[0].tipo_evento == "modelo_no_cargado"
    assert "demand_rf" in resultado[0].mensaje
    assert resultado[0].prioridad == "alta"


def test_get_notificaciones_rol_desconocido_sin_generador_calculado(service, warehouse_service):
    resultado = service.get_notificaciones(_user("rol_inexistente"))
    assert resultado == []
    warehouse_service.get_notificaciones.assert_not_called()


# ── Generador calculado: gerencia (desvío del forecast) ──────────────────────
def test_get_notificaciones_gerencia_sin_desvio_no_alerta(service, prediction_service):
    prediction_service.get_sales_forecast.return_value = {"metricas": {"crecimiento_esperado": 5.0}}
    resultado = service.get_notificaciones(_user("gerencia"))
    assert resultado == []


def test_get_notificaciones_gerencia_reporta_desvio_alto(service, prediction_service):
    prediction_service.get_sales_forecast.return_value = {"metricas": {"crecimiento_esperado": 45.0}}
    resultado = service.get_notificaciones(_user("gerencia"))
    assert len(resultado) == 1
    assert resultado[0].tipo_evento == "desvio_forecast"
    assert resultado[0].prioridad == "alta"
    assert "por encima" in resultado[0].mensaje


def test_get_notificaciones_gerencia_reporta_caida(service, prediction_service):
    prediction_service.get_sales_forecast.return_value = {"metricas": {"crecimiento_esperado": -25.0}}
    resultado = service.get_notificaciones(_user("gerencia"))
    assert len(resultado) == 1
    assert "por debajo" in resultado[0].mensaje


# ── Generador calculado: ventas (churn alto, RLS por vendedor) ───────────────
def test_get_notificaciones_ventas_sin_vendedor_origen_no_consulta_cartera(service, cartera360_service):
    resultado = service.get_notificaciones(_user("ventas", id_vendedor_origen=None))
    assert resultado == []
    cartera360_service.get_lista_trabajo.assert_not_called()


def test_get_notificaciones_ventas_filtra_por_umbral_de_churn(service, cartera360_service):
    cartera360_service.get_lista_trabajo.return_value = [
        {"cliente_id": "C1", "probabilidad_abandono": 85.0},
        {"cliente_id": "C2", "probabilidad_abandono": 10.0},
    ]
    resultado = service.get_notificaciones(_user("ventas", id_vendedor_origen="VEN01"))
    assert len(resultado) == 1
    assert "C1" in resultado[0].mensaje
    cartera360_service.get_lista_trabajo.assert_called_once_with("VEN01")


# ── Emisión persistida y dedupe (RN-N2) ──────────────────────────────────────
def test_emitir_descarta_duplicado_reciente(service, notification_repo):
    notification_repo.existe_duplicado_reciente.return_value = True

    resultado = service.emitir("metas_generadas", "gerencia", "Metas generadas", "Hay metas nuevas")

    assert resultado is None
    notification_repo.crear.assert_not_called()


def test_emitir_crea_cuando_no_hay_duplicado(service, notification_repo):
    notification_repo.existe_duplicado_reciente.return_value = False
    notification_repo.crear.return_value = MagicMock()

    resultado = service.emitir("metas_generadas", "gerencia", "Metas generadas", "Hay metas nuevas", prioridad="alta")

    assert resultado is not None
    notification_repo.crear.assert_called_once()


def test_emitir_degrada_con_gracia_si_el_repo_falla(service, notification_repo):
    notification_repo.existe_duplicado_reciente.side_effect = RuntimeError("db caída")
    resultado = service.emitir("metas_generadas", "gerencia", "t", "m")
    assert resultado is None


# ── Estado de lectura (RN-N3) ────────────────────────────────────────────────
def test_marcar_leida_lanza_notfound_si_no_existe(service, notification_repo):
    notification_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        service.marcar_leida(_user("gerencia"), 999)


def test_marcar_leida_lanza_permission_denied_fuera_de_alcance(service, notification_repo):
    notif = MagicMock(rol_destino="ventas", usuario_id=None)
    notification_repo.get_by_id.return_value = notif
    with pytest.raises(PermissionDeniedError):
        service.marcar_leida(_user("gerencia"), 1)


def test_marcar_leida_permite_notificacion_de_todo_el_rol(service, notification_repo):
    notif = MagicMock(rol_destino="gerencia", usuario_id=None)
    notification_repo.get_by_id.return_value = notif
    notification_repo.marcar_leida.return_value = notif

    service.marcar_leida(_user("gerencia", user_id=5), 1)

    notification_repo.marcar_leida.assert_called_once_with(notif, 5)


def test_marcar_todas_delega_al_repo_con_rol_y_usuario(service, notification_repo):
    notification_repo.marcar_todas_leidas.return_value = 3
    resultado = service.marcar_todas(_user("ventas", user_id=7))
    assert resultado == 3
    notification_repo.marcar_todas_leidas.assert_called_once_with("ventas", 7)


# ── Historial paginado ────────────────────────────────────────────────────────
def test_get_historial_pagina_los_resultados_del_repo(service, notification_repo):
    persistida = MagicMock(id=1, tipo_evento="x", titulo="t", mensaje="m", accion_url=None,
                            prioridad="media", fecha_creacion=None, leida_por=[])
    notification_repo.get_historial_por_rol.return_value = [persistida]

    page = service.get_historial(_user("gerencia", user_id=1), PaginationParams(page=1, page_size=25))

    assert page.total == 1
    assert page.items[0].persistida is True
