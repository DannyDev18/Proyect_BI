# backend/app/schemas/analytics.py
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# Reutilizado del contrato tipado de reportes de Bodega (Fase 5, docs/features/
# plan_actualizacion_modulo_bodega.md §5.2) -- Fase 2 Gerencia (docs/features/
# plan_correcciones_pendientes.md §3): "no duplicar exportadores", así que el reporte
# del dashboard de Gerencia usa exactamente el mismo contrato/exportador Excel
# (`warehouse_export.reporte_a_excel`) en vez de inventar uno nuevo.
from app.schemas.warehouse import KpiResumenEjecutivo, ReporteBodegaResponse as ReporteDashboardResponse, SeccionReporte  # noqa: F401,E501

class GPKPIGerencia(BaseModel):
    # Calculado en SQL (AnalyticsRepository.get_management_kpis, `total_sales`) --
    # docs/auditoria/33_actualizacion_modulo_gerencia.md, H2: antes el servicio lo
    # descartaba y el frontend lo reconstruía sumando `ventas_por_sucursal`, una fuente
    # que excluye sucursales con neto exactamente 0 y podía divergir del total real.
    ingresos_totales: float
    margen_utilidad_neta: float
    ticket_promedio: float
    # docs/auditoria/39_madurez_bi_toma_decisiones.md, H-02: reemplaza a `roi_estimado`
    # (`margen * 1.15`, una constante sin regla de negocio). RN-BI2: retorno sobre costo de
    # mercadería vendida. `None` cuando no hay costo con el que comparar -- el frontend
    # debe comunicar "sin base de cálculo", no 0%.
    roi_real: Optional[float] = None
    costo_mercaderia: float = 0.0
    ventas_por_sucursal: Dict[str, float]
    ventas_por_vendedor: Optional[Dict[str, float]] = None
    # Fase 2 Gerencia (docs/features/plan_correcciones_pendientes.md §3): comparativa vs.
    # período anterior de igual longitud -- None cuando no hay start_date/end_date
    # explícitos (vista "todo el histórico", sin período previo con el que comparar).
    ingresos_totales_tendencia_pct: Optional[float] = None
    margen_utilidad_neta_tendencia_pct: Optional[float] = None
    ticket_promedio_tendencia_pct: Optional[float] = None
    roi_real_tendencia_pct: Optional[float] = None
    # G-04 (docs/features/plan_madurez_bi_toma_decisiones.md): contexto de la comparación --
    # contra qué período se comparan las tendencias y, si alguna vino en None, por qué no
    # hubo base de cálculo. `None` cuando no se pidieron fechas explícitas.
    comparacion: Optional["ContextoComparacion"] = None


class ContextoComparacion(BaseModel):
    """Metadatos de la comparación temporal aplicada a los KPIs (G-04)."""
    modo: str
    desde_referencia: str
    hasta_referencia: str
    periodos_promediados: int
    # Motivos por los que una tendencia concreta no tiene base comparable. El criterio de
    # aceptación de G-04 exige comunicarlo, no mostrar 0%.
    sin_base: Optional[List[str]] = None

class BPKPIBodega(BaseModel):
    items_sobrestock: int
    items_riesgo_desabasto: int
    transferencias_recomendadas: List[Dict[str, Any]]

# Reemplaza al panel "Histórico y Predicción de Ventas (ML)" (auditoría 49, decomisión de
# `sales_rf`): Venta Neta real mes a mes, sin ningún modelo -- el gráfico del frontend
# (barras + línea de promedio móvil, aritmética simple sobre esta misma serie) es el
# análisis honesto que reemplaza a la predicción retirada.
class EvolucionMensualVentasItem(BaseModel):
    anio: int
    mes: int
    venta_neta: float

class EvolucionMensualVentasResponse(BaseModel):
    serie: List[EvolucionMensualVentasItem]

class VPKPIVentas(BaseModel):
    meta_mensual: float
    cumplimiento_actual: float
    meta_proyectada: float
    ranking_vendedores: List[Dict[str, Any]]

# Respuestas para llamadas directas de Inferencia
# (`MetricasPrediccion`/`PrediccionVentasResponse` -- panel ML de predicción de ventas --
# se retiraron junto con `sales_rf`, auditoría 49. Ver `EvolucionMensualVentasResponse`
# más abajo, su reemplazo: histórico real, sin ningún modelo.)
class PrediccionDemandaResponse(BaseModel):
    producto_cod: str
    demanda_proxima_semana: float

class SegmentacionClienteResponse(BaseModel):
    cliente_id: str
    segmento: int
    nombre_segmento: str

class ChurnResponse(BaseModel):
    cliente_id: str
    probabilidad_abandono: float
    riesgo_alto: bool

class AuditLogEntryResponse(BaseModel):
    ts: str
    level: str
    source: str
    msg: str

class RecomendacionProducto(BaseModel):
    producto_cod: str
    score: float

class RecomendacionResponse(BaseModel):
    cliente_id: str
    recomendaciones: List[RecomendacionProducto]

# ── Integración ML: Metas y Comisiones (docs/auditoria/15_...) ──────────────────────
# (`ForecastCierreResponse` -- "Pronóstico de cierre" del vendedor -- se retiró junto con
# `sales_rf`, auditoría 49: dependía 100% de ese modelo vía el mismo walk-forward.)
class MetaSugeridaResponse(BaseModel):
    vendedor_origen: str
    meta_sugerida_estadistica: float
    metodo_estadistico: str
    meses_historico_usados: int
    valores_atipicos_excluidos: int
    meses_atipicos_ml_detectados: int
    componente_estacional: Optional[float] = None
    componente_tendencia: float
    factor_tendencia_aplicado: float
    coeficiente_variacion: float
    # Motor v2 (docs/auditoria/46_motor_metas_configurable.md, plan_motor_metas_configurable.md):
    anio_objetivo: int = 0
    mes_objetivo: int = 0
    indice_estacional_aplicado: float = 1.0
    fuente_indice_estacional: str = "neutro"
    referencia_alcanzable: float = 0.0
    banda_actuo: bool = False
    meta_pre_banda: float = 0.0
    meta_unidades_estadistica: float = 0.0
    # `True` cuando estos valores son la traza REAL persistida junto a la meta ya
    # generada (H-5); `False` cuando son un recálculo en vivo (meta legado sin
    # trazabilidad, o consulta sin meta generada todavía para ese período).
    es_trazabilidad_persistida: bool = False

class RecomendacionComercialItem(BaseModel):
    producto_cod: str
    score_afinidad: float

class RecomendacionesComercialesResponse(BaseModel):
    vendedor_origen: str
    recomendaciones: List[RecomendacionComercialItem]
