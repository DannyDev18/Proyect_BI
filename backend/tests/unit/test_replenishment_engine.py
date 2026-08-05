# backend/tests/unit/test_replenishment_engine.py
"""Motor puro de Reabastecimiento (docs/auditoria/50_reabastecimiento_inteligente.md,
docs/features/plan_reabastecimiento_inteligente.md). Cada fórmula con su caso de
degradación explícita (sin historia, demanda cero, lead time faltante) -- regla
transversal del plan: ningún resultado se presenta como más confiable de lo que los
datos sostienen."""
import math

import pytest

from app.inventory.engine import (
    CORTE_XYZ_X,
    CORTE_XYZ_Y,
    MESES_MINIMOS_CV,
    MESES_MINIMOS_ESTOCASTICO,
    EstadisticaDemanda,
    ResultadoLeadTime,
    calcular_prioridad,
    cantidad_sugerida,
    clasificar_abc,
    clasificar_xyz,
    coeficiente_variacion,
    cobertura_dias,
    construir_desglose,
    demanda_diaria_simple,
    detectar_cambio_brusco,
    detectar_tendencia_decreciente,
    dias_inventario,
    estadistica_demanda,
    estado_stock,
    evaluar_riesgo,
    punto_reorden,
    punto_reorden_determinista,
    resolver_lead_time,
    stock_seguridad,
)


# ── ABC ─────────────────────────────────────────────────────────────────────────────
class TestClasificarABC:
    def test_dentro_del_corte_a_es_clase_a(self):
        assert clasificar_abc(500, 500, 1000) == "A"  # acumulado=50% <= 80%

    def test_justo_en_el_corte_a_es_clase_a(self):
        assert clasificar_abc(100, 800, 1000) == "A"  # acumulado=80% == corte

    def test_entre_corte_a_y_b_es_clase_b(self):
        assert clasificar_abc(100, 900, 1000) == "B"  # acumulado=90%

    def test_sobre_corte_b_es_clase_c(self):
        assert clasificar_abc(10, 990, 1000) == "C"  # acumulado=99%

    def test_valor_total_cero_degrada_a_c(self):
        assert clasificar_abc(0, 0, 0) == "C"

    def test_cortes_personalizados(self):
        assert clasificar_abc(100, 500, 1000, corte_a=0.4, corte_b=0.7) == "B"


# ── XYZ ─────────────────────────────────────────────────────────────────────────────
class TestClasificarXYZ:
    def test_cv_none_degrada_a_z_conservador(self):
        """Sin evidencia de estabilidad, nunca se asume estabilidad."""
        assert clasificar_xyz(None) == "Z"

    def test_cv_bajo_corte_x(self):
        assert clasificar_xyz(CORTE_XYZ_X - 0.01) == "X"

    def test_cv_justo_en_corte_x(self):
        assert clasificar_xyz(CORTE_XYZ_X) == "X"

    def test_cv_entre_cortes_es_y(self):
        assert clasificar_xyz((CORTE_XYZ_X + CORTE_XYZ_Y) / 2) == "Y"

    def test_cv_sobre_corte_y_es_z(self):
        assert clasificar_xyz(CORTE_XYZ_Y + 0.5) == "Z"


# ── Demanda ────────────────────────────────────────────────────────────────────────
class TestEstadisticaDemanda:
    def test_serie_vacia_es_sin_historia(self):
        r = estadistica_demanda([], 0)
        assert r.metodo == "sin_historia"
        assert r.media_diaria == 0.0

    def test_meses_insuficientes_degrada_a_determinista(self):
        valores = [10.0] * 30
        r = estadistica_demanda(valores, MESES_MINIMOS_ESTOCASTICO - 1)
        assert r.metodo == "determinista"
        assert r.sigma_diaria == 0.0
        assert r.media_diaria == 10.0

    def test_un_solo_punto_degrada_a_determinista_aunque_meses_alcancen(self):
        r = estadistica_demanda([5.0], MESES_MINIMOS_ESTOCASTICO)
        assert r.metodo == "determinista"

    def test_historia_suficiente_calcula_estocastico(self):
        valores = [10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 13.0, 7.0]
        r = estadistica_demanda(valores, MESES_MINIMOS_ESTOCASTICO)
        assert r.metodo == "estocastico"
        assert r.media_diaria == pytest.approx(10.0)
        assert r.sigma_diaria > 0

    def test_demanda_constante_sigma_cero_pero_estocastico(self):
        valores = [10.0] * 20
        r = estadistica_demanda(valores, MESES_MINIMOS_ESTOCASTICO)
        assert r.metodo == "estocastico"
        assert r.sigma_diaria == 0.0


