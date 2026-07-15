import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHistorialNotificaciones, getNotificaciones, marcarNotificacionLeida, marcarTodasLeidas } from '../services/notifications';
import type { Notificacion } from '../types/notifications';
import type { PaginationQuery } from '../types/pagination';
import { qk } from '../constants/queryKeys';
import { useToast } from '../store/toastStore';

const POLL_MS = 60_000; // docs/features/plan_modulo_notificaciones.md §2.1: polling, sin WebSockets en v1

/** Campana global (§5.1 del plan): calculadas + persistidas del rol/usuario del token,
 * refrescadas cada 60s. Dispara un toast de alta prioridad cuando el polling trae una
 * notificación persistida nueva (§5.4) -- no ruidoso: solo persistidas nuevas de alta
 * prioridad, no cada calculada que cambia en cada tick. */
export const useNotificaciones = () => {
  const toast = useToast();
  const vistasRef = useRef<Set<number>>(new Set());
  const primerTick = useRef(true);

  const query = useQuery({
    queryKey: qk.notificaciones.lista(),
    queryFn: () => getNotificaciones().then((r) => r.data),
    refetchInterval: POLL_MS,
  });

  useEffect(() => {
    const notificaciones = query.data;
    if (!notificaciones) return;

    const persistidasAlta = notificaciones.filter((n) => n.persistida && n.id !== null && n.prioridad === 'alta');
    if (!primerTick.current) {
      for (const n of persistidasAlta) {
        if (!vistasRef.current.has(n.id as number)) toast(n.mensaje, 'warning');
      }
    }
    vistasRef.current = new Set(persistidasAlta.map((n) => n.id as number));
    primerTick.current = false;
  }, [query.data, toast]);

  return {
    data: (query.data ?? []) as Notificacion[],
    loading: query.isLoading,
    error: query.error ? 'Error al cargar notificaciones' : null,
    refetch: query.refetch,
  };
};

export const useMarcarNotificacionLeida = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => marcarNotificacionLeida(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.notificaciones.lista() }),
  });
};

export const useMarcarTodasLeidas = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => marcarTodasLeidas(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.notificaciones.lista() }),
  });
};

export const useHistorialNotificaciones = (pagination: PaginationQuery) =>
  useQuery({
    queryKey: qk.notificaciones.historial(pagination),
    queryFn: () => getHistorialNotificaciones(pagination).then((r) => r.data),
  });
