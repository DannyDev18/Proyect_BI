import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getGoalPeriods, getGoalsTracking, generateGoals, reviewGoal } from '../services/goals';
import { qk } from '../constants/queryKeys';
import type { GoalPeriod, GoalProposal } from '../types/goals';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

// Stable references so effects keyed on `.data` don't re-fire every render while loading.
const EMPTY_PERIODS: GoalPeriod[] = [];
const EMPTY_PROPOSALS: GoalProposal[] = [];

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

export const useReviewGoal = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, ...data }: { id: number; monto_meta: number; estado: 'APROBADA' | 'RECHAZADA'; comision_base_pct: number }) =>
      reviewGoal(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goals', 'tracking'] }),
  });
  return { review: mutation.mutateAsync, pendingId: mutation.isPending ? mutation.variables?.id ?? null : null };
};