class TestCoeficienteVariacion:
    def test_meses_insuficientes_es_none(self):
        assert coeficiente_variacion(10.0, 2.0, MESES_MINIMOS_CV - 1) is None

    def test_media_cero_es_none(self):
        assert coeficiente_variacion(0.0, 2.0, MESES_MINIMOS_CV) is None

    def test_calculo_normal(self):
        assert coeficiente_variacion(10.0, 5.0, MESES_MINIMOS_CV) == 0.5


# ── Stock de seguridad y ROP ──────────────────────────────────────────────────────
class TestStockSeguridad:
    def test_sin_historia_stock_seguridad_cero(self):
        stat = EstadisticaDemanda(0.0, 0.0, 0, "sin_historia")
        r = stock_seguridad(stat, lead_time_dias=7, nivel_servicio=0.95, dias_seguridad_fallback=5)
        assert r.metodo == "sin_historia"
        assert r.valor == 0.0
        assert r.z_usado is None

    def test_determinista_usa_dias_fallback_fijo(self):
        stat = EstadisticaDemanda(10.0, 0.0, 3, "determinista")
        r = stock_seguridad(stat, lead_time_dias=7, nivel_servicio=0.95, dias_seguridad_fallback=5)
        assert r.metodo == "determinista"
        assert r.valor == 50.0  # 10 * 5
        assert r.z_usado is None

    def test_lead_time_cero_degrada_a_determinista(self):
        stat = EstadisticaDemanda(10.0, 3.0, 8, "estocastico")
        r = stock_seguridad(stat, lead_time_dias=0, nivel_servicio=0.95, dias_seguridad_fallback=5)
        assert r.metodo == "determinista"

    def test_estocastico_formula_z_sigma_raiz_lt(self):
        stat = EstadisticaDemanda(10.0, 3.0, 8, "estocastico")
        r = stock_seguridad(stat, lead_time_dias=9, nivel_servicio=0.95, dias_seguridad_fallback=5)
        assert r.metodo == "estocastico"
        esperado = round(1.6449 * 3.0 * math.sqrt(9), 2)
        assert r.valor == pytest.approx(esperado, abs=0.01)
        assert r.z_usado == pytest.approx(1.6449)

    def test_nivel_servicio_mas_alto_da_mas_stock_seguridad(self):
        stat = EstadisticaDemanda(10.0, 3.0, 8, "estocastico")
        bajo = stock_seguridad(stat, lead_time_dias=7, nivel_servicio=0.90, dias_seguridad_fallback=5)
        alto = stock_seguridad(stat, lead_time_dias=7, nivel_servicio=0.99, dias_seguridad_fallback=5)
        assert alto.valor > bajo.valor

    def test_nivel_servicio_no_tabulado_usa_el_mas_cercano(self):
        stat = EstadisticaDemanda(10.0, 3.0, 8, "estocastico")
        r = stock_seguridad(stat, lead_time_dias=7, nivel_servicio=0.94, dias_seguridad_fallback=5)
        assert r.z_usado == pytest.approx(1.6449)  # el más cercano a 0.94 es 0.95


