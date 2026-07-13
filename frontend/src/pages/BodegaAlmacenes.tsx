import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeftRight, ArrowLeft, CheckCircle2, Eye, XCircle } from 'lucide-react';
import { AlertBadge } from '../components/ui/AlertBadge';
import { Button } from '../components/ui/Button';
import { DataTable, type DataTableColumn } from '../components/ui/DataTable';
import { Drawer } from '../components/ui/Drawer';
import { Pagination } from '../components/ui/Pagination';
import { BodegaFilterBar } from '../components/bodega/BodegaFilterBar';
import { useInventarioMatriz, useNecesidadCompra, useTransferenciasSugeridas } from '../hooks/bodega';
import { usePagination } from '../hooks/usePagination';
import { useBodegaFiltersStore, toQueryFilters } from '../store/bodegaFiltersStore';
import { fmt } from '../utils/format';
import type { EstadoStock, ProductoMatrizAlmacen, TransferenciaSugerida } from '../types/bodega';

const estadoBadge: Record<EstadoStock, 'critical' | 'warning' | 'neutral' | 'info'> = {
  'Crítico': 'critical', 'Cerca': 'warning', 'Seguro': 'neutral', 'Exceso': 'info',
};

// Tinte de fila por estado (heat-map ligero, mismo patrón que `rowClassName` en DashboardBodega).
const estadoRowTint: Record<EstadoStock, string> = {
  'Crítico': 'bg-red-500/5', 'Cerca': 'bg-amber-500/5', 'Seguro': '', 'Exceso': 'bg-blue-500/5',
};

const ESTADOS: EstadoStock[] = ['Crítico', 'Cerca', 'Seguro', 'Exceso'];

/** §3: Panel de Status de Artículos por Almacén + Matriz de Transferencias
 * Inteligentes + Proyección de necesidades antes de comprar. */
