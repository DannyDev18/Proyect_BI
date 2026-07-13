import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { BodegaFilterState } from '../types/bodega';

interface BodegaFiltersStore extends BodegaFilterState {
  setAlmacen: (almacen: string | null) => void;
  setCategoria: (categoria: string | null) => void;
  setProveedor: (proveedor: string | null) => void;
  setBusqueda: (busqueda: string) => void;
  setRangoFechas: (desde: string | null, hasta: string | null) => void;
  reset: () => void;
}

const initial: BodegaFilterState = {
  almacen: null,
  categoria: null,
  proveedor: null,
  busqueda: '',
  fechaDesde: null,
  fechaHasta: null,
};

/** Filtros globales del dashboard de Bodega (§1.1: "los filtros deben persistir en la
 * sesión del usuario") — persistidos en sessionStorage, no en localStorage. */
export const useBodegaFiltersStore = create<BodegaFiltersStore>()(
  persist(
    (set) => ({
      ...initial,
      setAlmacen: (almacen) => set({ almacen }),
      setCategoria: (categoria) => set({ categoria }),
      setProveedor: (proveedor) => set({ proveedor }),
      setBusqueda: (busqueda) => set({ busqueda }),
      setRangoFechas: (fechaDesde, fechaHasta) => set({ fechaDesde, fechaHasta }),
      reset: () => set(initial),
    }),
    {
      name: 'bodega-filters',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

/** Proyección de los filtros al shape de query params del servicio. */
export const toQueryFilters = (s: BodegaFilterState) => ({
  almacen: s.almacen,
  categoria: s.categoria,
  proveedor: s.proveedor,
  busqueda: s.busqueda || null,
  fecha_desde: s.fechaDesde,
  fecha_hasta: s.fechaHasta,
});
