import { RotateCcw } from 'lucide-react';
import { useBodegaFiltros } from '../../hooks/bodega';
import { useBodegaFiltersStore } from '../../store/bodegaFiltersStore';
import { Select } from '../ui/Select';
import { FilterBar, FilterField } from '../ui/FilterBar';

const dateCls =
  'bg-slate-950 border border-slate-700 text-slate-200 text-sm rounded-md px-3 py-1.5 transition-colors cursor-pointer outline-none max-w-[180px] focus-ring';

/** Filtros globales del dashboard de Bodega (§1.1): almacén, categoría, proveedor,
 * rango de fechas y tipo de movimiento de Kardex (RN validada en
 * docs/auditoria/02_reglas_negocio_validadas.md §3). Persisten en la sesión
 * (store con sessionStorage). */
export const BodegaFilterBar = () => {
  const { data: catalogos } = useBodegaFiltros();
  const f = useBodegaFiltersStore();

  return (
    <FilterBar>
      <FilterField label="Almacén">
        <Select className="max-w-[180px]" value={f.almacen ?? 'ALL'}
          onChange={(e) => f.setAlmacen(e.target.value === 'ALL' ? null : e.target.value)}>
          <option value="ALL">Todas las bodegas</option>
          {catalogos?.almacenes.map((a) => <option key={a} value={a}>{a}</option>)}
        </Select>
      </FilterField>

      <FilterField label="Categoría">
        <Select className="max-w-[180px]" value={f.categoria ?? 'ALL'}
          onChange={(e) => f.setCategoria(e.target.value === 'ALL' ? null : e.target.value)}>
          <option value="ALL">Todas las categorías</option>
          {catalogos?.categorias.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
      </FilterField>

      <FilterField label="Proveedor">
        <Select className="max-w-[180px]" value={f.proveedor ?? 'ALL'}
          onChange={(e) => f.setProveedor(e.target.value === 'ALL' ? null : e.target.value)}>
          <option value="ALL">Todos los proveedores</option>
          {catalogos?.proveedores.map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
      </FilterField>

      <FilterField label="Desde" htmlFor="bodega-fecha-desde">
        <input id="bodega-fecha-desde" type="date" className={dateCls} value={f.fechaDesde ?? ''}
          onChange={(e) => f.setRangoFechas(e.target.value || null, f.fechaHasta)} />
      </FilterField>
      <FilterField label="Hasta" htmlFor="bodega-fecha-hasta">
        <input id="bodega-fecha-hasta" type="date" className={dateCls} value={f.fechaHasta ?? ''}
          onChange={(e) => f.setRangoFechas(f.fechaDesde, e.target.value || null)} />
      </FilterField>

      <FilterField label="Tipo de movimiento" className="flex-1 min-w-[200px]">
        <Select className="max-w-full" value={f.tipoMovimiento ?? 'ALL'}
          onChange={(e) => f.setTipoMovimiento(e.target.value === 'ALL' ? null : e.target.value)}>
          <option value="ALL">Todos los movimientos</option>
          {catalogos?.tipos_movimiento.map((t) => (
            <option key={t.codigo} value={t.codigo}>{t.etiqueta}</option>
          ))}
        </Select>
      </FilterField>

      <button
        onClick={f.reset}
        title="Limpiar filtros"
        aria-label="Limpiar filtros"
        className="p-2 text-slate-400 hover:text-primary hover:bg-bg-hover rounded-lg transition-colors cursor-pointer focus-ring"
      >
        <RotateCcw size={16} />
      </button>
    </FilterBar>
  );
};