class TestPuntoReorden:
    def test_sin_historia_rop_cero_no_comprar_a_ciegas(self):
        stat = EstadisticaDemanda(0.0, 0.0, 0, "sin_historia")
        ss = stock_seguridad(stat, 7, 0.95, 5)
        r = punto_reorden(stat, 7, ss)
        assert r.valor == 0.0
        assert r.metodo == "sin_historia"

    def test_rop_determinista_es_demanda_por_lt_mas_ss_fijo(self):
        stat = EstadisticaDemanda(10.0, 0.0, 3, "determinista")
        ss = stock_seguridad(stat, 7, 0.95, 5)
        r = punto_reorden(stat, 7, ss)
        assert r.valor == pytest.approx(10 * 7 + 50)  # 120

    def test_rop_estocastico_incluye_variabilidad(self):
        stat = EstadisticaDemanda(10.0, 3.0, 8, "estocastico")
        ss = stock_seguridad(stat, 7, 0.95, 5)
        r = punto_reorden(stat, 7, ss)
        assert r.valor == pytest.approx(10 * 7 + ss.valor)
        assert r.metodo == "estocastico"


# ── Cobertura y riesgo ────────────────────────────────────────────────────────────
class TestCoberturaDias:
    def test_sin_demanda_es_none(self):
        assert cobertura_dias(100, 0) is None

    def test_calculo_normal(self):
        assert cobertura_dias(100, 10) == 10.0


class TestEvaluarRiesgo:
    def test_sin_stock_es_critico(self):
        assert evaluar_riesgo(cobertura=None, lead_time_dias=7, stock_actual=0, rop=50) == "critico"

    def test_sin_demanda_pero_con_stock_es_sin_demanda(self):
        assert evaluar_riesgo(cobertura=None, lead_time_dias=7, stock_actual=50, rop=0) == "sin_demanda"

    def test_cobertura_bajo_mitad_lead_time_es_critico(self):
        assert evaluar_riesgo(cobertura=3, lead_time_dias=7, stock_actual=30, rop=50) == "critico"

    def test_cobertura_bajo_lead_time_es_alto(self):
        assert evaluar_riesgo(cobertura=5, lead_time_dias=7, stock_actual=50, rop=60) == "alto"

    def test_stock_bajo_rop_pero_sobre_lead_time_es_medio(self):
        assert evaluar_riesgo(cobertura=8, lead_time_dias=7, stock_actual=40, rop=50) == "medio"

    def test_stock_sobre_rop_es_bajo(self):
        assert evaluar_riesgo(cobertura=20, lead_time_dias=7, stock_actual=200, rop=50) == "bajo"


class TestCalcularPrioridad:
    def test_riesgo_domina_sobre_clase_abc(self):
        p_critico_c = calcular_prioridad("critico", "C", 1)
        p_bajo_a = calcular_prioridad("bajo", "A", 1)
        assert p_critico_c < p_bajo_a

    def test_mismo_riesgo_desempata_por_abc(self):
        p_a = calcular_prioridad("alto", "A", 5)
        p_c = calcular_prioridad("alto", "C", 5)
        assert p_a < p_c

    def test_dias_hasta_quiebre_none_no_rompe(self):
        assert calcular_prioridad("alto", "B", None) == calcular_prioridad("alto", "B", 0)


# ── Lead time ──────────────────────────────────────────────────────────────────────
class TestResolverLeadTime:
    def test_prioriza_producto(self):
        r = resolver_lead_time(5, 10, 15, 20)
        assert r.dias == 5 and r.origen == "producto"

    def test_sin_producto_usa_categoria(self):
        r = resolver_lead_time(None, 10, 15, 20)
        assert r.dias == 10 and r.origen == "categoria"

    def test_sin_producto_ni_categoria_usa_proveedor(self):
        r = resolver_lead_time(None, None, 15, 20)
        assert r.dias == 15 and r.origen == "proveedor"

    def test_sin_ninguno_usa_default_y_lo_declara(self):
        r = resolver_lead_time(None, None, None, 20)
        assert r.dias == 20 and r.origen == "default"

    def test_valores_cero_o_negativos_se_ignoran(self):
        r = resolver_lead_time(0, -1, None, 20)
        assert r.origen == "default"


