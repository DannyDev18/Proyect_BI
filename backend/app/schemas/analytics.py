# backend/app/schemas/analytics.py
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class GPKPIGerencia(BaseModel):
    # Calculado en SQL (AnalyticsRepository.get_management_kpis, `total_sales`) --
    # docs/auditoria/33_actualizacion_modulo_gerencia.md, H2: antes el servicio lo
    # descartaba y el frontend lo reconstruía sumando `ventas_por_sucursal`, una fuente
    # que excluye sucursales con neto exactamente 0 y podía divergir del total real.
    ingresos_totales: float
    margen_utilidad_neta: float
    ticket_promedio: float
    roi_estimado: float
    ventas_por_sucursal: Dict[str, float]
    ventas_por_vendedor: Optional[Dict[str, float]] = None

class BPKPIBodega(BaseModel):
    items_sobrestock: int
    items_riesgo_desabasto: int
    transferencias_recomendadas: List[Dict[str, Any]]

class VPKPIVentas(BaseModel):
    meta_mensual: float
    cumplimiento_actual: float
    meta_proyectada: float
    ranking_vendedores: List[Dict[str, Any]]

# Respuestas para llamadas directas de Inferencia
class MetricasPrediccion(BaseModel):
    # Todos opcionales: cuando la serie filtrada (vendedor/almacén/sucursal) queda vacía o
    # la inferencia falla, el servicio degrada con gracia devolviendo metricas={} -- con
    # campos obligatorios eso explotaba en la validación de la respuesta (500) en vez de
    # llegar al frontend como "sin datos" (hallazgo de la verificación del doc 22).
    ventas_acumuladas: Optional[float] = None
    venta_esperada: Optional[float] = None
    crecimiento_esperado: Optional[float] = None
    mes_mayor_venta: Optional[str] = None
    mes_menor_venta: Optional[str] = None
    promedio_mensual: Optional[float] = None
    mae_modelo: Optional[float] = None
    # r2_modelo sí lo calcula el servicio (H-09, del sidecar real) pero el schema lo
    # omitía y Pydantic lo filtraba de la respuesta.
    r2_modelo: Optional[float] = None
    nivel_confianza: Optional[float] = None
    fecha_entrenamiento: Optional[str] = None
    algoritmo: Optional[str] = None

class PrediccionVentasResponse(BaseModel):
    granularidad: str
    periodos_proyectados: int
    historial_y_prediccion: List[Dict[str, Any]]
    metricas: MetricasPrediccion
    insights: List[str]

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

class AnomaliaResponse(BaseModel):
    transaccion_id: str
    score: float
    es_anomalia: bool

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
class ForecastCierreResponse(BaseModel):
    sucursal: str
    dias_restantes: int
    ventas_mes_actual: float
    proyeccion_cierre: float
    meta: float
    pct_cumplimiento_esperado: float
    probabilidad_alcanzar_meta: Optional[float] = None
    mae_modelo: Optional[float] = None

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

class RecomendacionComercialItem(BaseModel):
    producto_cod: str
    score_afinidad: float

class RecomendacionesComercialesResponse(BaseModel):
    vendedor_origen: str
    recomendaciones: List[RecomendacionComercialItem]
