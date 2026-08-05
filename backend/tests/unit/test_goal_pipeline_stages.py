# backend/tests/unit/test_goal_pipeline_stages.py
"""Etapas del motor de metas v3 no cubiertas por `IQRGoalCalculationEngine`
(docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md §18, Fase 6)."""
import pytest

from app.services.goal_pipeline_stages import (
    ETAPAS_CATALOGO,
    aplicar_capacidad_instalada,
    aplicar_estrategia,
    aplicar_factor_cartera,
    aplicar_factor_cumplimiento_historico,
    aplicar_factor_tipo,
    aplicar_penalizacion_volatilidad,
    metodo_implementado,
    redondear_meta,
)


# ── Catálogo cerrado ─────────────────────────────────────────────────────────────────
def test_catalogo_tiene_las_14_etapas():
    assert len(ETAPAS_CATALOGO) == 14


def test_catalogo_no_incluye_e12_ni_e14():
    """E12 (distribución corporativa) y E14 (potencial de mercado) se retiraron por
    completo (migración 0015): ninguna tenía nunca un método implementado, así que
    dejarlas en el catálogo era un mockup sin efecto real (petición explícita del
    usuario)."""
    assert "E12_distribucion" not in ETAPAS_CATALOGO
    assert "E14_potencial" not in ETAPAS_CATALOGO


def test_todas_las_etapas_declaran_parametros_como_lista():
    for etapa, info in ETAPAS_CATALOGO.items():
        assert isinstance(info.get("parametros"), list), f"{etapa} sin lista de parámetros"


def test_parametros_de_cada_etapa_tienen_las_claves_del_formulario_dinamico():
    campos_requeridos = {"clave", "label", "tipo", "min", "max", "paso", "default"}
    for etapa, info in ETAPAS_CATALOGO.items():
        for parametro in info["parametros"]:
            assert campos_requeridos.issubset(parametro.keys()), f"{etapa}.{parametro.get('clave')} incompleto"
            assert parametro["min"] <= parametro["default"] <= parametro["max"]


def test_metodo_implementado_semilla_es_true():
    ok, motivo = metodo_implementado("E1_limpieza", "tukey")
    assert ok is True
    assert motivo is None


def test_metodo_declarado_no_implementado_es_false_con_motivo():
    ok, motivo = metodo_implementado("E1_limpieza", "isolation_forest")
    assert ok is False
    assert motivo


def test_metodo_de_etapa_desconocida_es_false():
    ok, motivo = metodo_implementado("E99_inexistente", "cualquiera")
    assert ok is False
    assert "desconocida" in motivo


# ── E7 -- estrategia ─────────────────────────────────────────────────────────────────
def test_aplicar_estrategia_crecimiento_positivo():
    assert aplicar_estrategia(1000.0, 10.0) == pytest.approx(1100.0)


def test_aplicar_estrategia_crecimiento_cero_es_neutro():
    assert aplicar_estrategia(1000.0, 0.0) == pytest.approx(1000.0)


# ── E8 -- tipo de vendedor ───────────────────────────────────────────────────────────
def test_aplicar_factor_tipo_conocido():
    assert aplicar_factor_tipo(1000.0, "externo", {"externo": 1.10, "interno": 0.95}) == pytest.approx(1100.0)


def test_aplicar_factor_tipo_desconocido_es_neutro():
    assert aplicar_factor_tipo(1000.0, "jefe_agencia", {"externo": 1.10}) == pytest.approx(1000.0)


# ── E9 -- capacidad instalada ────────────────────────────────────────────────────────
def test_capacidad_instalada_recorta_si_supera_el_techo():
    r = aplicar_capacidad_instalada(10000.0, clientes_activos=10, ticket_promedio=100.0, frecuencia_compra_mensual=1.0, holgura=1.10)
    assert r.aplico is True
    assert r.meta_ajustada == pytest.approx(1100.0)


def test_capacidad_instalada_no_recorta_si_no_supera_el_techo():
    r = aplicar_capacidad_instalada(500.0, clientes_activos=10, ticket_promedio=100.0, frecuencia_compra_mensual=1.0)
    assert r.aplico is False
    assert r.meta_ajustada == pytest.approx(500.0)


@pytest.mark.parametrize("clientes,ticket,frecuencia", [(None, 100.0, 1.0), (10, None, 1.0), (10, 100.0, None), (0, 100.0, 1.0)])
def test_capacidad_instalada_se_omite_sin_insumos_completos(clientes, ticket, frecuencia):
    r = aplicar_capacidad_instalada(10000.0, clientes, ticket, frecuencia)
    assert r.aplico is False
    assert r.meta_ajustada == pytest.approx(10000.0)
    assert r.capacidad is None


# ── E11 -- redondeo ──────────────────────────────────────────────────────────────────
def test_redondeo_cercano():
    assert redondear_meta(1234.0, 100, "cercano") == 1200.0
    assert redondear_meta(1260.0, 100, "cercano") == 1300.0


def test_redondeo_arriba():
    assert redondear_meta(1201.0, 100, "arriba") == 1300.0


def test_redondeo_abajo():
    assert redondear_meta(1299.0, 100, "abajo") == 1200.0


def test_redondeo_multiplo_cero_es_paso_a_traves():
    assert redondear_meta(1234.0, 0, "cercano") == 1234.0


# ── E13 -- factor cartera ────────────────────────────────────────────────────────────
def test_factor_cartera_acota_al_rango():
    # 200/100 = 2.0, muy por encima del techo -> se acota a 1.15.
    assert aplicar_factor_cartera(1000.0, 200, 100) == pytest.approx(1150.0)


def test_factor_cartera_sin_datos_es_neutro():
    assert aplicar_factor_cartera(1000.0, None, 100) == pytest.approx(1000.0)


# ── E15 -- cumplimiento histórico ────────────────────────────────────────────────────
def test_cumplimiento_historico_premia_sobrecumplimiento():
    # cumplimiento_promedio=1.2 (120%), peso=0.5 -> 1 + 0.2*0.5 = 1.10
    assert aplicar_factor_cumplimiento_historico(1000.0, 1.2, peso=0.5) == pytest.approx(1100.0)


def test_cumplimiento_historico_sin_dato_es_neutro():
    assert aplicar_factor_cumplimiento_historico(1000.0, None) == pytest.approx(1000.0)


# ── E16 -- penalización por volatilidad ──────────────────────────────────────────────
def test_volatilidad_reduce_el_crecimiento_si_supera_el_umbral():
    resultado = aplicar_penalizacion_volatilidad(factor_crecimiento=1.20, coeficiente_variacion=0.60, umbral_cv=0.40, factor_reduccion=0.5)
    assert resultado == pytest.approx(1.10)  # 1 + 0.20*0.5


def test_volatilidad_no_actua_bajo_el_umbral():
    assert aplicar_penalizacion_volatilidad(1.20, coeficiente_variacion=0.20, umbral_cv=0.40) == pytest.approx(1.20)


def test_volatilidad_no_penaliza_un_factor_de_decrecimiento():
    assert aplicar_penalizacion_volatilidad(0.90, coeficiente_variacion=0.90, umbral_cv=0.40) == pytest.approx(0.90)
