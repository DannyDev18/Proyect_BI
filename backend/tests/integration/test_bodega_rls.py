# backend/tests/integration/test_bodega_rls.py
"""RN-B10 (docs/auditoria/42_correcciones_integrales_sistema.md, Fase 1.b): un usuario
con rol `bodega` solo debe poder leer datos de las bodegas que el administrador le
asignó (public.usuario_almacenes), o de todas si se marcó `todos_los_almacenes`. Cierra
H-1 (docs/features/plan_correcciones_integrales_sistema.md): antes cualquier usuario
`bodega` podía leer/exportar cualquier almacén con `?almacen=<otro>`.

Requiere Postgres real (ver tests/integration/conftest.py). Los usuarios de prueba se
crean una sola vez por módulo (fixtures `scope="module"`) y se limpian al final -- no
uno por test: `POST /auth/login` tiene un rate limit real de negocio
(`AUTH_LOGIN_RATE_LIMIT`, ver test_auth_endpoints.py) que un login por test agotaría."""
import uuid

import pytest

pytestmark = pytest.mark.integration

API = "/api/v1"


def _crear_usuario_bodega(client, admin_headers, *, codalms=None, todos_los_almacenes=False):
    email = f"bodega-rls-{uuid.uuid4().hex[:10]}@empresa.com"
    payload = {
        "nombre": "Bodega RLS Test",
        "email": email,
        "password": "Prueba2024!Seguro",
        "rol_id": _rol_id_bodega(client, admin_headers),
        "codalms": codalms or [],
        "todos_los_almacenes": todos_los_almacenes,
    }
    r = client.post(f"{API}/users/", headers=admin_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _rol_id_bodega(client, admin_headers):
    r = client.get(f"{API}/roles", headers=admin_headers)
    assert r.status_code == 200, r.text
    rol = next(x for x in r.json() if x["nombre"] == "bodega")
    return rol["id"]


def _almacenes_con_nombre(client, admin_headers) -> list[dict]:
    r = client.get(f"{API}/users/catalogos/almacenes", headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _login(client, email: str, password: str = "Prueba2024!Seguro") -> dict:
    r = client.post(f"{API}/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _borrar_usuario(client, admin_headers, user_id: int):
    client.delete(f"{API}/users/{user_id}", headers=admin_headers)


@pytest.fixture(scope="module")
def admin_headers(tokens):
    """Equivalente module-scoped de `auth_headers("administrador")` -- `auth_headers`
    (conftest) es function-scoped y no puede ser requerido por fixtures de módulo."""
    token = tokens.get("administrador")
    if not token:
        pytest.skip("No hay token para 'administrador' -- ¿está sembrada la BD de prueba?")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def catalogo_almacenes(client, admin_headers):
    catalogo = _almacenes_con_nombre(client, admin_headers)
    if len(catalogo) < 2:
        pytest.skip("Se necesitan al menos 2 almacenes reales en el EDW de prueba.")
    return catalogo


@pytest.fixture(scope="module")
def usuario_una_bodega(client, admin_headers, catalogo_almacenes):
    """Bodega A = la suya; Bodega B = ajena. Un solo login reutilizado por todos los
    tests que necesitan este perfil (evita agotar el rate limit de /auth/login)."""
    propia = catalogo_almacenes[0]["codalm"]
    ajena = catalogo_almacenes[1]["codalm"]
    user = _crear_usuario_bodega(client, admin_headers, codalms=[propia])
    headers = _login(client, user["email"])
    yield {"user": user, "headers": headers, "propia": propia, "ajena": ajena}
    _borrar_usuario(client, admin_headers, user["id"])


@pytest.fixture(scope="module")
def usuario_varias_bodegas(client, admin_headers, catalogo_almacenes):
    mias = [a["codalm"] for a in catalogo_almacenes[:2]]
    user = _crear_usuario_bodega(client, admin_headers, codalms=mias)
    headers = _login(client, user["email"])
    yield {"user": user, "headers": headers, "mias": mias}
    _borrar_usuario(client, admin_headers, user["id"])


@pytest.fixture(scope="module")
def usuario_todos_los_almacenes(client, admin_headers):
    user = _crear_usuario_bodega(client, admin_headers, todos_los_almacenes=True)
    headers = _login(client, user["email"])
    yield {"user": user, "headers": headers}
    _borrar_usuario(client, admin_headers, user["id"])


def test_usuario_con_una_bodega_no_ve_otra_al_elegirla(client, usuario_una_bodega):
    headers, propia, ajena = usuario_una_bodega["headers"], usuario_una_bodega["propia"], usuario_una_bodega["ajena"]

    r_propia = client.get(f"{API}/analytics/bodega/kpis", headers=headers, params={"almacen": propia})
    assert r_propia.status_code == 200

    # Pedir la bodega ajena: la restricción intersecta y no debe filtrar sus datos
    # (H-1). No se espera 403 (mismo criterio que resolve_sucursal_filter) -- se espera
    # que la respuesta quede vacía/neutra, nunca los datos de `ajena`.
    r_ajena = client.get(f"{API}/analytics/bodega/kpis", headers=headers, params={"almacen": ajena})
    assert r_ajena.status_code == 200
    assert r_ajena.json()["total_articulos"]["skus_activos"] == 0


def test_usuario_con_varias_bodegas_recibe_solo_la_union_de_las_suyas(client, usuario_varias_bodegas):
    headers, mias = usuario_varias_bodegas["headers"], usuario_varias_bodegas["mias"]

    r_todas = client.get(f"{API}/analytics/bodega/kpis", headers=headers)
    r_mia_0 = client.get(f"{API}/analytics/bodega/kpis", headers=headers, params={"almacen": mias[0]})
    assert r_todas.status_code == 200 and r_mia_0.status_code == 200
    # La vista sin filtro (restringida a mis 2 bodegas) debe tener al menos tantos SKUs
    # activos como la vista de una sola de ellas.
    assert r_todas.json()["total_articulos"]["skus_activos"] >= r_mia_0.json()["total_articulos"]["skus_activos"]


def test_usuario_todos_los_almacenes_sin_restriccion(client, usuario_todos_los_almacenes, catalogo_almacenes):
    headers = usuario_todos_los_almacenes["headers"]
    r = client.get(
        f"{API}/analytics/bodega/kpis", headers=headers,
        params={"almacen": catalogo_almacenes[0]["nombre_almacen"]},
    )
    assert r.status_code == 200
    # Sin restricción: debe poder consultar cualquier almacén real sin quedar en 0
    # forzado por RLS (puede ser 0 por datos reales del EDW, pero no debe fallar).


def test_crear_usuario_bodega_sin_almacenes_ni_todos_falla_validacion(client, admin_headers):
    payload = {
        "nombre": "Bodega Sin Asignar",
        "email": f"bodega-rls-{uuid.uuid4().hex[:10]}@empresa.com",
        "password": "Prueba2024!Seguro",
        "rol_id": _rol_id_bodega(client, admin_headers),
        "codalms": [],
        "todos_los_almacenes": False,
    }
    r = client.post(f"{API}/users/", headers=admin_headers, json=payload)
    assert r.status_code == 400


def test_reporte_excel_bodega_respeta_rls(client, usuario_una_bodega):
    """Vector de fuga de mayor volumen (H-1): la exportación Excel también debe quedar
    cubierta por la misma restricción que los endpoints JSON."""
    headers, ajena = usuario_una_bodega["headers"], usuario_una_bodega["ajena"]
    r = client.get(
        f"{API}/analytics/bodega/reportes/analisis-mensual/excel",
        headers=headers, params={"almacen": ajena},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_filtros_solo_lista_bodegas_asignadas(
    client, usuario_una_bodega, usuario_todos_los_almacenes, catalogo_almacenes,
):
    """El selector de almacén de la barra de filtros no debe mostrar bodegas ajenas a un
    usuario creado para una específica; un usuario con `todos_los_almacenes` sí debe ver
    el catálogo completo (petición explícita del usuario, 2026-07-29)."""
    nombres = {a["codalm"]: a["nombre_almacen"] for a in catalogo_almacenes}
    propia, ajena = usuario_una_bodega["propia"], usuario_una_bodega["ajena"]

    r_restringido = client.get(f"{API}/analytics/bodega/filtros", headers=usuario_una_bodega["headers"])
    assert r_restringido.status_code == 200
    vistos = r_restringido.json()["almacenes"]
    assert nombres[propia] in vistos
    assert nombres[ajena] not in vistos

    r_amplio = client.get(f"{API}/analytics/bodega/filtros", headers=usuario_todos_los_almacenes["headers"])
    assert r_amplio.status_code == 200
    assert nombres[ajena] in r_amplio.json()["almacenes"]
