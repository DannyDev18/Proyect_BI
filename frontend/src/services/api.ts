import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ─── Axios Instance ───────────────────────────────────────────────────────────
export const api = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      if (window.location.pathname !== '/login') window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ─── TypeScript Interfaces (mirrors backend schemas) ───────────────────────
export interface GerenciaKPIs {
  ventas_consolidadas?: number;
  ticket_promedio: number;
  margen_utilidad_neta: number;
  roi_estimado: number;
  ventas_por_sucursal: Record<string, number>;
  ventas_por_vendedor?: Record<string, number>;
}

export interface MetricasPrediccion {
  ventas_acumuladas: number;
  venta_esperada: number;
  crecimiento_esperado: number;
  mes_mayor_venta: string;
  mes_menor_venta: string;
  promedio_mensual: number;
  mae_modelo: number;
  nivel_confianza: number;
  fecha_entrenamiento: string;
}

export interface SalesPredictionPoint {
  fecha: string;
  monto_real?: number;
  monto_predicho?: number;
  intervalo_inferior?: number;
  intervalo_superior?: number;
}

export interface SalesPredictionResponse {
  horizonte: string;
  dias_proyectados: number;
  historial_y_prediccion: SalesPredictionPoint[];
  metricas: MetricasPrediccion;
  insights: string[];
}

export interface BodegaKPIs {
  items_riesgo_desabastecimiento: number;
  items_sobrestock: number;
  valorizacion_inventario: number;
  rotacion_mensual: number;
  alertas_criticas?: number;
}

export interface DemandaResponse {
  producto_cod: string;
  demanda_proxima_semana: number;
}

export interface VentasKPIs {
  meta_mensual: number;
  ventas_actuales: number;
  cumplimiento_pct: number;
  clientes_activos: number;
  churn_promedio?: number;
}

export interface ChurnResponse {
  cliente_id: string;
  probabilidad_abandono: number;
  riesgo_alto: boolean;
}

export interface RecomendacionResponse {
  cliente_id: string;
  recomendaciones: RecommendedProduct[];
}

export interface RecommendedProduct {
  producto_cod: string;
  nombre?: string;
  confianza?: number;
  lift?: number;
}

export interface SegmentacionResponse {
  cliente_id: string;
  segmento: number;
  nombre_segmento: string;
}

export interface AnomaliaResponse {
  transaccion_id: string;
  score: number;
  es_anomalia: boolean;
}

// ─── Auth y Usuarios (Admin) ──────────────────────────────────────────────────
export const authLogin = (email: string, password: string) =>
  api.post('/api/v1/auth/login', { username: email, password }, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  });

export const getMe = () => 
  api.get('/api/v1/users/me');

export const getRoles = () => 
  api.get('/api/v1/roles/');

export const getUsers = () => 
  api.get('/api/v1/users/');

export const createUser = (data: any) => 
  api.post('/api/v1/users/', data);

export const updateUser = (id: number, data: any) => 
  api.put(`/api/v1/users/${id}`, data);

export const deactivateUser = (id: number) => 
  api.delete(`/api/v1/users/${id}`);

export const activateUser = (id: number) => 
  api.post(`/api/v1/users/${id}/activate`);

// ─── Gerencia ─────────────────────────────────────────────────────────────────
const cleanParams = (params?: any) => {
  if (!params) return undefined;
  const cleaned: any = {};
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
  for (const [key, value] of Object.entries(params)) {
    if (value === '' || value === null || value === undefined) {
      continue;
    }
    if ((key === 'start_date' || key === 'end_date') && typeof value === 'string') {
      if (dateRegex.test(value)) {
        cleaned[key] = value;
      }
    } else {
      cleaned[key] = value;
    }
  }
  return cleaned;
};

export const getGerenciaKPIs = (params?: { start_date?: string, end_date?: string, categoria?: string, sucursal?: string, vendedor?: string }) =>
  api.get<GerenciaKPIs>('/api/v1/analytics/gerencia/kpis', { params: cleanParams(params) });

export const getRevenueByCategory = (params?: { start_date?: string, end_date?: string, sucursal?: string, vendedor?: string }) =>
  api.get<{cat: string, v: number}[]>('/api/v1/analytics/gerencia/revenue-by-category', { params: cleanParams(params) });

export const getCategories = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/categorias');

export const getSucursales = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/sucursales');

export const getVendedores = () =>
  api.get<string[]>('/api/v1/analytics/gerencia/vendedores');

export const getSalesPrediction = () =>
  api.get<SalesPredictionResponse>('/api/v1/analytics/gerencia/sales-prediction');

// ─── Bodega ───────────────────────────────────────────────────────────────────
export const getBodegaKPIs = () =>
  api.get<BodegaKPIs>('/api/v1/analytics/bodega/kpis-inventory');

export const getDemandForecast = (producto_cod: string) =>
  api.get<DemandaResponse>('/api/v1/analytics/bodega/demand-forecasting', {
    params: { producto_cod },
  });

// ─── Ventas ───────────────────────────────────────────────────────────────────
export const getSalesGoals = () =>
  api.get<VentasKPIs>('/api/v1/analytics/ventas/goals');

export const getChurnRisk = (cliente_id: string) =>
  api.get<ChurnResponse>('/api/v1/analytics/ventas/churn-risk', {
    params: { cliente_id },
  });

export const getRecommendations = (cliente_id: string) =>
  api.get<RecomendacionResponse>('/api/v1/analytics/ventas/recommendations', {
    params: { cliente_id },
  });

export const getCustomerSegment = (cliente_cod: string) =>
  api.get<SegmentacionResponse>(`/api/v1/analytics/ventas/clientes/${cliente_cod}/segmento`);

// ─── Admin ────────────────────────────────────────────────────────────────────
export const detectAnomaly = (transaccion_id: string) =>
  api.get<AnomaliaResponse>('/api/v1/analytics/admin/anomalies', {
    params: { transaccion_id },
  });

export const getMLOpsStatus = () =>
  api.get('/api/v1/admin/mlops/status');
