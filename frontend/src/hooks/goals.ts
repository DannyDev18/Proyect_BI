import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getGoalPeriods, getGoalsTracking, generateGoals, reviewGoal, getGoalsAISummary, getCommissionTracking } from '../services/goals';
import { qk } from '../constants/queryKeys';
import type { GoalPeriod, GoalProposal, GoalsAISummary, VendorCommissionRow } from '../types/goals';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

// Stable references so effects keyed on `.data` don't re-fire every render while loading.
const EMPTY_PERIODS: GoalPeriod[] = [];
const EMPTY_PROPOSALS: GoalProposal[] = [];
const EMPTY_AI_SUMMARY: GoalsAISummary = { vendedores_en_riesgo: [], vendedores_alta_probabilidad: [], recomendaciones_por_categoria: [] };
const EMPTY_COMMISSIONS: VendorCommissionRow[] = [];

export const usePeriods = () => {
  const query = useQuery({
    queryKey: qk.goals.periods(),
    queryFn: () => getGoalPeriods().then((r) => r.data),
  });
  return { data: query.data ?? EMPTY_PERIODS, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useGoalsTracking = (anio: number, mes: number) => {
  const query = useQuery({
    queryKey: qk.goals.tracking(anio, mes),
    queryFn: () => getGoalsTracking(anio, mes).then((r) => r.data.reporte_cumplimiento || []),
  });
  return { data: query.data ?? EMPTY_PROPOSALS, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useGenerateGoals = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ anio, mes, factor }: { anio: number; mes: number; factor: number }) =>
      generateGoals(anio, mes, factor),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goals', 'tracking'] }),
  });
  return { generate: mutation.mutateAsync, loading: mutation.isPending };
};

export const useGoalsAISummary = () => {
  const query = useQuery({
    queryKey: qk.goals.aiSummary(),
    queryFn: () => getGoalsAISummary().then((r) => r.data),
  });
  return { data: query.data ?? EMPTY_AI_SUMMARY, loading: query.isLoading, error: errorMessage(query.error) };
};

/** Comisiones (docs/modulo_metas.md): cumplimiento real + comisión devengada por
 * vendedor en el período, para el panel gerencial. */
export const useCommissionTracking = (anio: number, mes: number) => {
  const query = useQuery({
    queryKey: qk.goals.commissionTracking(anio, mes),
    queryFn: () => getCommissionTracking(anio, mes).then((r) => r.data.comisiones),
  });
  return { data: query.data ?? EMPTY_COMMISSIONS, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useReviewGoal = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, ...data }: { id: number; monto_meta: number; estado: 'APROBADA' | 'RECHAZADA'; comision_base_pct: number }) =>
      reviewGoal(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goals', 'tracking'] }),
  });
  return { review: mutation.mutateAsync, pendingId: mutation.isPending ? mutation.variables?.id ?? null : null };
};
