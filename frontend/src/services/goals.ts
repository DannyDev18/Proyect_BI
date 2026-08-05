import { api } from './http';
import type {
  GoalPeriod, GoalProposal, GoalsAISummary, MetaConfigCatalogo, MetaConfigModulo,
  MetaSugeridaDesglose, VendorCommissionRow,
} from '../types/goals';

const clean = (params: object) =>
  Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''));

export const getGoalPeriods = () =>
  api.get<GoalPeriod[]>('/api/v1/gerencia/goals/periods');

/** `vendedor` opcional (Fase 3 §3.1): sin selección, vista agregada de todos los
 * vendedores (comportamiento previo intacto). */
export const getGoalsTracking = (anio: number, mes: number, vendedor?: string | null) =>
  api.get<{ reporte_cumplimiento: GoalProposal[] }>('/api/v1/gerencia/goals/tracking', {
    params: clean({ anio, mes, vendedor }),
  });

export const generateGoals = (anio: number, mes: number, pressure_factor: number) =>
  api.post(`/api/v1/gerencia/goals/generate`, null, {
    params: { anio, mes, pressure_factor },
  });

// `comision_base_pct` ya no se edita desde este flujo (petición explícita del usuario:
// la comisión real siempre es variable, este campo del esquema plano legado no tiene
// ningún efecto sobre lo que se paga -- ver docstring de GoalsConsole.tsx). El backend
// conserva el campo opcional por compatibilidad; el frontend deja de enviarlo.
export const reviewGoal = (id: number, data: { monto_meta: number; estado: 'APROBADA' | 'RECHAZADA' }) =>
  api.put(`/api/v1/gerencia/goals/${id}/review`, data);

/** Integración ML (docs/auditoria/15_...): metas sugeridas por IA, vendedores en
 * riesgo/alta probabilidad y recomendaciones comerciales por categoría. */
export const getGoalsAISummary = () =>
  api.get<GoalsAISummary>('/api/v1/gerencia/goals/ai-summary');

/** Comisiones (docs/modulo_metas.md): cumplimiento real (Venta Neta) y comisión
 * devengada por vendedor en el período -- cierra el hallazgo R-1 de
 * docs/auditoria/14_...md (antes solo se mostraba la meta configurada). */
export const getCommissionTracking = (anio: number, mes: number, vendedor?: string | null) =>
  api.get<{ comisiones: VendorCommissionRow[] }>('/api/v1/gerencia/goals/commissions', {
    params: clean({ anio, mes, vendedor }),
  });

/** Desglose del motor estadístico IQR para el drawer de revisión de gerencia
 * (plan_actualizacion_modulo_metas_comisiones.md Fase 2 ítem 1) -- equivalente
 * gerencial de `getMetaSugerida` (services/ventas.ts), que solo cubre al vendedor
 * autenticado; esta acepta cualquier `vendedor_origen` de la propuesta seleccionada. */
export const getMetaSugeridaGerencia = (vendedorOrigen: string, anio?: number | null, mes?: number | null) =>
  api.get<MetaSugeridaDesglose>('/api/v1/gerencia/goals/meta-sugerida', {
    params: { vendedor_origen: vendedorOrigen, anio: anio ?? undefined, mes: mes ?? undefined },
  });

// Nota: `/meta-config/parametros[/auditoria]` (motor v2 plano, 13 constantes) se
// conserva en el backend por compatibilidad pero no tiene UI propia desde que el
// pipeline modular (abajo) lo reemplazó -- sin cliente frontend a propósito.

// ── Configuración modular del motor de metas v3 (Fase 6) ────────────────────────────
export const getMetaConfigCatalogo = () =>
  api.get<MetaConfigCatalogo>('/api/v1/gerencia/goals/meta-config/catalogo');

export const getMetaConfigModulos = () =>
  api.get<MetaConfigModulo[]>('/api/v1/gerencia/goals/meta-config/modulos');

export const putMetaConfigModulo = (
  etapa: string, payload: { metodo: string | null; activo: boolean; parametros: Record<string, unknown> },
) => api.put<MetaConfigModulo>(`/api/v1/gerencia/goals/meta-config/modulos/${etapa}`, payload);
