import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getGoalPeriods, getGoalsTracking, generateGoals, reviewGoal, getGoalsAISummary, getCommissionTracking,
  getMetaSugeridaGerencia, getMetaConfigCatalogo, getMetaConfigModulos, putMetaConfigModulo,
} from '../services/goals';
import { qk } from '../constants/queryKeys';
import type {
  GoalPeriod, GoalProposal, GoalsAISummary, MetaConfigCatalogo, MetaConfigModulo, VendorCommissionRow,
} from '../types/goals';
import { getApiErrorMessage as errorMessage } from '../utils/apiError';

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

export const useGoalsTracking = (anio: number, mes: number, vendedor?: string | null) => {
  const query = useQuery({
    queryKey: qk.goals.tracking(anio, mes, vendedor),
    queryFn: () => getGoalsTracking(anio, mes, vendedor).then((r) => r.data.reporte_cumplimiento || []),
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
export const useCommissionTracking = (anio: number, mes: number, vendedor?: string | null) => {
  const query = useQuery({
    queryKey: qk.goals.commissionTracking(anio, mes, vendedor),
    queryFn: () => getCommissionTracking(anio, mes, vendedor).then((r) => r.data.comisiones),
  });
  return { data: query.data ?? EMPTY_COMMISSIONS, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useReviewGoal = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, ...data }: { id: number; monto_meta: number; estado: 'APROBADA' | 'RECHAZADA' }) =>
      reviewGoal(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['goals', 'tracking'] }),
  });
  return { review: mutation.mutateAsync, pendingId: mutation.isPending ? mutation.variables?.id ?? null : null };
};

/** Desglose IQR de una propuesta puntual, para el drawer de revisión de gerencia --
 * solo se pide cuando el drawer está abierto (`enabled`), nunca precargado por fila. */
export const useMetaSugeridaGerencia = (
  vendedorOrigen: string | null, anio?: number | null, mes?: number | null,
) => {
  const query = useQuery({
    queryKey: qk.goals.metaSugeridaGerencia(vendedorOrigen ?? '', anio, mes),
    queryFn: () => getMetaSugeridaGerencia(vendedorOrigen as string, anio, mes).then((r) => r.data),
    enabled: !!vendedorOrigen,
  });
  return { data: query.data, loading: query.isLoading, error: errorMessage(query.error) };
};

// Nota: el motor v2 plano (`/meta-config/parametros[/auditoria]`) no tiene hooks propios
// -- el pipeline modular de abajo lo reemplazó por completo como fuente real del motor,
// y su bitácora ya vive en `useComisionConfigAuditoria` (tabla compartida).

// ── Configuración modular del motor de metas v3 (Fase 6) ────────────────────────────
const EMPTY_META_CONFIG_CATALOGO: MetaConfigCatalogo = {};
const EMPTY_META_CONFIG_MODULOS: MetaConfigModulo[] = [];

export const useMetaConfigCatalogo = () => {
  const query = useQuery({
    queryKey: qk.goals.metaConfigCatalogo(),
    queryFn: () => getMetaConfigCatalogo().then((r) => r.data),
  });
  return { data: query.data ?? EMPTY_META_CONFIG_CATALOGO, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useMetaConfigModulos = () => {
  const query = useQuery({
    queryKey: qk.goals.metaConfigModulos(),
    queryFn: () => getMetaConfigModulos().then((r) => r.data),
  });
  return { data: query.data ?? EMPTY_META_CONFIG_MODULOS, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useUpdateMetaConfigModulo = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ etapa, metodo, activo, parametros }: {
      etapa: string; metodo: string | null; activo: boolean; parametros: Record<string, unknown>;
    }) => putMetaConfigModulo(etapa, { metodo, activo, parametros }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.goals.metaConfigModulos() });
      // La bitácora de este cambio vive en la tabla compartida que lee la pantalla
      // "Bitácora de cambios" (BitacoraPanel.tsx / useComisionConfigAuditoria), no en un
      // panel embebido propio -- se invalida esa misma query para que se refresque sola.
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.auditoria() });
    },
  });
  return { update: mutation.mutateAsync, pendingEtapa: mutation.isPending ? mutation.variables?.etapa ?? null : null };
};
