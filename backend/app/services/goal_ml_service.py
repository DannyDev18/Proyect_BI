# backend/app/services/goal_ml_service.py
"""Integración ML dentro del módulo Metas y Comisiones
(docs/auditoria/15_fase_integracion_ml_metas_comisiones.md,
docs/auditoria/20_decomision_goals_rf.md). Compone modelos YA entrenados y publicados (no
reentrena nada) con el motor de cálculo estadístico (`goal_calculation_engine.py`) y el
histórico del EDW:

- **Generación de metas**: estadística pura sobre **Venta Neta**
  (`GoalRepository.get_vendor_monthly_history` = ventas - devoluciones del período) vía
  `IQRGoalCalculationEngine` -- 24 meses, recorte de picos con IQR, tendencia de los
  últimos meses. El modelo `goals_rf` fue decomisionado (docs/auditoria/20_...md): no
  aportaba mejor precisión que el motor estadístico y complicaba sin necesidad la
  generación de metas realistas.
- **Detección de valores atípicos**: `anomaly` (IsolationForest) corrido al grano
  correcto (línea de transacción, igual que su contrato) para señalar qué MESES del
  histórico del vendedor tienen comportamiento extraordinario -- esos meses no se
  eliminan, solo pesan menos en `IQRGoalCalculationEngine` (ver `PESO_MES_ATIPICO_ML`).
- **Recomendación comercial**: `association` (reglas direccionales) aplicado sobre los
  productos que más vende el vendedor, para sugerir qué más colocar.
- **Pronóstico de cierre**: `sales_rf` vía el mismo walk-forward que usa Gerencia
  (`app/ml/forecasting.py`), con horizonte = días restantes del mes en curso.

Toda inferencia pasa por `app/ml/inference.py`, que ya aplica
`app/ml/contract_validation.py` (ModelLoader -> ContractValidator -> Modelo ->
validación de salida) antes de devolver un valor. Dos políticas de fallo distintas,
deliberadas:
  - Pronóstico de cierre y recomendaciones son el ENTREGABLE principal de su propia
    llamada: si el contrato falla, se propaga (`ModelContractError`, ya es un
    `DomainError` -> 400) en vez de degradar en silencio -- exactamente lo que la
    auditoría 11 marcó como el bug histórico (0.0/"Error" mudo).
  - La señal de anomalías es un INSUMO adicional del cálculo estadístico de metas: si
    su contrato falla, se registra el error y se continúa sin esa señal (el cálculo de
    metas no debe romperse por un modelo secundario)."""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from statistics import NormalDist

import pandas as pd

from app.core.config import settings
from app.core.exceptions import ExternalDataError, ModelContractError, ValidationError
from app.ml import inference
from app.ml.forecasting import walk_forward_forecast
from app.ml.model_loader import ModelLoader
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.goal_repository import GoalRepository, VendorMonthlySales
from app.services.commission_engine import fecha_referencia_periodo
from app.services.goal_calculation_engine import IQRGoalCalculationEngine, RegistroMensual

logger = logging.getLogger("Backend.GoalMLService")

# Umbral RELATIVO (no absoluto): un mes pesa menos si su fracción de transacciones
# anómalas supera 2x la mediana histórica del propio vendedor. Evita hardcodear la tasa
# de contaminación del modelo (detalle de entrenamiento, ml/contracts/models/anomalies.json)
# como si fuera una regla de negocio.
FACTOR_UMBRAL_ANOMALIA_MENSUAL = 2.0
FRACCION_MINIMA_ANOMALIA = 0.05


@dataclass
class SugerenciaMeta:
    vendedor_origen: str
    meta_sugerida_estadistica: float
    metodo_estadistico: str
    meses_historico_usados: int
    valores_atipicos_excluidos: int
    meses_atipicos_ml_detectados: int
    # Trazabilidad del cálculo de Venta Neta -> propuesta del siguiente mes (ver
    # `IQRGoalCalculationEngine._calcular_base_siguiente_mes`): permite al panel gerencial
    # mostrar por qué se sugirió el monto, no solo el número final.
    componente_estacional: float | None
    componente_tendencia: float
    factor_tendencia_aplicado: float
    coeficiente_variacion: float