# ── Cantidad sugerida ──────────────────────────────────────────────────────────────
class TestCantidadSugerida:
    def test_stock_sobre_objetivo_no_compra(self):
        stat = EstadisticaDemanda(10.0, 0.0, 3, "determinista")
        ss = stock_seguridad(stat, 7, 0.95, 5)
        rop = punto_reorden(stat, 7, ss)
        cantidad = cantidad_sugerida(stock_actual=1000, demanda_diaria_media=10, rop=rop, horizonte_dias=30)
        assert cantidad == 0.0

    def test_calcula_hasta_cubrir_rop_mas_horizonte(self):
        stat = EstadisticaDemanda(10.0, 0.0, 3, "determinista")
        ss = stock_seguridad(stat, 7, 0.95, 5)
        rop = punto_reorden(stat, 7, ss)  # 120
        cantidad = cantidad_sugerida(stock_actual=0, demanda_diaria_media=10, rop=rop, horizonte_dias=30)
        assert cantidad == pytest.approx(120 + 300)  # rop + demanda*horizonte

    def test_redondea_al_multiplo_de_compra(self):
        stat = EstadisticaDemanda(10.0, 0.0, 3, "determinista")
        ss = stock_seguridad(stat, 7, 0.95, 5)
        rop = punto_reorden(stat, 7, ss)
        cantidad = cantidad_sugerida(stock_actual=0, demanda_diaria_media=10, rop=rop, horizonte_dias=30, multiplo_compra=50)
        assert cantidad % 50 == 0
        assert cantidad >= 420


# ── Desglose de explicabilidad ────────────────────────────────────────────────────
class TestConstruirDesglose:
    def test_desglose_completo_con_historia_suficiente(self):
        stat = estadistica_demanda([10.0, 12.0, 8.0, 11.0, 9.0, 10.0, 13.0, 7.0], MESES_MINIMOS_ESTOCASTICO)
        cv = coeficiente_variacion(stat.media_diaria, stat.sigma_diaria, stat.meses_con_venta)
        lt = resolver_lead_time(7, None, None, 10)
        ss = stock_seguridad(stat, lt.dias, 0.95, 5)
        rop = punto_reorden(stat, lt.dias, ss)
        cantidad = cantidad_sugerida(50, stat.media_diaria, rop, 30)
        d = construir_desglose(
            codart="ABC123", clase_abc="A", clase_xyz=clasificar_xyz(cv),
            stat=stat, cv=cv, metodo_demanda="ml_demand_rf",
            lt=lt, nivel_servicio=0.95, ss=ss, rop=rop,
            stock_actual=50, cantidad=cantidad,
        )
        assert d.codart == "ABC123"
        assert d.lead_time_origen == "producto"
        assert d.metodo_stock_seguridad == "estocastico"
        assert d.riesgo in {"critico", "alto", "medio", "bajo", "sin_demanda"}
        assert len(d.razones) >= 1

    def test_desglose_declara_lead_time_por_defecto(self):
        stat = EstadisticaDemanda(5.0, 0.0, 2, "determinista")
        lt = resolver_lead_time(None, None, None, 12)
        ss = stock_seguridad(stat, lt.dias, 0.90, 5)
        rop = punto_reorden(stat, lt.dias, ss)
        cantidad = cantidad_sugerida(10, stat.media_diaria, rop, 30)
        d = construir_desglose(
            codart="XYZ999", clase_abc="C", clase_xyz="Z",
            stat=stat, cv=None, metodo_demanda="estadistico",
            lt=lt, nivel_servicio=0.90, ss=ss, rop=rop,
            stock_actual=10, cantidad=cantidad,
        )
        assert any("por defecto" in r for r in d.razones)

    def test_desglose_sin_historia_declara_la_limitacion(self):
        stat = EstadisticaDemanda(0.0, 0.0, 0, "sin_historia")
        lt = resolver_lead_time(None, None, None, 10)
        ss = stock_seguridad(stat, lt.dias, 0.95, 5)
        rop = punto_reorden(stat, lt.dias, ss)
        cantidad = cantidad_sugerida(0, stat.media_diaria, rop, 30)
        d = construir_desglose(
            codart="NEW001", clase_abc="C", clase_xyz="Z",
            stat=stat, cv=None, metodo_demanda="sin_historia",
            lt=lt, nivel_servicio=0.90, ss=ss, rop=rop,
            stock_actual=0, cantidad=cantidad,
        )
        assert d.punto_reorden == 0.0
        assert d.cantidad_sugerida == 0.0
        assert any("Sin historia" in r for r in d.razones)


