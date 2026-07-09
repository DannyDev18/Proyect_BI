import { api } from './http';
import type { GoalPeriod, GoalProposal } from '../types/goals';

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
