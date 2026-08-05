import { useState } from 'react';
import { Activity, AlertTriangle, Cpu, Database, FileText, ShieldCheck, ShieldX, Store, Users } from 'lucide-react';
import { useAdminResumen, useAuditLogs, useModelsStatus, useSystemHealth } from '../hooks/admin';
import { usePagination } from '../hooks/usePagination';
import { Badge } from '../components/ui/Badge';
import { ChartCard } from '../components/ui/ChartCard';
import { DataTable, type DataTableColumn } from '../components/ui/DataTable';
import { KpiCard, KpiCardSkeleton } from '../components/ui/KpiCard';
import { Pagination } from '../components/ui/Pagination';
import { DateField } from '../components/ui/DateField';

const levelColor = {
  INFO:  'text-info',
  WARN:  'text-warning',
  ERROR: 'text-danger',
};

interface AuditEntry {
  ts: string;
  level: string;
  source: string;
  msg: string;
}

const auditColumns: DataTableColumn<AuditEntry>[] = [
  { key: 'ts', header: 'Timestamp', render: (e) => <span className="text-slate-500">{e.ts}</span> },
  {
    key: 'level', header: 'Nivel',
    render: (e) => <span className={`font-semibold ${levelColor[e.level as keyof typeof levelColor] ?? 'text-slate-400'}`}>{e.level}</span>,
  },
  { key: 'source', header: 'Módulo', render: (e) => <span className="text-slate-400">{e.source}</span> },
  { key: 'msg', header: 'Mensaje', render: (e) => <span className="text-slate-300 max-w-xs truncate block">{e.msg}</span> },
];