@dataclass
class ForecastCierre:
    sucursal: str
    dias_restantes: int
    ventas_mes_actual: float
    proyeccion_cierre: float
    meta: float
    pct_cumplimiento_esperado: float
    probabilidad_alcanzar_meta: float | None
    mae_modelo: float | None


@dataclass
class RecomendacionComercial:
    producto_cod: str
    score_afinidad: float


@dataclass
class RecomendacionPorCategoria:
    categoria_origen: str
    categoria_sugerida: str
    producto_sugerido: str
    score_afinidad: float


@dataclass
class ClasificacionRiesgoVendedor:
    nombre: str
    ventas: float
    meta: float
    pct_cumplimiento: float
    pct_esperado_a_la_fecha: float
    estado: str  # 'en_riesgo' | 'en_ritmo' | 'alta_probabilidad'


# Panel gerencial: clasificación por RITMO (día del mes transcurrido vs. % de meta ya
# cumplido), no por un modelo ML de probabilidad -- el modelo `sales_rf` no tiene grano
# por vendedor (H-14b, ml/contracts/models/sales.json: entrena con la serie GLOBAL), así
# que una probabilidad por vendedor individual no sería una inferencia real del modelo,
# sería inventada. Este umbral relativo (0.8/1.1 sobre el ritmo esperado) es la
# alternativa honesta: dato real (ventas/meta) comparado contra el tiempo transcurrido.
UMBRAL_RIESGO_RITMO = 0.8
UMBRAL_ALTA_PROBABILIDAD_RITMO = 1.1


