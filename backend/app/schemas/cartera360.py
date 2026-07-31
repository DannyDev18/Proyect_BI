# backend/app/schemas/cartera360.py
"""Esquemas del módulo Ventas — Cartera de Clientes 360
(docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32)."""
import datetime

from pydantic import BaseModel


class ClienteListaTrabajo(BaseModel):
    cliente_id: str
    nombre_cliente: str
    num_compras: int
    ultima_compra: datetime.date | None
    dias_sin_comprar: int
    valor_historico: float
    frecuencia_promedio_dias: float | None
    alerta_caida_frecuencia: bool
    # Churn real del modelo (no la señal estadística de alerta_caida_frecuencia, que solo
    # se usa para armar el shortlist barato -- ver Cartera360Service.get_lista_trabajo).
    probabilidad_abandono: float
    # Umbral CHURN_UMBRAL_RIESGO_ALTO ya evaluado en el backend (plan_actualizacion_modulo_ventas.md
    # Fase 2 "churn accionable"): permite filtrar "solo riesgo alto" en la UI sin duplicar
    # el umbral como número mágico en el frontend.
    riesgo_alto: bool
    prioridad: float
    # Fase 4 §4.2 (docs/features/plan_correcciones_integrales_sistema.md): activo/inactivo/
    # potencial derivado de `dias_sin_comprar` real, umbrales en settings.CARTERA360_DIAS_*.
    estado_cartera: str


class ListaTrabajoResponse(BaseModel):
    clientes: list[ClienteListaTrabajo]


class ProductoRecomendadoCliente(BaseModel):
    producto_cod: str
    score: float


class DetalleClienteResponse(BaseModel):
    cliente_id: str
    probabilidad_abandono: float
    riesgo_alto: bool
    segmento: int
    nombre_segmento: str
    productos_recomendados: list[ProductoRecomendadoCliente]


class RegistrarGestionRequest(BaseModel):
    cliente_id: str
    evento: str
    motivo: str | None = None


class RegistrarGestionResponse(BaseModel):
    id: int
    evento: str


class TasaRecuperacionResponse(BaseModel):
    total_gestiones: int
    recompras: int
    tasa_recuperacion_pct: float


# ── "Mi Ruta Inteligente de Ventas" (docs/features/plan_refactor_cartera360_ruta_
# inteligente.md). Contratos nuevos bajo /ruta/*, conviviendo con los de arriba
# (§7 Estrategia de migración: los endpoints /cartera360/* no cambian). R-0: todo campo
# aquí tiene fuente real documentada -- ningún placeholder.

class TarjetasHeaderResponse(BaseModel):
    clientes_asignados: int
    clientes_con_alerta: int
    clientes_recuperados_mes: int
    ingreso_potencial_en_riesgo: float
    oportunidades_activas: int
    valor_potencial_ruta_hoy: float  # Reemplaza "Valor esperado del día" (DEC-3, §4.1) -- suma real de ticket_promedio
    objetivo_diario: float | None  # None si no hay meta mensual generada para el vendedor
    avance_dia: float


class ScoreDesglose(BaseModel):
    """El score final es un PRODUCTO (valor_historico * (1 + p_abandono/100)), nunca una
    suma -- el frontend debe renderizar 2 medidores independientes, no una barra apilada
    aditiva (mismo criterio que ScoreDecompositionBar de Venta Cruzada Fase 5)."""
    valor_historico: float
    probabilidad_abandono: float


class OfertaSugerida(BaseModel):
    codart: str
    nombre: str
    precio: float
    motivo: str


class ClasificacionAlerta(BaseModel):
    codigo: str  # riesgo_critico | riesgo_medio | estable | oportunidad | premium | crecimiento
    etiqueta: str


class ClienteRuta(BaseModel):
    cliente_id: str
    nombre_cliente: str
    prioridad: float
    score_desglose: ScoreDesglose
    probabilidad_recompra: float  # DEC-3A: 100 - probabilidad_abandono de churn_rf
    dias_sin_comprar: int
    frecuencia_promedio_dias: float | None
    tiempo_restante_dias: float | None  # frecuencia_promedio_dias - dias_sin_comprar (puede ser negativo: ya venció su ciclo)
    valor_historico: float
    motivo: str  # plantilla determinista sobre señales reales (§4.2)
    clasificacion: ClasificacionAlerta
    oferta_sugerida: OfertaSugerida | None
    ultima_gestion_evento: str | None
    ultima_gestion_fecha: str | None
    proxima_accion_fecha: str | None


class RutaHoyResponse(BaseModel):
    tarjetas: TarjetasHeaderResponse
    clientes: list[ClienteRuta]


class RegistrarGestionRutaRequest(BaseModel):
    cliente_id: str
    evento: str
    canal: str | None = None
    resultado: str | None = None
    proxima_accion_fecha: str | None = None  # ISO date, opcional
    nota: str | None = None


class RegistrarGestionRutaResponse(BaseModel):
    id: int
    evento: str
    canal: str | None
    fecha: str


class TimelineEvento(BaseModel):
    tipo: str  # compra | devolucion | cobro | gestion
    fecha: str
    descripcion: str
    monto: float | None = None
    evento_gestion: str | None = None  # solo si tipo == "gestion"


class TimelineClienteResponse(BaseModel):
    cliente_id: str
    eventos: list[TimelineEvento]


class EfectividadPorCanal(BaseModel):
    canal: str
    contactados: int
    ventas: int
    conversion_pct: float


class EfectividadComercialResponse(BaseModel):
    tiene_datos: bool  # False si total_gestiones < CARTERA360_MIN_GESTIONES_EFECTIVIDAD (RN-CS5: estado vacío real)
    total_gestiones: int
    total_ventas_atribuidas: int
    conversion_pct: float | None
    tiempo_promedio_cierre_dias: float | None
    ingresos_atribuidos: float | None
    por_canal: list[EfectividadPorCanal]


class PlanDia(BaseModel):
    dia: str  # lunes..viernes
    cupo: int
    clientes: list[str]  # cliente_id, subconjunto de la ruta del día ya calculada


class PlanSemanalResponse(BaseModel):
    dias: list[PlanDia]


class ProximaAccion(BaseModel):
    """Auditoría 43 (H43-13, docs/auditoria/43_correcciones_sesion_ventas_y_datos.md):
    agenda propia del vendedor, independiente del top-N de `/ruta/hoy` -- ese ranking
    EXCLUYE deliberadamente a estos mismos clientes (rotación de la ruta), así que la
    fuente tiene que ser un endpoint aparte, no un filtro sobre `/ruta/hoy`."""
    cliente_id: str
    nombre_cliente: str
    ultimo_evento: str
    ultima_gestion_fecha: str
    proxima_accion_fecha: str
    estado: str  # "vencida" | "hoy" | "proxima"


class ProximasAccionesResponse(BaseModel):
    acciones: list[ProximaAccion]
