import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getSalesGoals, getMyGoalTracking, getChurnRisk, getRecommendations, getCustomerSegment,
  getGoalForecastCierre, getMetaSugerida, getGoalRecommendations, getMyCommission, getPostGoalInvoices,
} from '../services/ventas';
import { qk } from '../constants/queryKeys';
import type { PostGoalInvoiceItem } from '../types/ventas';

const EMPTY_INVOICES: PostGoalInvoiceItem[] = [];

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

export const useSalesGoals = () => {
  const query = useQuery({
    queryKey: qk.ventas.goals(),
    queryFn: () => getSalesGoals().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

/** Dashboard vendedor: cumplimiento de meta del período vigente, vía el mismo endpoint
 * de `useSalesGoals` pero tipado según el contrato real del backend. */
export const useMyGoalTracking = () => {
  const query = useQuery({
    queryKey: qk.ventas.myGoalTracking(),
    queryFn: () => getMyGoalTracking().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

/** Integración ML (docs/auditoria/15_...): pronóstico de cierre del mes en curso. */
export const useGoalForecastCierre = () => {
  const query = useQuery({
    queryKey: qk.ventas.forecastCierre(),
    queryFn: () => getGoalForecastCierre().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
};

/** Meta sugerida por el motor estadístico (IQR + anomalías, sin ML). */
export const useMetaSugerida = () => {
  const query = useQuery({
    queryKey: qk.ventas.metaSugerida(),
    queryFn: () => getMetaSugerida().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
};

/** Productos recomendados (reglas de asociación) para ayudar a cerrar la meta. */
export const useGoalRecommendations = () => {
  const query = useQuery({
    queryKey: qk.ventas.goalRecommendations(),
    queryFn: () => getGoalRecommendations().then((r) => r.data),
  });
  return { data: query.data?.recomendaciones ?? [], loading: query.isLoading, error: errorMessage(query.error) };
};

/** Comisiones (docs/modulo_metas.md): mi cumplimiento real y comisión devengada del
 * mes en curso, con alerta de última semana si voy por debajo del 70%. */
export const useMyCommission = () => {
  const query = useQuery({
    queryKey: qk.ventas.myCommission(),
    queryFn: () => getMyCommission().then((r) => r.data),
  });
  return { data: query.data ?? null, loading: query.isLoading, error: errorMessage(query.error) };
};

/** Facturas emitidas después de alcanzar el 100% de la meta -- solo tiene contenido
 * una vez superada la meta del mes en curso. */
export const usePostGoalInvoices = () => {
  const query = useQuery({
    queryKey: qk.ventas.postGoalInvoices(),
    queryFn: () => getPostGoalInvoices().then((r) => r.data.facturas),
  });
  return { data: query.data ?? EMPTY_INVOICES, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useChurnRisk = () => {
  const mutation = useMutation({
    mutationFn: (cliente_id: string) => getChurnRisk(cliente_id).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (cliente_id: string) => { mutation.reset(); mutation.mutate(cliente_id); },
  };
};

export const useRecommendations = () => {
  const mutation = useMutation({
    mutationFn: (cliente_id: string) => getRecommendations(cliente_id).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (cliente_id: string) => { mutation.reset(); mutation.mutate(cliente_id); },
  };
};

export const useCustomerSegment = () => {
  const mutation = useMutation({
    mutationFn: (cliente_cod: string) => getCustomerSegment(cliente_cod).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    execute: (cliente_cod: string) => { mutation.reset(); mutation.mutate(cliente_cod); },
  };
};