class GoalMLService:
    def __init__(
        self,
        goal_repo: GoalRepository,
        dataset_repo: DatasetRepository,
        model_loader: ModelLoader,
        calculation_engine: IQRGoalCalculationEngine | None = None,
        commission_config_repo: CommissionConfigRepository | None = None,
        notification_service=None,
    ):
        self.goal_repo = goal_repo
        self.dataset_repo = dataset_repo
        self.model_loader = model_loader
        self.calculation_engine = calculation_engine or IQRGoalCalculationEngine()
        self.commission_config_repo = commission_config_repo
        # `NotificationService` opcional (docs/auditoria/31_modulo_notificaciones.md, RN-N2):
        # sin tipar el import directo evita un ciclo (NotificationService no depende de
        # GoalMLService, pero se compone en `app.api.dependencies` en el mismo módulo).
        self.notification_service = notification_service

    # ── Generación de metas (estadística pura: IQR sobre Venta Neta, sin ML) ───────────
    def generate_proposals(self, anio: int, mes: int, factor_presion: float = 1.0) -> int:
        """Genera/actualiza las metas OFICIALES del período `anio`/`mes` (docs/auditoria/
        19_.../20_...md): una fila por vendedor (no por vendedor×sucursal, ver
        `GoalRepository.get_vendors_with_recent_sales`), usando `meta_sugerida_estadistica`
        (`IQRGoalCalculationEngine` sobre Venta Neta, 24 meses con recorte de picos vía
        IQR + tendencia de los últimos meses + techo/piso de sanidad contra la tendencia
        reciente) -- sin ningún modelo ML (`goals_rf` decomisionado).

        `factor_presion` (el mismo slider de "presión comercial" que ya usaba el
        generador anterior) se pasa como `factor_crecimiento` del motor estadístico --
        mismo rol: empuje comercial adicional sobre la tendencia ya calculada.

        Ajuste por tipo de vendedor (docs/features/plan_integracion_comisiones_variables.md
        §2, brecha B1): si hay `commission_config_repo` disponible, la meta base se
        multiplica por `COMISION_META_FACTOR_EXTERNO`/`_INTERNO` según
        `comision_config_vendedor.tipo`; un vendedor "nuevo" (fecha_ingreso dentro de
        `COMISION_VENDEDOR_NUEVO_MESES`) recibe `COMISION_VENDEDOR_NUEVO_FACTOR` del
        promedio del equipo en vez de su propio histórico (insuficiente/inexistente)."""
        vendedores = self.goal_repo.get_vendors_with_recent_sales(anio, mes)
        base_por_vendedor: dict[str, float] = {}
        for t in vendedores:
            sugerencia = self.suggest_goal(t.vendedor_origen, factor_crecimiento=factor_presion)
            base_por_vendedor[t.vendedor_origen] = sugerencia.meta_sugerida_estadistica

        promedio_equipo = (
            sum(base_por_vendedor.values()) / len(base_por_vendedor) if base_por_vendedor else 0.0
        )

        registros_afectados = 0
        for t in vendedores:
            meta_monto = self._ajustar_meta_por_tipo(t.vendedor_origen, base_por_vendedor[t.vendedor_origen], promedio_equipo, anio, mes)
            meta_unidades = max(0.0, float(t.unidades_anterior or 0.0) * factor_presion)

            existing = self.goal_repo.find_proposal(anio, mes, t.vendedor_origen)
            if not existing:
                self.goal_repo.insert_proposal(anio, mes, t.vendedor_origen, meta_monto, meta_unidades)
                registros_afectados += 1
            elif existing[1] == "PROPUESTA":
                self.goal_repo.update_proposal_amounts(existing[0], meta_monto, meta_unidades)
                registros_afectados += 1

        self.goal_repo.commit()
        if registros_afectados > 0 and self.notification_service is not None:
            self.notification_service.emitir(
                tipo_evento="metas_generadas",
                rol_destino="gerencia",
                titulo="Metas propuestas listas para aprobar",
                mensaje=f"📋 Se generaron/actualizaron {registros_afectados} propuestas de meta para {mes}/{anio}.",
                prioridad="media",
                accion_url="/gerencia/metas",
                contexto={"anio": anio, "mes": mes},
            )
        return registros_afectados

    def _ajustar_meta_por_tipo(
        self, vendedor_origen: str, meta_base: float, promedio_equipo: float, anio: int, mes: int,
    ) -> float:
        if self.commission_config_repo is None:
            return meta_base
        config_vendedor = self.commission_config_repo.get_config_vendedor(
            vendedor_origen, fecha_referencia_periodo(anio, mes)
        )

        if config_vendedor and config_vendedor.fecha_ingreso:
            meses_antiguedad = (anio - config_vendedor.fecha_ingreso.year) * 12 + (mes - config_vendedor.fecha_ingreso.month)
            if 0 <= meses_antiguedad < settings.COMISION_VENDEDOR_NUEVO_MESES:
                return round(promedio_equipo * settings.COMISION_VENDEDOR_NUEVO_FACTOR, 2)

        tipo = config_vendedor.tipo if config_vendedor else "externo"
        factor = settings.COMISION_META_FACTOR_EXTERNO if tipo == "externo" else settings.COMISION_META_FACTOR_INTERNO
        return round(meta_base * factor, 2)

    def suggest_goal(
        self, vendedor_origen: str, factor_estacional: float = 1.0, factor_crecimiento: float = 1.0,
    ) -> SugerenciaMeta:
        hist = self.goal_repo.get_vendor_monthly_history(vendedor_origen)
        if not hist:
            raise ValidationError(f"Sin histórico de ventas para vendedor={vendedor_origen}.")

        registros = [RegistroMensual(anio=h.anio, mes=h.mes, ventas=h.ventas, unidades=h.unidades) for h in hist]
        meses_atipicos_ml = self._detectar_meses_atipicos(vendedor_origen, hist)

        resultado = self.calculation_engine.calcular(
            vendedor_origen, registros, factor_estacional, factor_crecimiento,
            meses_atipicos_ml=meses_atipicos_ml,
        )

        return SugerenciaMeta(
            vendedor_origen=vendedor_origen,
            meta_sugerida_estadistica=resultado.meta_ventas_total,
            metodo_estadistico=resultado.metodo,
            meses_historico_usados=resultado.meses_historico_usados,
            valores_atipicos_excluidos=resultado.valores_atipicos_excluidos,
            meses_atipicos_ml_detectados=resultado.meses_atipicos_ml_detectados,
            componente_estacional=resultado.componente_estacional,
            componente_tendencia=resultado.componente_tendencia,
            factor_tendencia_aplicado=resultado.factor_tendencia_aplicado,
            coeficiente_variacion=resultado.coeficiente_variacion,
        )

    # ── Detección de valores atípicos (anomaly, grano de transacción) ─────────
    def _detectar_meses_atipicos(
        self, vendedor_origen: str, hist: list[VendorMonthlySales],
    ) -> frozenset[tuple[int, int]]:
        if not hist or not self.model_loader.is_loaded("anomaly"):
            return frozenset()

        primero = min(hist, key=lambda h: (h.anio, h.mes))
        try:
            transacciones = self.goal_repo.get_vendor_transactions_history(vendedor_origen, primero.anio, primero.mes)
        except Exception as e:
            logger.error(f"Fallo consultando transacciones para detección de anomalías ({vendedor_origen}): {e}")
            return frozenset()
        if not transacciones:
            return frozenset()

        df = pd.DataFrame([t._asdict() for t in transacciones])
        try:
            resultado = inference.detect_anomalies(self.model_loader, df[["subtotal_neto", "cantidad", "costo_total", "margen"]])
        except ModelContractError as e:
            # Señal secundaria: si el contrato falla, se continúa sin ella (no bloquea
            # la generación de la meta, que sigue funcionando solo con IQR).
            logger.error(f"Contrato del modelo 'anomaly' violado, se omite la señal ML para esta meta: {e}")
            return frozenset()

        df["es_anomalia"] = (resultado["is_anomaly_pred"].to_numpy() == -1)
        fracciones = df.groupby(["anio", "mes"])["es_anomalia"].mean()
        if fracciones.empty:
            return frozenset()

        mediana = float(fracciones.median())
        umbral = max(mediana * FACTOR_UMBRAL_ANOMALIA_MENSUAL, FRACCION_MINIMA_ANOMALIA)
        atipicos = frozenset((int(a), int(m)) for (a, m), frac in fracciones.items() if frac > umbral)
        if atipicos:
            logger.info(f"Meses atípicos detectados (IsolationForest) para {vendedor_origen}: {sorted(atipicos)}")
        return atipicos

    # ── Recomendación comercial ────────────────────────────────────────────────
    def get_commercial_recommendations(self, vendedor_origen: str, top_n: int = 5) -> list[RecomendacionComercial]:
        top_productos = self.goal_repo.get_vendor_top_products(vendedor_origen, limit=10)
        if not top_productos:
            return []
        recs_df = inference.get_recommendations(self.model_loader, top_productos, top_n=top_n)
        return [RecomendacionComercial(producto_cod=str(row["item_B"]), score_afinidad=float(row["score"])) for _, row in recs_df.iterrows()]

    # ── Pronóstico de cierre ───────────────────────────────────────────────────
    def forecast_cierre(self, sucursal: str | None, meta_mensual: float) -> ForecastCierre:
        hoy = datetime.date.today()
        ultimo_dia_mes = (datetime.date(hoy.year + (hoy.month == 12), hoy.month % 12 + 1, 1) - datetime.timedelta(days=1))
        dias_restantes = (ultimo_dia_mes - hoy).days

        try:
            df_hist = self.dataset_repo.get_daily_sales_history(sucursal=sucursal)
        except Exception as e:
            logger.error(f"Fallo consultando historial de ventas para pronóstico de cierre (sucursal={sucursal}): {e}")
            raise ExternalDataError("No se pudo consultar el historial de ventas del EDW.") from e

        if df_hist.empty:
            return ForecastCierre(sucursal or "Consolidado", dias_restantes, 0.0, 0.0, meta_mensual, 0.0, None, None)

        df_hist["ds"] = pd.to_datetime(df_hist["ds"])
        df_hist = df_hist.sort_values("ds").set_index("ds").resample("D").sum().fillna(0)

        ventas_mes_actual = float(
            df_hist.loc[(df_hist.index.year == hoy.year) & (df_hist.index.month == hoy.month), "y_sales_net"].sum()
        )

        generated = walk_forward_forecast(self.model_loader, df_hist, "y_sales_net", dias_restantes, inference.predict_sales)
        proyeccion_restante = sum(v for _, v in generated)
        proyeccion_cierre = ventas_mes_actual + proyeccion_restante

        mae_modelo = self.model_loader.get_meta("sales_rf").get("metrics", {}).get("MAE")
        pct_esperado = round((proyeccion_cierre / meta_mensual) * 100, 1) if meta_mensual > 0 else 0.0
        probabilidad = self._probabilidad_alcanzar_meta(proyeccion_cierre, meta_mensual, mae_modelo, dias_restantes)

        return ForecastCierre(
            sucursal=sucursal or "Consolidado",
            dias_restantes=dias_restantes,
            ventas_mes_actual=round(ventas_mes_actual, 2),
            proyeccion_cierre=round(proyeccion_cierre, 2),
            meta=meta_mensual,
            pct_cumplimiento_esperado=pct_esperado,
            probabilidad_alcanzar_meta=probabilidad,
            mae_modelo=round(mae_modelo, 2) if mae_modelo is not None else None,
        )

    # ── Recomendaciones por categoría (panel gerencial) ────────────────────────
    def get_category_recommendations(self, top_n: int = 10) -> list[RecomendacionPorCategoria]:
        """Reglas de asociación globales (sin `item_history`, ver `inference.get_recommendations`)
        agregadas a nivel de categoría vía `dim_producto.nombre_clase` -- vista macro para
        Gerencia, complementaria a `get_commercial_recommendations` (por vendedor)."""
        rules_df = inference.get_recommendations(self.model_loader, item_history=None, top_n=top_n)
        if rules_df.empty:
            return []
        codarts = list(set(rules_df["item_A"]).union(set(rules_df["item_B"])))
        categorias = self.goal_repo.get_product_categories(codarts)
        return [
            RecomendacionPorCategoria(
                categoria_origen=categorias.get(str(row["item_A"]), "Desconocida"),
                categoria_sugerida=categorias.get(str(row["item_B"]), "Desconocida"),
                producto_sugerido=str(row["item_B"]),
                score_afinidad=float(row["score"]),
            )
            for _, row in rules_df.iterrows()
        ]

    # ── Clasificación de riesgo por vendedor (panel gerencial) ─────────────────
    def classify_vendor_risk(self, ranking_vendedores: list[dict]) -> list[ClasificacionRiesgoVendedor]:
        hoy = datetime.date.today()
        ultimo_dia_mes = (datetime.date(hoy.year + (hoy.month == 12), hoy.month % 12 + 1, 1) - datetime.timedelta(days=1)).day
        pct_tiempo_transcurrido = round((hoy.day / ultimo_dia_mes) * 100, 1)

        resultados = []
        for row in ranking_vendedores:
            meta = float(row.get("meta") or 0.0)
            ventas = float(row.get("ventas") or 0.0)
            pct_cumplimiento = round((ventas / meta) * 100, 1) if meta > 0 else 0.0

            if pct_cumplimiento < pct_tiempo_transcurrido * UMBRAL_RIESGO_RITMO:
                estado = "en_riesgo"
            elif pct_cumplimiento > pct_tiempo_transcurrido * UMBRAL_ALTA_PROBABILIDAD_RITMO:
                estado = "alta_probabilidad"
            else:
                estado = "en_ritmo"

            resultados.append(ClasificacionRiesgoVendedor(
                nombre=str(row.get("nombre", "Desconocido")), ventas=ventas, meta=meta,
                pct_cumplimiento=pct_cumplimiento, pct_esperado_a_la_fecha=pct_tiempo_transcurrido, estado=estado,
            ))
        return resultados

    @staticmethod
    def _probabilidad_alcanzar_meta(
        proyeccion_cierre: float, meta: float, mae_modelo: float | None, dias_restantes: int,
    ) -> float | None:
        """Aproximación estadística (no un modelo calibrado): asume que el error diario
        del modelo (MAE real del holdout, mismo dato que usa el intervalo de Gerencia,
        H-09) es independiente entre días y se acumula en cuadratura sobre los días
        restantes -- una desviación estándar aproximada de la proyección total. Con esa
        desviación, `P(cierre >= meta)` es la cola superior de una normal centrada en la
        proyección puntual. Se documenta como aproximación explícita, no como
        probabilidad calibrada de un clasificador."""
        if mae_modelo is None or dias_restantes <= 0 or meta <= 0:
            return None
        sigma = mae_modelo * (dias_restantes ** 0.5)
        if sigma <= 0:
            return 100.0 if proyeccion_cierre >= meta else 0.0
        z = (meta - proyeccion_cierre) / sigma
        prob = 1 - NormalDist().cdf(z)
        return round(max(0.0, min(1.0, prob)) * 100, 1)
