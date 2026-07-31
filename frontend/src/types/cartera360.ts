// Tipos del módulo Ventas — Cartera de Clientes 360
// (docs/features/propuesta_nuevos_modulos_roi.md §4, auditoría 32)
// Contratos de backend/app/schemas/cartera360.py

/** activo / inactivo / potencial -- derivado en el backend de `dias_sin_comprar` real
 * (umbrales `CARTERA360_DIAS_*`, `Cartera360Service._estado_cartera`), nunca recalculado
 * en el frontend. */
export type EstadoCartera = 'activo' | 'inactivo' | 'potencial';

export interface ClienteListaTrabajo {
  cliente_id: string;
  nombre_cliente: string;
  num_compras: number;
  /** ISO date (YYYY-MM-DD), `null` si el cliente no tiene compras registradas. */
  ultima_compra: string | null;
  dias_sin_comprar: number;
  valor_historico: number;
  frecuencia_promedio_dias: number | null;
  alerta_caida_frecuencia: boolean;
  /** Churn real del modelo (churn_rf), 0-100. Ya viene calculado en la lista de trabajo. */
  probabilidad_abandono: number;
  /** CHURN_UMBRAL_RIESGO_ALTO ya evaluado en el backend -- filtrar por esto, no por un umbral duplicado en el frontend. */
  riesgo_alto: boolean;
  prioridad: number;
  estado_cartera: EstadoCartera;
}

export interface ListaTrabajo {
  clientes: ClienteListaTrabajo[];
}

export interface ProductoRecomendadoCliente {
  producto_cod: string;
  score: number;
}

export interface DetalleCliente {
  cliente_id: string;
  probabilidad_abandono: number;
  riesgo_alto: boolean;
  segmento: number;
  nombre_segmento: string;
  productos_recomendados: ProductoRecomendadoCliente[];
}

export type EventoGestion = 'contactado' | 'recompro' | 'perdido';

export interface RegistrarGestionRequest {
  cliente_id: string;
  evento: EventoGestion;
  motivo?: string | null;
}

export interface RegistrarGestionResponse {
  id: number;
  evento: string;
}

export interface TasaRecuperacion {
  total_gestiones: number;
  recompras: number;
  tasa_recuperacion_pct: number;
}

// ── "Mi Ruta Inteligente de Ventas" ────────────────────────────────────────
// (docs/features/plan_refactor_cartera360_ruta_inteligente.md)
// Contratos de backend/app/schemas/cartera360.py (sección "Mi Ruta Inteligente")

export interface TarjetasHeader {
  clientes_asignados: number;
  clientes_con_alerta: number;
  clientes_recuperados_mes: number;
  ingreso_potencial_en_riesgo: number;
  oportunidades_activas: number;
  /** Reemplaza "Valor esperado del día" (DEC-3): suma real de ticket_promedio, etiquetado como potencial, no esperado. */
  valor_potencial_ruta_hoy: number;
  /** null si el vendedor no tiene meta mensual generada para el período actual. */
  objetivo_diario: number | null;
  avance_dia: number;
}

export interface ScoreDesglose {
  valor_historico: number;
  probabilidad_abandono: number;
}

export interface OfertaSugerida {
  codart: string;
  nombre: string;
  precio: number;
  motivo: string;
}

export type CodigoAlerta = 'riesgo_critico' | 'riesgo_medio' | 'estable' | 'oportunidad' | 'premium' | 'crecimiento';

export interface ClasificacionAlerta {
  codigo: CodigoAlerta;
  etiqueta: string;
}

export interface ClienteRuta {
  cliente_id: string;
  nombre_cliente: string;
  prioridad: number;
  score_desglose: ScoreDesglose;
  /** DEC-3A: 100 - probabilidad_abandono de churn_rf. Reemplaza "probabilidad de cierre" (sin fuente real). */
  probabilidad_recompra: number;
  dias_sin_comprar: number;
  frecuencia_promedio_dias: number | null;
  tiempo_restante_dias: number | null;
  valor_historico: number;
  motivo: string;
  clasificacion: ClasificacionAlerta;
  oferta_sugerida: OfertaSugerida | null;
  ultima_gestion_evento: string | null;
  ultima_gestion_fecha: string | null;
  proxima_accion_fecha: string | null;
}

export interface RutaHoy {
  tarjetas: TarjetasHeader;
  clientes: ClienteRuta[];
}

/** Auditoría 43 (H43-13): agenda propia del vendedor, independiente del top-N de
 * `/ruta/hoy` -- ese ranking excluye deliberadamente a estos mismos clientes mientras la
 * fecha siga vigente (rotación de la ruta). */
export type EstadoProximaAccion = 'vencida' | 'hoy' | 'proxima';

export interface ProximaAccion {
  cliente_id: string;
  nombre_cliente: string;
  ultimo_evento: string;
  ultima_gestion_fecha: string;
  proxima_accion_fecha: string;
  estado: EstadoProximaAccion;
}

export interface ProximasAcciones {
  acciones: ProximaAccion[];
}

export type EventoGestionRuta =
  | 'contactado' | 'recompro' | 'perdido'
  | 'no_contesto' | 'reagendado' | 'interesado_sin_cierre' | 'objecion_precio' | 'objecion_stock';

export type CanalGestion = 'llamada' | 'whatsapp' | 'email' | 'visita';

export interface RegistrarGestionRutaRequest {
  cliente_id: string;
  evento: EventoGestionRuta;
  canal?: CanalGestion | null;
  resultado?: string | null;
  proxima_accion_fecha?: string | null;
  nota?: string | null;
}

export interface RegistrarGestionRutaResponse {
  id: number;
  evento: string;
  canal: string | null;
  fecha: string;
}

export type TipoEventoTimeline = 'compra' | 'devolucion' | 'cobro' | 'gestion';

export interface TimelineEvento {
  tipo: TipoEventoTimeline;
  fecha: string;
  descripcion: string;
  monto: number | null;
  evento_gestion?: string | null;
}

export interface TimelineCliente {
  cliente_id: string;
  eventos: TimelineEvento[];
}

export interface EfectividadPorCanal {
  canal: string;
  contactados: number;
  ventas: number;
  conversion_pct: number;
}

export interface EfectividadComercial {
  /** false = estado vacío real (D-1: menos de CARTERA360_MIN_GESTIONES_EFECTIVIDAD gestiones), nunca una tasa sobre muestra insuficiente. */
  tiene_datos: boolean;
  total_gestiones: number;
  total_ventas_atribuidas: number;
  conversion_pct: number | null;
  tiempo_promedio_cierre_dias: number | null;
  ingresos_atribuidos: number | null;
  por_canal: EfectividadPorCanal[];
}

export interface PlanDia {
  dia: string;
  cupo: number;
  clientes: string[];
}

export interface PlanSemanal {
  dias: PlanDia[];
}