export const BodegaAlmacenes = () => {
  const store = useBodegaFiltersStore();
  const filters = useMemo(() => toQueryFilters(store), [store]);

  const [estadoFiltro, setEstadoFiltro] = useState<string | null>(null);
  const matrizPagination = usePagination([filters, estadoFiltro]);
  const matriz = useInventarioMatriz(filters, estadoFiltro, matrizPagination.query);
  const transferenciasPagination = usePagination(filters);
  const transferencias = useTransferenciasSugeridas(filters, transferenciasPagination.query);
  const plan = useNecesidadCompra(filters, 45, { page: 1, page_size: 50 });

  // Aprobación/rechazo local (H23-5: el ERP es de solo lectura; este estado marca la
  // decisión del encargado y se refleja en el reporte que exporta a gerencia).
  const [decisiones, setDecisiones] = useState<Record<string, 'aprobada' | 'rechazada'>>({});
  const decidir = (key: string, valor: 'aprobada' | 'rechazada') =>
    setDecisiones((d) => ({ ...d, [key]: d[key] === valor ? undefined as never : valor }));

  const [detalle, setDetalle] = useState<TransferenciaSugerida | null>(null);

  const almacenes = useMemo(() => matriz.data?.almacenes ?? [], [matriz.data]);
  const matrizColumns: DataTableColumn<ProductoMatrizAlmacen>[] = useMemo(() => [
    {
      key: 'producto', header: 'Artículo',
      render: (p) => (
        <>
          <p className="font-semibold text-slate-200">{p.nombre}</p>
          <p className="text-xs text-slate-500">{p.codart} · {p.categoria}</p>
        </>
      ),
    },
    ...almacenes.map((a): DataTableColumn<ProductoMatrizAlmacen> => ({
      key: `almacen-${a}`, header: a.replace(/^ALMACEN\s+/i, ''), numeric: true,
      render: (p) => {
        const stock = p.stock_por_almacen[a] ?? 0;
        return <span className={stock <= 0 ? 'text-slate-600' : 'text-slate-300'}>{stock <= 0 ? '·' : stock.toLocaleString('es-EC')}</span>;
      },
    })),
    { key: 'total', header: 'Total', numeric: true, render: (p) => <span className="font-semibold text-slate-100">{p.stock_total.toLocaleString('es-EC')}</span> },
    { key: 'reorden', header: 'Reorden', numeric: true, render: (p) => <span className="text-slate-400">{p.punto_reorden}</span> },
    { key: 'estado', header: 'Estado', render: (p) => <AlertBadge variant={estadoBadge[p.estado]}>{p.estado}</AlertBadge> },
  ], [almacenes]);

  const transferenciasColumns: DataTableColumn<TransferenciaSugerida>[] = [
    {
      key: 'producto', header: 'Producto',
      render: (t) => (
        <>
          <p className="font-semibold text-slate-200">{t.nombre}</p>
          <p className="text-xs text-slate-500 max-w-[320px] whitespace-normal">{t.motivo}</p>
        </>
      ),
    },
    {
      key: 'origen', header: 'Origen (stock · días)',
      render: (t) => (
        <span className="font-mono text-slate-300">
          {t.almacen_origen}<span className="text-slate-500"> · {t.stock_origen} uds · {t.dias_inv_origen != null ? `${t.dias_inv_origen}d` : '∞'}</span>
        </span>
      ),
    },
    {
      key: 'destino', header: 'Destino (stock · días)',
      render: (t) => (
        <span className="font-mono text-slate-300">
          {t.almacen_destino}<span className="text-slate-500"> · {t.stock_destino} uds · {t.dias_inv_destino != null ? `${t.dias_inv_destino}d` : '—'}</span>
        </span>
      ),
    },
    { key: 'cantidad', header: 'Cantidad', numeric: true, render: (t) => <span className="text-cyan-400 font-semibold">{t.cantidad_transferir}</span> },
    { key: 'dias_post', header: 'Días destino post', numeric: true, render: (t) => <span className="text-slate-400">{t.dias_inv_destino_post != null ? `${t.dias_inv_destino_post}d` : '—'}</span> },
    {
      key: 'prioridad', header: 'Prioridad',
      render: (t) => (
        <AlertBadge variant={t.prioridad === 'Alta' ? 'critical' : t.prioridad === 'Media' ? 'warning' : 'neutral'}>
          {t.prioridad}
        </AlertBadge>
      ),
    },
    {
      key: 'accion', header: 'Acción',
      render: (t) => {
        const key = `${t.codart}-${t.almacen_origen}-${t.almacen_destino}`;
        const decision = decisiones[key];
        return (
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => decidir(key, 'aprobada')} aria-label="Aprobar transferencia" title="Aprobar"
              className={`p-1.5 rounded-md transition-colors cursor-pointer focus-ring ${decision === 'aprobada' ? 'bg-emerald-500/20 text-emerald-400' : 'text-slate-500 hover:text-emerald-400'}`}>
              <CheckCircle2 size={16} />
            </button>
            <button type="button" onClick={() => decidir(key, 'rechazada')} aria-label="Rechazar transferencia" title="Rechazar"
              className={`p-1.5 rounded-md transition-colors cursor-pointer focus-ring ${decision === 'rechazada' ? 'bg-red-500/20 text-red-400' : 'text-slate-500 hover:text-red-400'}`}>
              <XCircle size={16} />
            </button>
            <button type="button" onClick={() => setDetalle(t)} aria-label="Ver detalle de la transferencia" title="Ver detalle"
              className="p-1.5 rounded-md transition-colors cursor-pointer focus-ring text-slate-500 hover:text-cyan-400">
              <Eye size={16} />
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <Link to="/bodega" className="text-xs text-slate-500 hover:text-cyan-400 flex items-center gap-1 mb-1 focus-ring rounded">
            <ArrowLeft size={12} /> Dashboard de Bodega
          </Link>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Status de Artículos por Almacén</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Stock consolidado por bodega, transferencias inteligentes y plan de compras (45 días)
          </p>
        </div>
      </div>

      <BodegaFilterBar />

      {/* §3.1 Matriz de inventario por almacén */}
      <div className="animate-fade-in-up">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
          <h3 className="font-sans font-semibold text-slate-200">Inventario por Almacén</h3>
          <div className="flex items-center gap-2">
            {ESTADOS.map((e) => (
              <Button key={e} size="sm" variant={estadoFiltro === e ? 'primary' : 'ghost'}
                onClick={() => setEstadoFiltro(estadoFiltro === e ? null : e)}>
                {e}
              </Button>
            ))}
          </div>
        </div>
        <DataTable
          columns={matrizColumns}
          data={matriz.data?.productos.items ?? []}
          rowKey={(p) => p.codart}
          loading={matriz.loading}
          error={matriz.error ?? undefined}
          onRetry={matriz.refetch}
          rowClassName={(p) => estadoRowTint[p.estado]}
          maxHeight="max-h-[480px]"
          emptyTitle="Sin artículos que reportar"
          emptyDescription="No hay artículos con los filtros actuales."
          pagination={matriz.data && (
            <Pagination
              page={matriz.data.productos.page} pageSize={matriz.data.productos.page_size}
              total={matriz.data.productos.total} totalPages={matriz.data.productos.total_pages}
              onPageChange={matrizPagination.setPage} onPageSizeChange={matrizPagination.setPageSize}
            />
          )}
        />
      </div>

      {/* §3.2 Matriz de transferencias inteligentes */}
      <div className="animate-fade-in-up">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div className="flex items-center gap-3">
            <ArrowLeftRight size={18} className="text-cyan-400" aria-hidden="true" />
            <h3 className="font-sans font-semibold text-slate-200">Transferencias Inteligentes Sugeridas</h3>
          </div>
          {transferencias.data && (
            <span className="text-xs text-emerald-400">
              Ahorro estimado por no comprar: {fmt(transferencias.data.ahorro_total_estimado)}
            </span>
          )}
        </div>
        <DataTable
          columns={transferenciasColumns}
          data={transferencias.data?.sugerencias.items ?? []}
          rowKey={(t) => `${t.codart}-${t.almacen_origen}-${t.almacen_destino}`}
          loading={transferencias.loading}
          error={transferencias.error ?? undefined}
          onRetry={transferencias.refetch}
          rowClassName={(t) => decisiones[`${t.codart}-${t.almacen_origen}-${t.almacen_destino}`] === 'rechazada' ? 'opacity-40' : ''}
          maxHeight="max-h-[420px]"
          emptyTitle="Sin transferencias sugeridas"
          emptyDescription="No hay transferencias sugeridas con los filtros actuales."
          pagination={transferencias.data && (
            <Pagination
              page={transferencias.data.sugerencias.page} pageSize={transferencias.data.sugerencias.page_size}
              total={transferencias.data.sugerencias.total} totalPages={transferencias.data.sugerencias.total_pages}
              onPageChange={transferenciasPagination.setPage} onPageSizeChange={transferenciasPagination.setPageSize}
            />
          )}
        />
      </div>

      {/* §3.3 Plan de compras (horizonte 45 días) */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="card animate-fade-in-up overflow-hidden">
          <div className="p-6 border-b border-slate-800">
            <h3 className="font-sans font-semibold text-slate-200">Recomendados para Compra (próximo mes)</h3>
            {plan.data && (
              <p className="text-xs text-slate-500 mt-1">
                {plan.data.total_productos_a_comprar} productos · {fmt(plan.data.valor_total_compra)} · proyección {plan.data.horizonte_dias} días
              </p>
            )}
          </div>
          <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <tbody className="divide-y divide-slate-800/80">
                {(plan.data?.recomendados.items ?? []).map((p) => (
                  <tr key={p.codart} className="hover:bg-slate-800/20">
                    <td className="px-5 py-2.5">
                      <p className="font-semibold text-slate-200 text-xs">{p.nombre}</p>
                      <p className="text-[11px] text-slate-500">{p.codart} · {p.justificacion}</p>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-cyan-400">{p.cantidad_sugerida} uds</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-300">{fmt(p.costo_total)}</td>
                    <td className="px-4 py-2.5">
                      <AlertBadge variant={p.prioridad === 'Alta' ? 'critical' : p.prioridad === 'Media' ? 'warning' : 'neutral'}>
                        {p.prioridad}
                      </AlertBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card animate-fade-in-up overflow-hidden">
          <div className="p-6 border-b border-slate-800">
            <h3 className="font-sans font-semibold text-slate-200">NO Comprar (excedente / baja rotación)</h3>
            {plan.data && (
              <p className="text-xs text-emerald-400 mt-1">Ahorro estimado: {fmt(plan.data.ahorro_por_no_comprar)}</p>
            )}
          </div>
          <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <tbody className="divide-y divide-slate-800/80">
                {(plan.data?.no_comprar ?? []).map((p) => (
                  <tr key={p.codart} className="hover:bg-slate-800/20">
                    <td className="px-5 py-2.5">
                      <p className="font-semibold text-slate-200 text-xs">{p.nombre}</p>
                      <p className="text-[11px] text-slate-500">{p.codart} · {p.motivo}</p>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-300">{p.stock_actual} uds</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-400">
                      {p.dias_inventario != null ? `${p.dias_inventario} días` : 'sin consumo'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <Drawer open={detalle != null} onClose={() => setDetalle(null)} title={detalle?.nombre ?? 'Detalle de transferencia'}>
        {detalle && (
          <div className="space-y-4 text-sm">
            <div>
              <p className="text-[11px] uppercase tracking-widest text-slate-500">Producto</p>
              <p className="text-slate-200 font-semibold">{detalle.nombre}</p>
              <p className="text-xs text-slate-500">{detalle.codart} · {detalle.categoria}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-widest text-slate-500">Motivo</p>
              <p className="text-slate-300">{detalle.motivo}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500">Origen</p>
                <p className="text-slate-200 font-mono">{detalle.almacen_origen}</p>
                <p className="text-xs text-slate-500">{detalle.stock_origen} uds · {detalle.dias_inv_origen != null ? `${detalle.dias_inv_origen}d` : '∞'}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500">Destino</p>
                <p className="text-slate-200 font-mono">{detalle.almacen_destino}</p>
                <p className="text-xs text-slate-500">{detalle.stock_destino} uds · {detalle.dias_inv_destino != null ? `${detalle.dias_inv_destino}d` : '—'}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500">Cantidad a transferir</p>
                <p className="text-cyan-400 font-mono font-semibold">{detalle.cantidad_transferir}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500">Días destino post-transferencia</p>
                <p className="text-slate-300 font-mono">{detalle.dias_inv_destino_post != null ? `${detalle.dias_inv_destino_post}d` : '—'}</p>
              </div>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-widest text-slate-500">Prioridad</p>
              <AlertBadge variant={detalle.prioridad === 'Alta' ? 'critical' : detalle.prioridad === 'Media' ? 'warning' : 'neutral'}>
                {detalle.prioridad}
              </AlertBadge>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};
