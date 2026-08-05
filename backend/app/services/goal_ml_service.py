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
    auditoría 11 marcó como el bug histórico (0.0/"Error" mudo)."""
from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import statistics
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.ml import inference
from app.ml.model_loader import ModelLoader
from app.repositories.commission_config_repository import CommissionConfigRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.goal_repository import GoalRepository, VendorRecentSales
from app.services.commission_engine import fecha_referencia_periodo
from app.services.goal_calculation_engine import (
    DEFAULT_PARAMETROS, METODO_SIN_HISTORICO, IQRGoalCalculationEngine, MetaMotorParametros, RegistroMensual,
    ajustar_meta_por_madurez,
)
from app.services.goal_pipeline_stages import (
    PipelineConfigV3, aplicar_capacidad_instalada, aplicar_estrategia, aplicar_factor_cartera,
    aplicar_factor_cumplimiento_historico, aplicar_factor_tipo, aplicar_penalizacion_volatilidad, redondear_meta,
)

DEFAULT_PIPELINE_CONFIG = PipelineConfigV3()

logger = logging.getLogger("Backend.GoalMLService")


@dataclass
class SugerenciaMeta:
    vendedor_origen: str
    meta_sugerida_estadistica: float
    metodo_estadistico: str
    meses_historico_usados: int
    valores_atipicos_excluidos: int
    meses_atipicos_ml_detectados: int
    # Trazabilidad del cálculo de Venta Neta -> propuesta del período objetivo (motor v2,
    # docs/auditoria/46_motor_metas_configurable.md): permite al panel gerencial mostrar
    # por qué se sugirió el monto, no solo el número final.
    componente_estacional: float | None
    componente_tendencia: float
    factor_tendencia_aplicado: float
    coeficiente_variacion: float
    anio_objetivo: int = 0
    mes_objetivo: int = 0
    indice_estacional_aplicado: float = 1.0
    fuente_indice_estacional: str = "neutro"
    referencia_alcanzable: float = 0.0
    banda_actuo: bool = False
    meta_pre_banda: float = 0.0
    # Trazabilidad REAL persistida (H-5): si la meta ya fue generada y guardada, esto
    # trae la traza EXACTA que produjo `monto_meta` en `metas_comerciales_operativas`,
    # no un recálculo con la configuración de hoy. `False` cuando el valor mostrado es un
    # recálculo en vivo (metas legado sin `trazabilidad_calculo`, o consulta sin meta
    # generada todavía).
    es_trazabilidad_persistida: bool = False
    # Fase 6 (docs/features/plan_motor_metas_configurable.md §6, corrige H-7): unidades
    # ya pasan por el MISMO motor v2 (desestacionalización, IQR, banda de
    # alcanzabilidad) que el monto -- antes era "unidades del mes anterior × presión",
    # sin ninguna limpieza estadística.
    meta_unidades_estadistica: float = 0.0



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
        meta_motor_parametros: MetaMotorParametros = DEFAULT_PARAMETROS,
        pipeline_config: PipelineConfigV3 = DEFAULT_PIPELINE_CONFIG,
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
        # Configuración editable del motor v2 (docs/features/plan_motor_metas_
        # configurable.md §5.5) -- resuelta UNA VEZ por instancia (inyectada por
        # `app.api.dependencies` desde `MetaConfigService.get_motor_parametros()`), no
        # una consulta por vendedor.
        self.meta_motor_parametros = meta_motor_parametros
        # Etapas del pipeline v3 que no viven dentro de `IQRGoalCalculationEngine`
        # (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md §9/§18, Fase 6) --
        # resuelto UNA VEZ por instancia, mismo patrón que `meta_motor_parametros`.
        self.pipeline_config = pipeline_config
        # Índice estacional de empresa: se resuelve perezosamente (una sola consulta) y
        # se cachea para toda la vida de la instancia -- `generate_proposals` calcula
        # decenas de vendedores en el mismo lote y no debe repetir esta consulta agregada
        # por cada uno (mismo patrón de pre-resolución que `CommissionSimulationService`).
        self._indice_estacional_empresa_cache: dict[int, float] | None = None

    # ── Generación de metas (estadística pura sobre Venta Neta, sin ML) ────────────────
    def generate_proposals(self, anio: int, mes: int, factor_presion: float = 1.0) -> int:
        """Genera/actualiza las metas OFICIALES del período `anio`/`mes` (docs/auditoria/
        19_.../20_.../46_motor_metas_configurable.md): una fila por vendedor (no por
        vendedor×sucursal, ver `GoalRepository.get_vendors_with_recent_sales`), usando
        el motor v2 (`IQRGoalCalculationEngine`: nivel robusto desestacionalizado ×
        índice estacional (propio o de empresa) × tendencia reciente, acotado por una
        banda de alcanzabilidad sobre la meta final) -- sin ningún modelo ML (`goals_rf`
        decomisionado).

        **H-1 corregido (auditoría 46):** el período objetivo es SIEMPRE `(anio, mes)`,
        el que Gerencia pidió -- antes el motor lo inferí­a como "el mes siguiente al
        último dato disponible", que podía no coincidir con el período solicitado.

        `factor_presion` (el mismo slider de "presión comercial" que ya usaba el
        generador anterior) se pasa como `factor_crecimiento` del motor estadístico --
        mismo rol: empuje comercial adicional sobre la tendencia ya calculada.

        Ajuste por tipo de vendedor (docs/features/plan_integracion_comisiones_variables.md
        §2, brecha B1): si hay `commission_config_repo` disponible, la meta base se
        multiplica por `COMISION_META_FACTOR_EXTERNO`/`_INTERNO` según
        `comision_config_vendedor.tipo`; un vendedor "nuevo" (fecha_ingreso dentro de
        `COMISION_VENDEDOR_NUEVO_MESES`) recibe `COMISION_VENDEDOR_NUEVO_FACTOR` de la
        **mediana** del equipo (no el promedio -- H-6/escalera de degradación: un
        vendedor de volumen inusualmente alto no debe distorsionar la referencia de un
        vendedor nuevo) en vez de su propio histórico (insuficiente/inexistente)."""
        vendedores = list(self.goal_repo.get_vendors_with_recent_sales(anio, mes))

        # R-8/auditoría 47 A-0.4: vendedores activos que JAMÁS vendieron nada no aparecen
        # en `get_vendors_with_recent_sales` (exige venta el mes anterior) -- sin esto,
        # nunca entraban al lote y jamás recibían ninguna meta. Se agregan con
        # `unidades_anterior=0` y SIN pasar por `suggest_goal`/el motor IQR (que exige
        # histórico y lanzaría `ValidationError`); su meta se resuelve enteramente en
        # `_ajustar_meta_por_tipo` -> `ajustar_meta_por_madurez` con `meses_antiguedad=0`,
        # que ya devuelve el benchmark puro del equipo (peso propio = 0.0).
        codvens_con_venta_reciente = {t.vendedor_origen for t in vendedores}
        vendedores_sin_historico = {
            v for v in self.goal_repo.get_active_vendors_without_history()
            if v not in codvens_con_venta_reciente
        }
        for codven in vendedores_sin_historico:
            vendedores.append(VendorRecentSales(vendedor_origen=codven, unidades_anterior=0.0))

        sugerencias_por_vendedor: dict[str, SugerenciaMeta] = {}
        for t in vendedores:
            if t.vendedor_origen in vendedores_sin_historico:
                continue
            sugerencias_por_vendedor[t.vendedor_origen] = self.suggest_goal(
                t.vendedor_origen, anio, mes, factor_crecimiento=factor_presion,
                usar_trazabilidad_persistida=False,
            )

        montos_base = [s.meta_sugerida_estadistica for s in sugerencias_por_vendedor.values()]
        unidades_base = [s.meta_unidades_estadistica for s in sugerencias_por_vendedor.values()]
        mediana_equipo_monto = statistics.median(montos_base) if montos_base else 0.0
        mediana_equipo_unidades = statistics.median(unidades_base) if unidades_base else 0.0

        for codven in vendedores_sin_historico:
            sugerencias_por_vendedor[codven] = SugerenciaMeta(
                vendedor_origen=codven,
                meta_sugerida_estadistica=mediana_equipo_monto,
                metodo_estadistico=METODO_SIN_HISTORICO,
                meses_historico_usados=0,
                valores_atipicos_excluidos=0,
                meses_atipicos_ml_detectados=0,
                componente_estacional=None,
                componente_tendencia=1.0,
                factor_tendencia_aplicado=1.0,
                coeficiente_variacion=0.0,
                anio_objetivo=anio,
                mes_objetivo=mes,
                referencia_alcanzable=mediana_equipo_monto,
                meta_unidades_estadistica=mediana_equipo_unidades,
            )

        # E9/E13 comparten el mismo insumo real (cartera del vendedor, últimos 6 meses de
        # fact_ventas_detalle) -- se resuelve UNA vez por vendedor (no una vez por monto Y
        # por unidades) y solo si alguna de las dos etapas está activa, para no gastar una
        # consulta al EDW por vendedor cuando ambas están desactivadas (semilla).
        necesita_cartera = self.pipeline_config.capacidad_activa or self.pipeline_config.cartera_activa

        registros_afectados = 0
        for t in vendedores:
            sugerencia = sugerencias_por_vendedor[t.vendedor_origen]
            cartera = self.goal_repo.get_metricas_cartera_vendedor(t.vendedor_origen, anio, mes) if necesita_cartera else None
            cumplimiento_promedio = (
                self.goal_repo.get_cumplimiento_historico_promedio(t.vendedor_origen, anio, mes)
                if self.pipeline_config.cumplimiento_activo else None
            )
            meta_monto = self._ajustar_meta_por_tipo(
                t.vendedor_origen, sugerencia.meta_sugerida_estadistica, mediana_equipo_monto, anio, mes,
                sugerencia=sugerencia, cartera=cartera, cumplimiento_promedio=cumplimiento_promedio,
            )
            meta_unidades = self._ajustar_meta_por_tipo(
                t.vendedor_origen, sugerencia.meta_unidades_estadistica, mediana_equipo_unidades, anio, mes,
                sugerencia=sugerencia, cartera=cartera, cumplimiento_promedio=cumplimiento_promedio,
            )

            trazabilidad_json = json.dumps(self._trazabilidad_a_dict(sugerencia, meta_monto, meta_unidades))

            existing = self.goal_repo.find_proposal(anio, mes, t.vendedor_origen)
            if not existing:
                self.goal_repo.insert_proposal(anio, mes, t.vendedor_origen, meta_monto, meta_unidades, trazabilidad_json)
                registros_afectados += 1
            elif existing[1] == "PROPUESTA":
                self.goal_repo.update_proposal_amounts(existing[0], meta_monto, meta_unidades, trazabilidad_json)
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

    def _trazabilidad_a_dict(self, sugerencia: SugerenciaMeta, meta_monto_final: float, meta_unidades_final: float) -> dict:
        """Serializa la traza completa del cálculo (docs/auditoria/
        46_motor_metas_configurable.md, H-5) -- persistida junto a la meta para que "ver
        cómo se calculó" muestre los valores REALES que la produjeron, no un recálculo
        con la configuración de hoy. `meta_monto_final`/`meta_unidades_final` son el
        monto YA ajustado por tipo de vendedor (posterior a `meta_sugerida_estadistica`,
        que es la salida cruda del motor)."""
        d = dataclasses.asdict(sugerencia)
        d["meta_monto_final"] = round(meta_monto_final, 2)
        d["meta_unidades_final"] = round(meta_unidades_final, 2)
        # Fase 6 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md §20):
        # snapshot de la configuración modular TAL COMO ESTABA al generar -- "ver cómo se
        # calculó" debe mostrar la configuración real usada, no la de hoy (RN-MT5, mismo
        # principio que ya rige `es_trazabilidad_persistida`).
        d["version"] = "v3"
        d["config_snapshot"] = self.pipeline_config.config_snapshot
        return d

    def _ajustar_meta_por_tipo(
        self, vendedor_origen: str, meta_base: float, mediana_equipo: float, anio: int, mes: int,
        sugerencia: SugerenciaMeta, cartera: dict | None = None, cumplimiento_promedio: float | None = None,
    ) -> float:
        """Aplica, en orden, las etapas del pipeline v3 que no viven dentro de
        `IQRGoalCalculationEngine` (§18 del plan): E6 madurez, E7 estrategia, E8 tipo de
        vendedor, E9 capacidad instalada, E13 factor cartera, E15 cumplimiento histórico,
        E16 volatilidad, E11 redondeo (siempre último). Todas las etapas opcionales
        (E7/E9/E13/E15/E16) están desactivadas en la semilla -- activarlas es una
        decisión explícita de gerencia vía `/meta-config/modulos`.

        E6+E8: primero se mezcla la meta propia con el benchmark del equipo según cuánta
        historia real respalda a `meta_base` (`sugerencia.meses_historico_usados`, ya
        calculado por el motor v2), y DESPUÉS se aplica el factor de tipo externo/interno
        sobre el resultado ya mezclado -- nunca al revés, para no aplicar el ajuste de
        tipo sobre una meta que en realidad es 100% benchmark ajeno al propio vendedor.
        Reemplaza el escalón único anterior (cliff binario) por la transición gradual de
        `ajustar_meta_por_madurez`."""
        resultado_madurez = ajustar_meta_por_madurez(
            meta_propia=meta_base, benchmark_equipo=mediana_equipo,
            meses_antiguedad=sugerencia.meses_historico_usados,
            umbral_nuevo_meses=self.pipeline_config.umbral_nuevo_meses,
            umbral_maduro_meses=self.pipeline_config.umbral_maduro_meses,
            peso_propio_intermedio=self.pipeline_config.peso_propio_intermedio,
        )
        meta = resultado_madurez.meta_ajustada

        # E7 -- objetivo estratégico de la empresa (§18-E7): desactivado en la semilla,
        # pendiente de que gerencia defina un % de crecimiento (§17.4 del plan).
        if self.pipeline_config.estrategia_activa:
            meta = aplicar_estrategia(meta, self.pipeline_config.crecimiento_pct)

        # E8 -- factor por tipo de vendedor (§18-E8): absorbe la tabla que antes vivía
        # como `COMISION_META_FACTOR_EXTERNO`/`_INTERNO` leída directo de `settings` --
        # ahora la fuente única es la etapa E8 de `metas_config_modulos` (auditoría 46
        # H-10: un factor aplicándose en dos sitios a la vez ya causó un bug real).
        if self.commission_config_repo is not None:
            config_vendedor = self.commission_config_repo.get_config_vendedor(
                vendedor_origen, fecha_referencia_periodo(anio, mes)
            )
            tipo = config_vendedor.tipo if config_vendedor else "externo"
            meta = aplicar_factor_tipo(meta, tipo, self.pipeline_config.factores_tipo_vendedor)

        # E9 -- capacidad instalada (§18-E9): tope duro con la cartera REAL del vendedor
        # (últimos 6 meses de fact_ventas_detalle, `GoalRepository.
        # get_metricas_cartera_vendedor`) -- sin cartera medible (vendedor nuevo,
        # mostrador sin clientes identificados) la etapa se omite por diseño propio de
        # `aplicar_capacidad_instalada`, nunca aplica un tope de 0.
        if self.pipeline_config.capacidad_activa and cartera is not None:
            meta = aplicar_capacidad_instalada(
                meta, cartera["clientes_activos_mes"], cartera["ticket_promedio"],
                cartera["frecuencia_compra_mensual"], holgura=self.pipeline_config.capacidad_holgura,
            ).meta_ajustada

        # E13 -- factor cartera activa (§18-E13): mismos insumos reales que E9 --
        # compara el mes más reciente contra el promedio de la ventana, acotado a un
        # rango estrecho (nunca deja que un cambio de cartera por sí solo duplique o
        # anule la meta).
        if self.pipeline_config.cartera_activa and cartera is not None:
            meta = aplicar_factor_cartera(
                meta, cartera["clientes_activos_mes"], cartera["promedio_clientes_activos_ventana"],
                factor_min=self.pipeline_config.cartera_factor_min, factor_max=self.pipeline_config.cartera_factor_max,
            )

        # E15 -- factor de cumplimiento histórico (§18-E15): promedio REAL de venta/meta
        # de los últimos meses del propio vendedor (`GoalRepository.
        # get_cumplimiento_historico_promedio`) -- `None` (sin histórico comparable) deja
        # la etapa neutra por diseño de `aplicar_factor_cumplimiento_historico`.
        if self.pipeline_config.cumplimiento_activo:
            meta = aplicar_factor_cumplimiento_historico(
                meta, cumplimiento_promedio, peso=self.pipeline_config.cumplimiento_peso,
            )

        # E16 -- penalización por volatilidad (§18-E16): reduce el componente de
        # CRECIMIENTO ya calculado por el motor v2 (`sugerencia.factor_tendencia_
        # aplicado`) cuando la serie del vendedor es muy errática (`sugerencia.
        # coeficiente_variacion`), reescalando la meta por la razón entre el factor
        # penalizado y el original -- nunca recalcula la tendencia desde cero.
        if self.pipeline_config.volatilidad_activa and sugerencia.factor_tendencia_aplicado > 0:
            factor_ajustado = aplicar_penalizacion_volatilidad(
                sugerencia.factor_tendencia_aplicado, sugerencia.coeficiente_variacion,
                umbral_cv=self.pipeline_config.volatilidad_umbral_cv,
                factor_reduccion=self.pipeline_config.volatilidad_factor_reduccion,
            )
            meta = meta * (factor_ajustado / sugerencia.factor_tendencia_aplicado)

        # E11 -- redondeo (§18-E11): siempre el último paso del pipeline.
        meta = redondear_meta(meta, self.pipeline_config.redondeo_multiplo, self.pipeline_config.redondeo_modo)
        return round(meta, 2)

    def _get_indice_estacional_empresa(self) -> dict[int, float]:
        if self._indice_estacional_empresa_cache is None:
            self._indice_estacional_empresa_cache = self.goal_repo.get_indice_estacional_empresa()
        return self._indice_estacional_empresa_cache

    def suggest_goal(
        self, vendedor_origen: str, anio_objetivo: int | None = None, mes_objetivo: int | None = None,
        factor_estacional: float = 1.0, factor_crecimiento: float = 1.0,
        usar_trazabilidad_persistida: bool = True,
    ) -> SugerenciaMeta:
        """Calcula la meta sugerida para `(anio_objetivo, mes_objetivo)` -- si se omiten
        (compatibilidad con llamadores que solo quieren "la próxima meta razonable"),
        el motor cae a su comportamiento legado (mes siguiente al último dato).

        `usar_trazabilidad_persistida=False` fuerza un recálculo fresco incluso si ya
        existe una meta guardada para ese período -- usado por `generate_proposals`
        (regenerar SIEMPRE debe reflejar el histórico/configuración actuales, nunca
        reciclar una traza vieja); el valor `True` por defecto es para el endpoint de
        lectura ("ver cómo se calculó"), que debe mostrar los valores REALES que
        produjeron la meta ya persistida (H-5), no un recálculo con datos de hoy."""
        hist = self.goal_repo.get_vendor_monthly_history(vendedor_origen)
        if not hist:
            raise ValidationError(f"Sin histórico de ventas para vendedor={vendedor_origen}.")

        registros = [RegistroMensual(anio=h.anio, mes=h.mes, ventas=h.ventas, unidades=h.unidades) for h in hist]

        resultado = self.calculation_engine.calcular(
            vendedor_origen, registros, anio_objetivo, mes_objetivo, factor_estacional, factor_crecimiento,
            indice_estacional_empresa=self._get_indice_estacional_empresa(),
            parametros=self.meta_motor_parametros,
            aplicar_limpieza=self.pipeline_config.aplicar_limpieza,
            aplicar_estacionalidad=self.pipeline_config.aplicar_estacionalidad,
            aplicar_tendencia=self.pipeline_config.aplicar_tendencia,
            aplicar_estabilidad=self.pipeline_config.aplicar_estabilidad,
            aplicar_banda=self.pipeline_config.aplicar_banda,
        )

        trazabilidad_persistida = None
        if usar_trazabilidad_persistida and anio_objetivo is not None and mes_objetivo is not None:
            trazabilidad_persistida = self.goal_repo.get_trazabilidad(anio_objetivo, mes_objetivo, vendedor_origen)

        if trazabilidad_persistida:
            return SugerenciaMeta(
                vendedor_origen=vendedor_origen,
                meta_sugerida_estadistica=trazabilidad_persistida.get("meta_sugerida_estadistica", resultado.meta_ventas_total),
                metodo_estadistico=trazabilidad_persistida.get("metodo_estadistico", resultado.metodo),
                meses_historico_usados=trazabilidad_persistida.get("meses_historico_usados", resultado.meses_historico_usados),
                valores_atipicos_excluidos=trazabilidad_persistida.get("valores_atipicos_excluidos", resultado.valores_atipicos_excluidos),
                meses_atipicos_ml_detectados=trazabilidad_persistida.get("meses_atipicos_ml_detectados", resultado.meses_atipicos_ml_detectados),
                componente_estacional=trazabilidad_persistida.get("componente_estacional", resultado.componente_estacional),
                componente_tendencia=trazabilidad_persistida.get("componente_tendencia", resultado.componente_tendencia),
                factor_tendencia_aplicado=trazabilidad_persistida.get("factor_tendencia_aplicado", resultado.factor_tendencia_aplicado),
                coeficiente_variacion=trazabilidad_persistida.get("coeficiente_variacion", resultado.coeficiente_variacion),
                anio_objetivo=trazabilidad_persistida.get("anio_objetivo", resultado.anio_objetivo),
                mes_objetivo=trazabilidad_persistida.get("mes_objetivo", resultado.mes_objetivo),
                indice_estacional_aplicado=trazabilidad_persistida.get("indice_estacional_aplicado", resultado.indice_estacional_aplicado),
                fuente_indice_estacional=trazabilidad_persistida.get("fuente_indice_estacional", resultado.fuente_indice_estacional),
                referencia_alcanzable=trazabilidad_persistida.get("referencia_alcanzable", resultado.referencia_alcanzable),
                banda_actuo=trazabilidad_persistida.get("banda_actuo", resultado.banda_actuo),
                meta_pre_banda=trazabilidad_persistida.get("meta_pre_banda", resultado.meta_pre_banda),
                es_trazabilidad_persistida=True,
                meta_unidades_estadistica=trazabilidad_persistida.get("meta_unidades_estadistica", resultado.meta_unidades_total),
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
            anio_objetivo=resultado.anio_objetivo,
            mes_objetivo=resultado.mes_objetivo,
            indice_estacional_aplicado=resultado.indice_estacional_aplicado,
            fuente_indice_estacional=resultado.fuente_indice_estacional,
            referencia_alcanzable=resultado.referencia_alcanzable,
            banda_actuo=resultado.banda_actuo,
            meta_pre_banda=resultado.meta_pre_banda,
            es_trazabilidad_persistida=False,
            meta_unidades_estadistica=resultado.meta_unidades_total,
        )

    # ── Recomendación comercial ────────────────────────────────────────────────
    def get_commercial_recommendations(self, vendedor_origen: str, top_n: int = 5) -> list[RecomendacionComercial]:
        top_productos = self.goal_repo.get_vendor_top_products(vendedor_origen, limit=10)
        if not top_productos:
            return []
        recs_df = inference.get_recommendations(self.model_loader, top_productos, top_n=top_n)
        return [RecomendacionComercial(producto_cod=str(row["item_B"]), score_afinidad=float(row["score"])) for _, row in recs_df.iterrows()]

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
