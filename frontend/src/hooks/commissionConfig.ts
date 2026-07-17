import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getMatrizCategorias, upsertMatrizCategoria, getFactoresCredito, replaceFactoresCredito,
  getConfigVendedores, upsertConfigVendedor, postCommissionSimulation, getPerfilCategorias, getLineasSinCosto,
  getComisionConfigAuditoria, searchClasesProducto, searchVendedoresComision,
} from '../services/commissionConfig';
import { qk } from '../constants/queryKeys';
import type {
  ComisionConfigAuditoriaEntrada, ConfigVendedor, FactorCredito, LineaSinCosto, MatrizCategoria, PerfilCategoria,
} from '../types/commissionConfig';

const errorMessage = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : 'Error al cargar datos') : null;

const EMPTY_MATRIZ: MatrizCategoria[] = [];
const EMPTY_CREDITO: FactorCredito[] = [];
const EMPTY_VENDEDORES: ConfigVendedor[] = [];
const EMPTY_PERFILES: PerfilCategoria[] = [];
const EMPTY_LINEAS: LineaSinCosto[] = [];
const EMPTY_AUDITORIA: ComisionConfigAuditoriaEntrada[] = [];

/** Configuración del sistema de Comisiones Variables (docs/features/
 * plan_integracion_comisiones_variables.md §3.5): matriz de categorías, factores de
 * crédito y tipo de vendedor. Panel de gerencia -- ajustar sin programar. */
export const useMatrizCategorias = () => {
  const query = useQuery({
    queryKey: qk.commissionConfig.matriz(),
    queryFn: () => getMatrizCategorias().then((r) => r.data.reglas),
  });
  return { data: query.data ?? EMPTY_MATRIZ, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useUpsertMatrizCategoria = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: upsertMatrizCategoria,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.matriz() });
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.auditoria() });
    },
  });
  return { upsert: mutation.mutateAsync, loading: mutation.isPending };
};

export const useFactoresCredito = () => {
  const query = useQuery({
    queryKey: qk.commissionConfig.credito(),
    queryFn: () => getFactoresCredito().then((r) => r.data.factores),
  });
  return { data: query.data ?? EMPTY_CREDITO, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useReplaceFactoresCredito = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: replaceFactoresCredito,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.credito() });
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.auditoria() });
    },
  });
  return { replace: mutation.mutateAsync, loading: mutation.isPending };
};

export const useConfigVendedores = () => {
  const query = useQuery({
    queryKey: qk.commissionConfig.vendedores(),
    queryFn: () => getConfigVendedores().then((r) => r.data.vendedores),
  });
  return { data: query.data ?? EMPTY_VENDEDORES, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

export const useUpsertConfigVendedor = () => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ vendedorOrigen, ...payload }: { vendedorOrigen: string; tipo: 'externo' | 'interno'; factor_tipo: number; fecha_ingreso?: string | null }) =>
      upsertConfigVendedor(vendedorOrigen, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.vendedores() });
      queryClient.invalidateQueries({ queryKey: qk.commissionConfig.auditoria() });
    },
  });
  return { upsert: mutation.mutateAsync, pendingVendedor: mutation.isPending ? mutation.variables?.vendedorOrigen ?? null : null };
};

/** Simulación retroactiva plano vs. variable (Fase 2 del plan) -- se dispara bajo
 * demanda (mutation), no como query automática: es una consulta potencialmente pesada
 * sobre el EDW (N meses x M vendedores, grano de línea). */
export const useCommissionSimulation = () => {
  const mutation = useMutation({
    mutationFn: ({ meses, anioDesde, mesDesde }: { meses: number; anioDesde?: number; mesDesde?: number }) =>
      postCommissionSimulation(meses, anioDesde, mesDesde).then((r) => r.data),
  });
  return {
    data: mutation.data ?? null,
    loading: mutation.isPending,
    error: errorMessage(mutation.error),
    simulate: (meses: number, anioDesde?: number, mesDesde?: number) => mutation.mutateAsync({ meses, anioDesde, mesDesde }),
  };
};

export const usePerfilCategorias = (meses = 24) => {
  const query = useQuery({
    queryKey: qk.commissionConfig.perfilCategorias(meses),
    queryFn: () => getPerfilCategorias(meses).then((r) => r.data.perfiles),
  });
  return { data: query.data ?? EMPTY_PERFILES, loading: query.isLoading, error: errorMessage(query.error) };
};

export const useLineasSinCosto = (anio?: number, mes?: number) => {
  const query = useQuery({
    queryKey: qk.commissionConfig.lineasSinCosto(anio, mes),
    queryFn: () => getLineasSinCosto(anio, mes).then((r) => r.data.lineas),
  });
  return { data: query.data ?? EMPTY_LINEAS, loading: query.isLoading, error: errorMessage(query.error) };
};

/** Bitácora de cambios (plan_actualizacion_modulo_metas_comisiones.md Fase 2 ítem 2) --
 * se invalida en las 3 mutaciones de arriba, así que se refresca sola tras cada cambio. */
export const useComisionConfigAuditoria = () => {
  const query = useQuery({
    queryKey: qk.commissionConfig.auditoria(),
    queryFn: () => getComisionConfigAuditoria().then((r) => r.data.entradas),
  });
  return { data: query.data ?? EMPTY_AUDITORIA, loading: query.isLoading, error: errorMessage(query.error), refetch: query.refetch };
};

/** Búsqueda inteligente (autocomplete) de clase de producto y vendedor -- solo
 * dispara la consulta con 2+ caracteres (mismo umbral que <Autocomplete/>), así el
 * backend nunca recibe una petición por cada tecla ni un fetch del catálogo entero. */
export const useSearchClasesProducto = (q: string) => {
  const query = useQuery({
    queryKey: qk.commissionConfig.searchClases(q),
    queryFn: () => searchClasesProducto(q).then((r) => r.data),
    enabled: q.trim().length >= 2,
  });
  return { data: query.data ?? null, loading: query.isLoading };
};

export const useSearchVendedoresComision = (q: string) => {
  const query = useQuery({
    queryKey: qk.commissionConfig.searchVendedores(q),
    queryFn: () => searchVendedoresComision(q).then((r) => r.data),
    enabled: q.trim().length >= 2,
  });
  return { data: query.data ?? null, loading: query.isLoading };
};