class TestDetectarCambioBrusco:
    def test_valor_fuera_de_2_sigma_dispara_la_alerta(self):
        assert detectar_cambio_brusco(valor_reciente=100, media_historica=20, sigma_historica=5, meses_con_venta=6) is True

    def test_valor_dentro_de_2_sigma_no_dispara(self):
        assert detectar_cambio_brusco(valor_reciente=22, media_historica=20, sigma_historica=5, meses_con_venta=6) is False

    def test_exactamente_en_el_borde_no_dispara(self):
        assert detectar_cambio_brusco(valor_reciente=30, media_historica=20, sigma_historica=5, meses_con_venta=6) is False

    def test_sin_variabilidad_historica_no_dispara(self):
        assert detectar_cambio_brusco(valor_reciente=100, media_historica=20, sigma_historica=0, meses_con_venta=6) is False

    def test_pocos_meses_de_historia_no_dispara_aunque_el_salto_sea_grande(self):
        assert detectar_cambio_brusco(valor_reciente=100, media_historica=20, sigma_historica=5, meses_con_venta=2) is False


class TestDetectarTendenciaDecreciente:
    def test_tres_meses_estrictamente_decrecientes_dispara(self):
        assert detectar_tendencia_decreciente([50, 40, 30, 20], periodos=3) is True

    def test_un_repunte_intermedio_no_dispara(self):
        assert detectar_tendencia_decreciente([50, 30, 40, 20], periodos=3) is False

    def test_empate_no_cuenta_como_decreciente(self):
        assert detectar_tendencia_decreciente([50, 30, 30, 20], periodos=3) is False

    def test_menos_meses_que_periodos_no_dispara(self):
        assert detectar_tendencia_decreciente([50, 30], periodos=3) is False

    def test_serie_creciente_no_dispara(self):
        assert detectar_tendencia_decreciente([10, 20, 30, 40], periodos=3) is False


# ── Fórmulas deterministas legacy (D-1/D-2, auditoría 52 -- absorbidas de
# `WarehouseService` en la Fase 2 del refactor de módulo, mismo resultado exacto). ──────
class TestDemandaDiariaSimple:
    def test_divide_salidas_entre_dias(self):
        assert demanda_diaria_simple(300, 30) == 10.0

    def test_dias_cero_devuelve_cero_sin_dividir_por_cero(self):
        assert demanda_diaria_simple(300, 0) == 0.0


class TestPuntoReordenDeterminista:
    def test_usa_el_configurado_si_es_positivo(self):
        assert punto_reorden_determinista(50, 10, 7, 3) == 50.0

    def test_calcula_con_lead_time_y_seguridad_si_no_hay_configurado(self):
        assert punto_reorden_determinista(0, 10, 7, 3) == 100.0  # 10 * (7+3)

    def test_configurado_negativo_se_ignora(self):
        assert punto_reorden_determinista(-1, 10, 7, 3) == 100.0


class TestDiasInventario:
    def test_divide_stock_entre_salida_diaria(self):
        assert dias_inventario(100, 10) == 10.0

    def test_sin_salida_diaria_devuelve_none(self):
        assert dias_inventario(100, 0) is None


class TestEstadoStock:
    def test_dias_inventario_sobre_umbral_es_exceso(self):
        assert estado_stock(500, 50, 200, dias_exceso=180, factor_cerca_reorden=1.2) == "Exceso"

    def test_sin_punto_de_reorden_configurado_es_seguro(self):
        assert estado_stock(10, 0, None, dias_exceso=180, factor_cerca_reorden=1.2) == "Seguro"

    def test_stock_bajo_el_reorden_es_critico(self):
        assert estado_stock(5, 10, 5.0, dias_exceso=180, factor_cerca_reorden=1.2) == "Crítico"

    def test_stock_cerca_del_reorden_es_cerca(self):
        assert estado_stock(11, 10, 11.0, dias_exceso=180, factor_cerca_reorden=1.2) == "Cerca"

    def test_stock_lejos_del_reorden_es_seguro(self):
        assert estado_stock(50, 10, 50.0, dias_exceso=180, factor_cerca_reorden=1.2) == "Seguro"
