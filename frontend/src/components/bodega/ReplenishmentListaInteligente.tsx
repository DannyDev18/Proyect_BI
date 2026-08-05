import { useMemo, useState } from 'react';
import { AlertTriangle, Bell, Boxes, DollarSign, Gauge, PackageCheck, TrendingDown } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { KpiCard, KpiCardSkeleton } from '../ui/KpiCard';
import { Pagination } from '../ui/Pagination';
import { Select } from '../ui/Select';
import { FilterBar, FilterField } from '../ui/FilterBar';
import {
  useAlertasReabastecimiento, useListaReabastecimiento, useResumenReabastecimiento,
} from '../../hooks/replenishment';
import { usePagination } from '../../hooks/usePagination';
import type { toQueryFilters } from '../../store/bodegaFiltersStore';
import { fmt, fmtMoney } from '../../utils/format';
import type { ItemReabastecimiento, RiesgoReabastecimiento } from '../../types/replenishment';

const riesgoBadge: Record<RiesgoReabastecimiento, 'danger' | 'warning' | 'neutral' | 'info' | 'success'> = {
  critico: 'danger', alto: 'warning', medio: 'info', bajo: 'success', sin_demanda: 'neutral',
};

const riesgoLabel: Record<RiesgoReabastecimiento, string> = {
  critico: 'Crítico', alto: 'Alto', medio: 'Medio', bajo: 'Bajo', sin_demanda: 'Sin demanda',
};

const riesgoRowTint: Record<RiesgoReabastecimiento, string> = {
  critico: 'bg-danger/5', alto: 'bg-warning/5', medio: '', bajo: '', sin_demanda: '',
};

const metodoDemandaLabel: Record<string, string> = {
  ml_demand_rf: 'Modelo ML (demand_rf)',
  estadistico: 'Estadístico (histórico real)',
  sin_historia: 'Sin historia suficiente',
};

const origenLabel: Record<string, string> = {
  producto: 'Configurado para este producto',
  categoria: 'Configurado para la categoría',
  proveedor: 'Configurado para el proveedor',
  default: 'Valor global por defecto',
};

/** Fila expandible (Bloque 3, Explicabilidad): reutiliza el mismo patrón de
 * `DesgloseComision` (CommissionSimulationPanel) -- toda predicción debe volverse
 * explicable, nunca una caja negra. */
function DesgloseReabastecimiento({ row }: { row: ItemReabastecimiento }) {
  return (
    <div className="p-4 space-y-3">
      <div>
        <p className="text-xs font-semibold text-slate-400 mb-2">Por qué se recomienda esto</p>
        <ul className="space-y-1 list-disc list-inside">
          {row.razones.map((r, i) => (
            <li key={i} className="text-xs text-slate-300">{r}</li>
          ))}
        </ul>
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 border border-slate-800 rounded-lg p-3">
        <div>
          <dt className="text-[10px] uppercase text-slate-500">Demanda diaria (media / σ)</dt>
          <dd className="text-slate-300 font-mono text-xs">
            {row.demanda_diaria_media.toFixed(2)} / {row.demanda_diaria_sigma.toFixed(2)}
          </dd>
          <dd className="text-[10px] text-slate-600">{metodoDemandaLabel[row.metodo_demanda] ?? row.metodo_demanda}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase text-slate-500">Lead time</dt>
          <dd className="text-slate-300 font-mono text-xs">{row.lead_time_dias}d</dd>
          <dd className="text-[10px] text-slate-600">{origenLabel[row.lead_time_origen] ?? row.lead_time_origen}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase text-slate-500">Stock de seguridad</dt>
          <dd className="text-slate-300 font-mono text-xs">{row.stock_seguridad.toFixed(1)} uds</dd>
          <dd className="text-[10px] text-slate-600">
            Nivel de servicio {(row.nivel_servicio * 100).toFixed(1)}%{row.z_usado != null ? ` · z=${row.z_usado.toFixed(3)}` : ''}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase text-slate-500">Punto de reorden</dt>
          <dd className="text-slate-300 font-mono text-xs">{row.punto_reorden.toFixed(1)} uds</dd>
          <dd className="text-[10px] text-slate-600">Cobertura actual: {row.cobertura_dias != null ? `${row.cobertura_dias.toFixed(1)}d` : '—'}</dd>
        </div>
      </dl>
      <div className="flex items-center justify-between pt-1 border-t border-slate-800">
        <span className="text-xs text-slate-400">Cantidad sugerida a comprar</span>
        <span className="font-mono text-sm font-semibold text-warning">
          {row.cantidad_sugerida.toFixed(0)} uds · {fmtMoney(row.costo_total_sugerido)}
        </span>
      </div>
    </div>
  );
}

const severidadIcon: Record<string, { icon: typeof AlertTriangle; badge: 'warning' | 'neutral' }> = {
  media: { icon: AlertTriangle, badge: 'warning' },
  baja: { icon: TrendingDown, badge: 'neutral' },
};

