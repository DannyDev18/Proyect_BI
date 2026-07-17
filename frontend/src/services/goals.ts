import { api } from './http';
import type { GoalPeriod, GoalProposal, GoalsAISummary, MetaSugeridaDesglose, VendorCommissionRow } from '../types/goals';

export const getGoalPeriods = () =>
  api.get<GoalPeriod[]>('/api/v1/gerencia/goals/periods');

export const getGoalsTracking = (anio: number, mes: number) =>
  api.get<{ reporte_cumplimiento: GoalProposal[] }>('/api/v1/gerencia/goals/tracking', {
    params: { anio, mes },
  });

export const generateGoals = (anio: number, mes: number, pressure_factor: number) =>
  api.post(`/api/v1/gerencia/goals/generate`, null, {
    params: { anio, mes, pressure_factor },
  });

export const reviewGoal = (id: number, data: { monto_meta: number; estado: 'APROBADA' | 'RECHAZADA'; comision_base_pct: number }) =>
  api.put(`/api/v1/gerencia/goals/${id}/review`, data);

/** Integración ML (docs/auditoria/15_...): metas sugeridas por IA, vendedores en
 * riesgo/alta probabilidad y recomendaciones comerciales por categoría. */
export const getGoalsAISummary = () =>
  api.get<GoalsAISummary>('/api/v1/gerencia/goals/ai-summary');

/** Comisiones (docs/modulo_metas.md): cumplimiento real (Venta Neta) y comisión
 * devengada por vendedor en el período -- cierra el hallazgo R-1 de
 * docs/auditoria/14_...md (antes solo se mostraba la meta configurada). */
export const getCommissionTracking = (anio: number, mes: number) =>
  api.get<{ comisiones: VendorCommissionRow[] }>('/api/v1/gerencia/goals/commissions', {
    params: { anio, mes },
  });

/** Desglose del motor estadístico IQR para el drawer de revisión de gerencia
 * (plan_actualizacion_modulo_metas_comisiones.md Fase 2 ítem 1) -- equivalente
 * gerencial de `getMetaSugerida` (services/ventas.ts), que solo cubre al vendedor
 * autenticado; esta acepta cualquier `vendedor_origen` de la propuesta seleccionada. */
export const getMetaSugeridaGerencia = (vendedorOrigen: string) =>
  api.get<MetaSugeridaDesglose>('/api/v1/gerencia/goals/meta-sugerida', {
    params: { vendedor_origen: vendedorOrigen },
  });