export const DashboardAdmin = () => {
  const models = useModelsStatus();
  const health = useSystemHealth();
  const resumen = useAdminResumen();

  const [auditFilters, setAuditFilters] = useState({ fecha_desde: '', fecha_hasta: '', usuario: '', modulo: '' });
  const auditPagination = usePagination(auditFilters);
  const auditLogs = useAuditLogs(auditPagination.query, {
    fecha_desde: auditFilters.fecha_desde || undefined,
    fecha_hasta: auditFilters.fecha_hasta || undefined,
    usuario: auditFilters.usuario || undefined,
    modulo: auditFilters.modulo || undefined,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Sistema & Administración</h1>
          <p className="text-sm text-slate-500 mt-0.5">Logs de auditoría · Estado MLOps</p>
        </div>
        <Badge variant="success" dot>Sistema operativo</Badge>
      </div>

      {/* Métricas reales (Fase 5 §5.5, docs/features/plan_correcciones_integrales_sistema.md) */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 stagger-children">
        {resumen.loading ? (
          <><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /><KpiCardSkeleton /></>
        ) : resumen.error ? (
          <div className="col-span-full card">
            <p className="text-sm text-danger p-4">{resumen.error}</p>
          </div>
        ) : (
          <>
            <KpiCard title="Usuarios activos" value={resumen.data?.usuarios_activos ?? '—'} icon={ShieldCheck} trend="neutral" />
            <KpiCard title="Usuarios inactivos" value={resumen.data?.usuarios_inactivos ?? '—'} icon={ShieldX} trend="neutral" />
            <KpiCard title="Vendedores activos" value={resumen.data?.total_vendedores_activos ?? '—'} icon={Users} trend="neutral" />
            <KpiCard title="Bodegas" value={resumen.data?.total_almacenes ?? '—'} icon={Store} trend="neutral" />
          </>
        )}
      </div>

      {/* Estado MLOps */}
      <ChartCard
        title="Estado de Modelos ML (MLOps)"
        badge={{ label: 'En producción', variant: 'live' }}
        height="h-auto"
      >
        <div className="space-y-3 py-2">
          {models.loading ? (
            <p className="text-sm text-slate-500">Cargando estado de modelos…</p>
          ) : models.error ? (
            <p className="text-sm text-danger">{models.error}</p>
          ) : (
            models.data.map((m) => (
              <div key={m.name} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-slate-700 hover:border-slate-600 transition-colors">
                <div className="flex items-center gap-3">
                  <Cpu size={16} className="text-info flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-slate-200">{m.name}</p>
                    {m.r2 != null && <p className="text-xs text-slate-500 font-mono">R² = {m.r2.toFixed(2)}</p>}
                  </div>
                </div>
                <Badge variant={m.status === 'OK' ? 'success' : 'danger'}>{m.status}</Badge>
              </div>
            ))
          )}
        </div>
      </ChartCard>

      {/* Panel de salud del sistema (Fase 2 Admin, docs/features/plan_correcciones_pendientes.md §3) */}
      <div className="animate-fade-in-up stagger-1">
        <div className="flex items-center gap-3 mb-3">
          <Database size={18} className="text-slate-400" aria-hidden="true" />
          <h3 className="font-sans font-semibold text-slate-200">Salud del Sistema</h3>
          {health.data && (
            <Badge variant={health.data.logins_fallidos_conteo > 0 ? 'warning' : 'success'} className="ml-auto">
              {health.data.logins_fallidos_conteo} logins fallidos (últimas {health.data.logins_fallidos_ventana_horas}h)
            </Badge>
          )}
        </div>

        {health.loading ? (
          <p className="text-sm text-slate-500">Cargando estado del ETL…</p>
        ) : health.error ? (
          <p className="text-sm text-danger">{health.error}</p>
        ) : (
          <div className="card p-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 uppercase tracking-wide">
                  <th className="pb-2 font-semibold">Tabla destino</th>
                  <th className="pb-2 font-semibold">Estado</th>
                  <th className="pb-2 font-semibold">Última carga OK</th>
                  <th className="pb-2 font-semibold">Filas cargadas</th>
                  <th className="pb-2 font-semibold">Duración (s)</th>
                  <th className="pb-2 font-semibold">Error</th>
                </tr>
              </thead>
              <tbody>
                {(health.data?.etl_detalle ?? []).map((e) => (
                  <tr key={e.tabla_destino} className="border-t border-slate-800">
                    <td className="py-1.5 font-mono text-slate-300">{e.tabla_destino}</td>
                    <td className="py-1.5">
                      <Badge variant={e.estado === 'SUCCESS' ? 'success' : 'danger'}>{e.estado ?? '—'}</Badge>
                    </td>
                    <td className="py-1.5 text-slate-500">{e.ultimo_etl_ok ? new Date(e.ultimo_etl_ok).toLocaleString() : '—'}</td>
                    <td className="py-1.5 font-mono text-slate-400">{e.registros_cargados ?? '—'}</td>
                    <td className="py-1.5 font-mono text-slate-400">{e.duracion_seg ?? '—'}</td>
                    <td className="py-1.5 text-danger max-w-xs truncate">
                      {e.mensaje_error && <AlertTriangle size={12} className="inline mr-1" aria-hidden="true" />}
                      {e.mensaje_error ?? ''}
                    </td>
                  </tr>
                ))}
                {(health.data?.etl_detalle ?? []).length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-4 text-center text-slate-600">Sin corridas de ETL registradas.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Audit Log */}
      <div className="animate-fade-in-up stagger-2">
        <div className="flex items-center gap-3 mb-3">
          <FileText size={18} className="text-slate-400" aria-hidden="true" />
          <h3 className="font-sans font-semibold text-slate-200">Log de Auditoría del Sistema</h3>
          <Badge variant="neutral" className="ml-auto">{auditLogs.total} eventos</Badge>
        </div>

        <div className="card p-3 mb-3 grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="space-y-1">
            <label htmlFor="audit-desde" className="text-[11px] font-semibold uppercase text-slate-500">Desde</label>
            <DateField
              id="audit-desde"
              value={auditFilters.fecha_desde}
              onChange={(e) => setAuditFilters({ ...auditFilters, fecha_desde: e.target.value })}
              className="w-full"
              size="sm"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="audit-hasta" className="text-[11px] font-semibold uppercase text-slate-500">Hasta</label>
            <DateField
              id="audit-hasta"
              value={auditFilters.fecha_hasta}
              onChange={(e) => setAuditFilters({ ...auditFilters, fecha_hasta: e.target.value })}
              className="w-full"
              size="sm"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="audit-usuario" className="text-[11px] font-semibold uppercase text-slate-500">Usuario</label>
            <input
              id="audit-usuario" type="text" placeholder="codusu"
              value={auditFilters.usuario}
              onChange={(e) => setAuditFilters({ ...auditFilters, usuario: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-2 py-1.5 text-xs text-slate-200 outline-none placeholder-slate-700 focus-ring"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="audit-modulo" className="text-[11px] font-semibold uppercase text-slate-500">Módulo</label>
            <input
              id="audit-modulo" type="text" placeholder="ej: analytics"
              value={auditFilters.modulo}
              onChange={(e) => setAuditFilters({ ...auditFilters, modulo: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-2 py-1.5 text-xs text-slate-200 outline-none placeholder-slate-700 focus-ring"
            />
          </div>
        </div>

        <DataTable
          className="font-mono text-xs"
          columns={auditColumns}
          data={auditLogs.data}
          loading={auditLogs.loading}
          rowKey={(e) => `${e.ts}-${e.source}`}
          emptyTitle="Sin eventos registrados"
          emptyDescription="No hay actividad de auditoría en el período/filtros seleccionados."
        />
        <Pagination
          page={auditPagination.page}
          pageSize={auditPagination.pageSize}
          total={auditLogs.total}
          totalPages={auditLogs.totalPages}
          onPageChange={auditPagination.setPage}
          onPageSizeChange={auditPagination.setPageSize}
        />
        {auditLogs.error && (
          <div className="flex items-center gap-2 text-xs text-danger mt-3">
            <Activity size={12} aria-hidden="true" />
            <span>{auditLogs.error}</span>
          </div>
        )}
      </div>
    </div>
  );
};
