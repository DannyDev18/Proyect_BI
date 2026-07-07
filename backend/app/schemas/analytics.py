# backend/app/schemas/analytics.py
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class GPKPIGerencia(BaseModel):
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
    ventas_acumuladas: float
    venta_esperada: float
    crecimiento_esperado: float
    mes_mayor_venta: str
    mes_menor_venta: str
    promedio_mensual: float
    mae_modelo: float
    nivel_confianza: float
    fecha_entrenamiento: str

class PrediccionVentasResponse(BaseModel):
    horizonte: str
    dias_proyectados: int
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

class RecomendacionProducto(BaseModel):
    producto_cod: str
    score: float

class RecomendacionResponse(BaseModel):
    cliente_id: str
    recomendaciones: List[RecomendacionProducto]
