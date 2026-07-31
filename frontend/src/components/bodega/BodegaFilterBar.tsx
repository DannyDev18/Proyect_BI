import { RotateCcw } from 'lucide-react';
import { useBodegaFiltros } from '../../hooks/bodega';
import { useBodegaFiltersStore } from '../../store/bodegaFiltersStore';
import { Select } from '../ui/Select';
import { ComboboxField } from '../ui/ComboboxField';
import { DateField } from '../ui/DateField';
import { FilterBar, FilterField } from '../ui/FilterBar';

/** Filtros globales del dashboard de Bodega (§1.1): almacén, categoría, proveedor,
 * rango de fechas y tipo de movimiento de Kardex (RN validada en
 * docs/auditoria/02_reglas_negocio_validadas.md §3). Persisten en la sesión
 * (store con sessionStorage).
 *
 * El selector de almacén ya viene pre-filtrado por el backend (RN-B10,
 * `GET /analytics/bodega/filtros`): si el usuario se creó para una bodega específica
 * solo ve esa (o esas), y solo ve el catálogo completo si se marcó
 * `todos_los_almacenes` -- no hace falta filtrar de nuevo aquí.
 *
 * Filtros "inteligentes" (Fase 2 §2.2): `proveedor` depende de `categoria` -- al
 * cambiar la categoría, el catálogo de proveedores se recarga desde el backend
 * (`proveedores` restringido a los que realmente la suministran, `fact_compras`) y el
 * proveedor elegido se limpia si ya no pertenece al nuevo catálogo, para no dejar
 * seleccionada una combinación que no existe en los datos reales. */
export const BodegaFilterBar = () => {
  const f = useBodegaFiltersStore();
  const { data: catalogos } = useBodegaFiltros(f.categoria);

  const proveedoresDisponibles = catalogos?.proveedores ?? [];
  const proveedorInvalido = f.proveedor !== null && !proveedoresDisponibles.includes(f.proveedor);

  const handleCategoriaChange = (valor: string) => {
    const nueva = valor === 'ALL' ? null : valor;
    f.setCategoria(nueva);
    f.setProveedor(null); // el proveedor elegido puede no pertenecer a la nueva categoría
  };

  return (
    <FilterBar>
      <FilterField label="Almacén">
        <ComboboxField
          className="max-w-[180px]" aria-label="Almacén"
          value={f.almacen} allLabel="Todas las bodegas"
          options={catalogos?.almacenes ?? []}
          onChange={f.setAlmacen}
        />
      </FilterField>

      <FilterField label="Categoría">
        <ComboboxField
          className="max-w-[180px]" aria-label="Categoría"
          value={f.categoria} allLabel="Todas las categorías"
          options={catalogos?.categorias ?? []}
          onChange={(v) => handleCategoriaChange(v ?? 'ALL')}
        />
      </FilterField>

      <FilterField
        label="Proveedor"
        helper={f.categoria && proveedoresDisponibles.length === 0
          ? 'Sin proveedores registrados para esta categoría.' : undefined}
      >
        <ComboboxField
          className="max-w-[180px]" aria-label="Proveedor"
          value={proveedorInvalido ? null : f.proveedor} allLabel="Todos los proveedores"
          options={proveedoresDisponibles}
          disabled={!!f.categoria && proveedoresDisponibles.length === 0}
          onChange={f.setProveedor}
        />
      </FilterField>

      <FilterField label="Desde" htmlFor="bodega-fecha-desde">
        <DateField id="bodega-fecha-desde" value={f.fechaDesde ?? ''}
          onChange={(e) => f.setRangoFechas(e.target.value || null, f.fechaHasta)} />
      </FilterField>
      <FilterField label="Hasta" htmlFor="bodega-fecha-hasta">
        <DateField id="bodega-fecha-hasta" value={f.fechaHasta ?? ''}
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