/** F7 (§7.4 del plan): cambio brusco de demanda y tendencia decreciente sostenida --
 * las 2 señales que el generador de Bodega nunca calculó. El riesgo de quiebre y el
 * sobrestock ya son visibles en el Centro de Decisiones/Lista de abajo, no se
 * repiten aquí (ver docstring de `ReplenishmentService.get_alertas`). */
function AlertasPanel({ filters, horizonteDias }: { filters: ReturnType<typeof toQueryFilters>; horizonteDias: number }) {
  const alertas = useAlertasReabastecimiento(filters, horizonteDias);
  if (alertas.loading || alertas.error || !alertas.data || alertas.data.length === 0) return null;

  return (
    <div className="card p-4 animate-fade-in-up">
      <div className="flex items-center gap-2 mb-3">
        <Bell size={16} className="text-slate-400" />
        <h3 className="font-sans font-semibold text-slate-200 text-sm">Alertas inteligentes</h3>
      </div>
      <ul className="space-y-2">
        {alertas.data.map((a, i) => {
          const cfg = severidadIcon[a.severidad] ?? severidadIcon.baja;
          const Icon = cfg.icon;
          return (
            <li key={`${a.codart}-${a.tipo}-${i}`} className="flex items-start gap-2 text-xs">
              <Icon size={14} className={cfg.badge === 'warning' ? 'text-warning mt-0.5' : 'text-slate-500 mt-0.5'} />
              <div>
                <span className="font-semibold text-slate-200">{a.nombre}</span>{' '}
                <span className="text-slate-500">({a.codart})</span>
                <p className="text-slate-400">{a.mensaje}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface ReplenishmentListaInteligenteProps {
  filters: ReturnType<typeof toQueryFilters>;
}

/** Bloques 1 (Centro de Decisiones) y 2 (Lista Inteligente) del rediseño de
 * Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_inteligente.md).
 * Vista hija "Lista Inteligente" del módulo de Inventario/Reabastecimiento (Fase 6,
 * docs/features/plan_modulo_inventario_reabastecimiento.md) -- se mantienen juntos
 * porque comparten `filters`/`horizonteDias`: los KPIs del Centro de Decisiones deben
 * reaccionar al mismo horizonte/filtro que la lista, separarlos en pestañas distintas
 * habría duplicado ese estado sin beneficio real. Convive con `/bodega/almacenes`
 * (Predicción de Necesidad de Compra, motor determinista sin cambios) -- esta vista
 * prioriza por RIESGO REAL de quiebre (stock de seguridad + punto de reorden), no por
 * volumen de ventas. */
export const ReplenishmentListaInteligente = ({ filters }: ReplenishmentListaInteligenteProps) => {
  const [horizonteDias, setHorizonteDias] = useState(30);
  const [soloCriticos, setSoloCriticos] = useState(false);
  const [riesgo, setRiesgo] = useState<string | null>(null);
  const [claseAbc, setClaseAbc] = useState<string | null>(null);
  const [claseXyz, setClaseXyz] = useState<string | null>(null);

  const extra = useMemo(
    () => ({ horizonte_dias: horizonteDias, solo_criticos: soloCriticos, riesgo, clase_abc: claseAbc, clase_xyz: claseXyz }),
    [horizonteDias, soloCriticos, riesgo, claseAbc, claseXyz],
  );

  const resumen = useResumenReabastecimiento(filters, horizonteDias);
  const pagination = usePagination([filters, extra]);
  const lista = useListaReabastecimiento(filters, extra, pagination.query);

  const columns: DataTableColumn<ItemReabastecimiento>[] = [
    {
      key: 'producto', header: 'Artículo',
      render: (p) => (
        <>
          <p className="font-semibold text-slate-200">{p.nombre}</p>
          <p className="text-xs text-slate-500">{p.codart}</p>
        </>
      ),
    },
    {
      key: 'clasificacion', header: 'ABC / XYZ',
      render: (p) => (
        <span className="flex items-center gap-1">
          <Badge variant="neutral">{p.clase_abc}</Badge>
          <Badge variant="neutral">{p.clase_xyz}</Badge>
        </span>
      ),
    },
    { key: 'stock', header: 'Stock', numeric: true, render: (p) => <span className="text-slate-300">{p.stock_actual}</span> },
    {
      key: 'cobertura', header: 'Cobertura', numeric: true,
      render: (p) => <span className="text-slate-400">{p.cobertura_dias != null ? `${p.cobertura_dias.toFixed(1)}d` : '—'}</span>,
    },
    { key: 'reorden', header: 'Punto reorden', numeric: true, render: (p) => <span className="text-slate-400">{p.punto_reorden.toFixed(0)}</span> },
    {
      key: 'riesgo', header: 'Riesgo',
      render: (p) => <Badge variant={riesgoBadge[p.riesgo]}>{riesgoLabel[p.riesgo]}</Badge>,
    },
    { key: 'cantidad', header: 'Cant. sugerida', numeric: true, render: (p) => <span className="text-info font-semibold">{p.cantidad_sugerida.toFixed(0)}</span> },
    { key: 'costo', header: 'Costo total', numeric: true, render: (p) => <span className="text-slate-300">{fmtMoney(p.costo_total_sugerido)}</span> },
  ];

  return (
    <div className="space-y-6">
      {/* Bloque 1: Centro de Decisiones */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-fade-in-up">
        {resumen.loading && Array.from({ length: 4 }).map((_, i) => <KpiCardSkeleton key={i} />)}
        {!resumen.loading && resumen.data && (
          <>
            <KpiCard
              title="Riesgo crítico" value={resumen.data.productos_riesgo_critico} icon={AlertTriangle}
              state={resumen.data.productos_riesgo_critico > 0 ? 'danger' : 'success'}
              subValue={`${resumen.data.productos_riesgo_critico} de ${resumen.data.total_articulos_evaluados} artículos`}
              tooltip="Punto de reorden ya superado -- stock actual por debajo de la cobertura mínima segura."
            />
            <KpiCard
              title="Riesgo alto" value={resumen.data.productos_riesgo_alto} icon={Gauge}
              state={resumen.data.productos_riesgo_alto > 0 ? 'warning' : 'success'}
              tooltip="Cobertura cerca del lead time -- entra en riesgo de quiebre antes de recibir el próximo pedido."
            />
            <KpiCard
              title="Con recomendación de compra" value={resumen.data.productos_con_recomendacion_compra} icon={PackageCheck}
              tooltip="Artículos donde el modelo sugiere una cantidad de compra mayor a 0."
            />
            <KpiCard
              title="Costo de compra sugerida" value={fmt(resumen.data.costo_total_compra_sugerida)} icon={DollarSign}
              tooltip="Solo para apoyar la decisión de compra -- no es un KPI financiero oficial (eso vive en el Dashboard Ejecutivo)."
            />
          </>
        )}
      </div>

      {resumen.data && (resumen.data.cobertura_mediana_dias != null || resumen.data.cobertura_promedio_dias != null) && (
        <p className="text-xs text-slate-500 -mt-3 flex items-center gap-1.5">
          <Boxes size={13} /> Cobertura del catálogo evaluado: mediana {resumen.data.cobertura_mediana_dias?.toFixed(1) ?? '—'}d ·
          promedio {resumen.data.cobertura_promedio_dias?.toFixed(1) ?? '—'}d
        </p>
      )}

      <AlertasPanel filters={filters} horizonteDias={horizonteDias} />

      {/* Bloque 2: Lista Inteligente de Reabastecimiento */}
      <FilterBar>
        <FilterField label="Horizonte (días)">
          <Select size="sm" value={horizonteDias} onChange={(e) => setHorizonteDias(Number(e.target.value))}>
            <option value={15}>15 días</option>
            <option value={30}>30 días</option>
            <option value={45}>45 días</option>
            <option value={60}>60 días</option>
          </Select>
        </FilterField>
        <FilterField label="Riesgo">
          <Select size="sm" value={riesgo ?? 'ALL'} onChange={(e) => setRiesgo(e.target.value === 'ALL' ? null : e.target.value)}>
            <option value="ALL">Todos</option>
            <option value="critico">Crítico</option>
            <option value="alto">Alto</option>
            <option value="medio">Medio</option>
            <option value="bajo">Bajo</option>
            <option value="sin_demanda">Sin demanda</option>
          </Select>
        </FilterField>
        <FilterField label="Clase ABC">
          <Select size="sm" value={claseAbc ?? 'ALL'} onChange={(e) => setClaseAbc(e.target.value === 'ALL' ? null : e.target.value)}>
            <option value="ALL">Todas</option>
            <option value="A">A</option>
            <option value="B">B</option>
            <option value="C">C</option>
          </Select>
        </FilterField>
        <FilterField label="Clase XYZ">
          <Select size="sm" value={claseXyz ?? 'ALL'} onChange={(e) => setClaseXyz(e.target.value === 'ALL' ? null : e.target.value)}>
            <option value="ALL">Todas</option>
            <option value="X">X (estable)</option>
            <option value="Y">Y (variable)</option>
            <option value="Z">Z (irregular)</option>
          </Select>
        </FilterField>
        <FilterField label="Solo críticos" className="flex-row items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input type="checkbox" checked={soloCriticos} onChange={(e) => setSoloCriticos(e.target.checked)} />
            Ver solo críticos/altos
          </label>
        </FilterField>
      </FilterBar>

      <div className="animate-fade-in-up">
        <DataTable
          columns={columns}
          data={lista.data?.items ?? []}
          rowKey={(p) => p.codart}
          loading={lista.loading}
          error={lista.error ?? undefined}
          onRetry={lista.refetch}
          rowClassName={(p) => riesgoRowTint[p.riesgo]}
          renderExpanded={(row) => <DesgloseReabastecimiento row={row} />}
          responsive
          maxHeight="max-h-[560px]"
          emptyTitle="Sin artículos que reportar"
          emptyDescription="No hay artículos con los filtros actuales."
          pagination={lista.data && (
            <Pagination
              page={lista.data.page} pageSize={lista.data.page_size}
              total={lista.data.total} totalPages={lista.data.total_pages}
              onPageChange={pagination.setPage} onPageSizeChange={pagination.setPageSize}
            />
          )}
        />
      </div>
    </div>
  );
};
