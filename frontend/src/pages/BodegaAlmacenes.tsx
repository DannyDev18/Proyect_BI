import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeftRight, ArrowLeft, CheckCircle2, Eye, ShoppingCart, XCircle } from 'lucide-react';
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
import type { EstadoStock, ProductoCompra, ProductoMatrizAlmacen, TransferenciaSugerida } from '../types/bodega';

const estadoBadge: Record<EstadoStock, 'critical' | 'warning' | 'neutral' | 'info'> = {
  'Crítico': 'critical', 'Cerca': 'warning', 'Seguro': 'neutral', 'Exceso': 'info',
};

// Tinte de fila por estado (heat-map ligero, mismo patrón que `rowClassName` en DashboardBodega).
const estadoRowTint: Record<EstadoStock, string> = {
  'Crítico': 'bg-danger/5', 'Cerca': 'bg-warning/5', 'Seguro': '', 'Exceso': 'bg-primary/5',
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
  // G6 (movido desde DashboardBodega.tsx, D5 docs/features/plan_actualizacion_modulo_bodega.md):
  // horizonte de 45 días (plan de compras del mes), ahora con paginación real.
  const compraPagination = usePagination(filters);
  const plan = useNecesidadCompra(filters, 45, compraPagination.query);

  // Aprobación/rechazo local (H23-5: el ERP es de solo lectura; este estado marca la
  // decisión del encargado y se refleja en el reporte que exporta a gerencia).
  const [decisiones, setDecisiones] = useState<Record<string, 'aprobada' | 'rechazada'>>({});
  const decidir = (key: string, valor: 'aprobada' | 'rechazada') =>
    setDecisiones((d) => ({ ...d, [key]: d[key] === valor ? undefined as never : valor }));

  const [detalle, setDetalle] = useState<TransferenciaSugerida | null>(null);

  const compraColumns: DataTableColumn<ProductoCompra>[] = [
    {
      key: 'producto', header: 'Producto',
      render: (p) => (
        <>
          <p className="font-semibold text-slate-200">{p.nombre}</p>
          <p className="text-xs text-slate-500">{p.codart} · {p.justificacion}</p>
        </>
      ),
    },
    { key: 'stock', header: 'Stock', numeric: true, render: (p) => <span className="text-slate-300">{p.stock_actual}</span> },
    { key: 'salida', header: 'Salida diaria', numeric: true, render: (p) => <span className="text-slate-400">{p.salida_diaria}/día</span> },
    { key: 'llega', header: 'Llega a reorden', numeric: true, render: (p) => <span className="text-slate-400">{p.fecha_estimada_reorden ?? '—'}</span> },
    { key: 'cantidad', header: 'Cant. sugerida', numeric: true, render: (p) => <span className="text-info font-semibold">{p.cantidad_sugerida}</span> },
    { key: 'costo', header: 'Costo total', numeric: true, render: (p) => <span className="text-slate-300">{fmt(p.costo_total)}</span> },
    {
      key: 'prioridad', header: 'Prioridad',
      render: (p) => (
        <AlertBadge variant={p.prioridad === 'Alta' ? 'critical' : p.prioridad === 'Media' ? 'warning' : 'neutral'}>
          {p.prioridad}
        </AlertBadge>
      ),
    },
  ];

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
    { key: 'cantidad', header: 'Cantidad', numeric: true, render: (t) => <span className="text-info font-semibold">{t.cantidad_transferir}</span> },
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
      key: 'confianza', header: 'Confianza',
      render: (t) => t.confianza ? (
        <AlertBadge variant={t.confianza === 'alta' ? 'neutral' : t.confianza === 'media' ? 'warning' : 'critical'}>
          {t.confianza === 'baja' ? 'Baja · revisar' : t.confianza.charAt(0).toUpperCase() + t.confianza.slice(1)}
        </AlertBadge>
      ) : <span className="text-xs text-slate-600">—</span>,
    },
    {
      key: 'accion', header: 'Acción',
      render: (t) => {
        const key = `${t.codart}-${t.almacen_origen}-${t.almacen_destino}`;
        const decision = decisiones[key];
        return (
          <div className="flex items-center gap-1.5">
            <button type="button" onClick={() => decidir(key, 'aprobada')} aria-label="Aprobar transferencia" title="Aprobar"
              className={`p-1.5 rounded-md transition-colors cursor-pointer focus-ring ${decision === 'aprobada' ? 'bg-success/20 text-success' : 'text-slate-500 hover:text-success'}`}>
              <CheckCircle2 size={16} />
            </button>
            <button type="button" onClick={() => decidir(key, 'rechazada')} aria-label="Rechazar transferencia" title="Rechazar"
              className={`p-1.5 rounded-md transition-colors cursor-pointer focus-ring ${decision === 'rechazada' ? 'bg-danger/20 text-danger' : 'text-slate-500 hover:text-danger'}`}>
              <XCircle size={16} />
            </button>
            <button type="button" onClick={() => setDetalle(t)} aria-label="Ver detalle de la transferencia" title="Ver detalle"
              className="p-1.5 rounded-md transition-colors cursor-pointer focus-ring text-slate-500 hover:text-primary">
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
          <Link to="/bodega" className="text-xs text-slate-500 hover:text-primary flex items-center gap-1 mb-1 focus-ring rounded">
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
            <ArrowLeftRight size={18} className="text-info" aria-hidden="true" />
            <h3 className="font-sans font-semibold text-slate-200">Transferencias Inteligentes Sugeridas</h3>
          </div>
          {transferencias.data && (
            <span className="text-xs text-success">
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

      {/* §3.3 / G6 Predicción de Necesidad de Compra (movido desde DashboardBodega.tsx, D5) */}
      <div className="animate-fade-in-up">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div className="flex items-center gap-3">
            <ShoppingCart size={18} className="text-info" />
            <h3 className="font-sans font-semibold text-slate-200">Predicción de Necesidad de Compra</h3>
          </div>
          {plan.data && (
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <span>{plan.data.total_productos_a_comprar} productos · {fmt(plan.data.valor_total_compra)} · proyección {plan.data.horizonte_dias} días</span>
              <span className="text-success">Ahorro por no comprar: {fmt(plan.data.ahorro_por_no_comprar)}</span>
            </div>
          )}
        </div>
        <DataTable
          columns={compraColumns}
          data={plan.data?.recomendados.items ?? []}
          rowKey={(p) => p.codart}
          loading={plan.loading}
          error={plan.error ?? undefined}
          onRetry={plan.refetch}
          rowClassName={(p) => p.prioridad === 'Alta' ? 'bg-danger/5' : ''}
          maxHeight="max-h-[420px]"
          emptyTitle="Sin necesidades de compra"
          emptyDescription="No hay artículos que requieran reposición con los filtros actuales."
          pagination={plan.data && (
            <Pagination
              page={plan.data.recomendados.page} pageSize={plan.data.recomendados.page_size}
              total={plan.data.recomendados.total} totalPages={plan.data.recomendados.total_pages}
              onPageChange={compraPagination.setPage} onPageSizeChange={compraPagination.setPageSize}
            />
          )}
        />
      </div>

      {/* NO Comprar (excedente / baja rotación) */}
      <div className="grid grid-cols-1 gap-4">
        <div className="card animate-fade-in-up overflow-hidden">
          <div className="p-6 border-b border-slate-800">
            <h3 className="font-sans font-semibold text-slate-200">NO Comprar (excedente / baja rotación)</h3>
            {plan.data && (
              <p className="text-xs text-success mt-1">Ahorro estimado: {fmt(plan.data.ahorro_por_no_comprar)}</p>
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
                <p className="text-info font-mono font-semibold">{detalle.cantidad_transferir}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500">Días destino post-transferencia</p>
                <p className="text-slate-300 font-mono">{detalle.dias_inv_destino_post != null ? `${detalle.dias_inv_destino_post}d` : '—'}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500">Prioridad</p>
                <AlertBadge variant={detalle.prioridad === 'Alta' ? 'critical' : detalle.prioridad === 'Media' ? 'warning' : 'neutral'}>
                  {detalle.prioridad}
                </AlertBadge>
              </div>
              {detalle.confianza && (
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-slate-500">Confianza estadística</p>
                  <AlertBadge variant={detalle.confianza === 'alta' ? 'neutral' : detalle.confianza === 'media' ? 'warning' : 'critical'}>
                    {detalle.confianza === 'baja' ? 'Baja · revisar manualmente' : detalle.confianza.charAt(0).toUpperCase() + detalle.confianza.slice(1)}
                  </AlertBadge>
                </div>
              )}
            </div>

            {detalle.justificacion && (
              <div>
                <p className="text-[11px] uppercase tracking-widest text-slate-500 mb-2">
                  Justificación estadística del destino (RN-B9, ventana 90 días)
                </p>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border border-slate-800 rounded-lg p-3">
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Demanda media / mediana</dt>
                    <dd className="text-slate-300 font-mono text-xs">
                      {detalle.justificacion.demanda_media_destino ?? '—'} / {detalle.justificacion.demanda_mediana_destino ?? '—'} uds/día
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Coef. de variación</dt>
                    <dd className="text-slate-300 font-mono text-xs">{detalle.justificacion.coeficiente_variacion_destino ?? '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Tendencia (30 vs 90d)</dt>
                    <dd className="text-slate-300 font-mono text-xs">
                      {detalle.justificacion.tendencia_destino_pct != null ? `${detalle.justificacion.tendencia_destino_pct}%` : '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Venta $ destino (90d)</dt>
                    <dd className="text-success font-mono text-xs">{fmt(detalle.justificacion.venta_monetaria_destino_90d ?? 0)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Meses con venta (últimos 6)</dt>
                    <dd className="text-slate-300 font-mono text-xs">{detalle.justificacion.meses_con_venta_destino}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Cobertura origen post</dt>
                    <dd className="text-slate-300 font-mono text-xs">
                      {detalle.justificacion.dias_cobertura_origen_post != null ? `${detalle.justificacion.dias_cobertura_origen_post}d` : '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Costo logístico estimado</dt>
                    <dd className="text-slate-300 font-mono text-xs">{fmt(detalle.justificacion.costo_logistico_estimado)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase text-slate-500">Beneficio neto estimado</dt>
                    <dd className="text-success font-mono text-xs font-semibold">{fmt(detalle.justificacion.beneficio_neto_estimado)}</dd>
                  </div>
                </dl>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};
