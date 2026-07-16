import { useState } from 'react';
import { Activity, AlertTriangle, Cpu, Database, FileText, ShieldAlert } from 'lucide-react';
import {
  useActualizarAnomaliaRevision, useAnomaliaRevisiones, useAnomalyDetector, useAuditLogs, useModelsStatus,
  useSystemHealth,
} from '../hooks/admin';
import { usePagination } from '../hooks/usePagination';
import { Badge } from '../components/ui/Badge';
import { SearchInput } from '../components/ui/SearchInput';
import { ChartCard } from '../components/ui/ChartCard';
import { DataTable, type DataTableColumn } from '../components/ui/DataTable';
import { Pagination } from '../components/ui/Pagination';
import { Select } from '../components/ui/Select';
import type { AnomaliaEstado, AnomaliaRevision } from '../types/admin';

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

const estadoBadgeVariant: Record<AnomaliaEstado, 'danger' | 'warning' | 'neutral' | 'success'> = {
  nueva: 'danger',
  revisada: 'neutral',
  descartada: 'neutral',
  confirmada: 'warning',
};

export const DashboardAdmin = () => {
  const anomaly = useAnomalyDetector();
  const models = useModelsStatus();
  const health = useSystemHealth();
  const [txId, setTxId] = useState('');

  // Fase 2 Admin (docs/features/plan_correcciones_pendientes.md §3): triage de
  // anomalías -- separa "nueva" de lo ya trabajado, en vez de un resultado puntual.
  const [revisionEstado, setRevisionEstado] = useState<AnomaliaEstado>('nueva');
  const revisionPagination = usePagination(revisionEstado);
  const revisiones = useAnomaliaRevisiones(revisionPagination.query, revisionEstado);
  const actualizarRevision = useActualizarAnomaliaRevision();

  const revisionColumns: DataTableColumn<AnomaliaRevision>[] = [
    {
      key: 'fecha_deteccion', header: 'Detectada',
      render: (r) => <span className="text-slate-500 font-mono text-xs">{new Date(r.fecha_deteccion).toLocaleString()}</span>,
    },
    { key: 'transaccion_id', header: 'Transacción', render: (r) => <span className="font-mono text-slate-300">{r.transaccion_id}</span> },
    { key: 'score', header: 'Score', render: (r) => <span className="font-mono text-slate-400">{r.score.toFixed(4)}</span> },
    {
      key: 'estado', header: 'Estado',
      render: (r) => <Badge variant={estadoBadgeVariant[r.estado]}>{r.estado}</Badge>,
    },
    {
      key: 'acciones', header: 'Acción',
      render: (r) => (
        r.estado === 'nueva' ? (
          <div className="flex gap-1.5">
            <button
              type="button"
              disabled={actualizarRevision.loading}
              onClick={() => actualizarRevision.execute({ id: r.id, estado: 'confirmada' })}
              className="px-2 py-1 rounded text-xs font-medium bg-danger/10 text-danger border border-danger/30 hover:bg-danger/20 transition-colors disabled:opacity-50"
            >
              Confirmar fraude
            </button>
            <button
              type="button"
              disabled={actualizarRevision.loading}
              onClick={() => actualizarRevision.execute({ id: r.id, estado: 'descartada' })}
              className="px-2 py-1 rounded text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700 hover:border-slate-600 transition-colors disabled:opacity-50"
            >
              Descartar
            </button>
          </div>
        ) : (
          <span className="text-xs text-slate-600">
            {r.fecha_revision ? new Date(r.fecha_revision).toLocaleDateString() : '—'}
          </span>
        )
      ),
    },
  ];

  const [auditFilters, setAuditFilters] = useState({ fecha_desde: '', fecha_hasta: '', usuario: '', modulo: '' });
  const auditPagination = usePagination(auditFilters);
  const auditLogs = useAuditLogs(auditPagination.query, {
    fecha_desde: auditFilters.fecha_desde || undefined,
    fecha_hasta: auditFilters.fecha_hasta || undefined,
    usuario: auditFilters.usuario || undefined,
    modulo: auditFilters.modulo || undefined,
  });

  const handleSearch = (val: string) => {
    setTxId(val);
    anomaly.execute(val);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Sistema & Administración</h1>
          <p className="text-sm text-slate-500 mt-0.5">Logs de auditoría · Estado MLOps · Detección de anomalías</p>
        </div>
        <Badge variant="success" dot>Sistema operativo</Badge>
      </div>

      {/* Main 2-column grid */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

        {/* Detección de Anomalías (Isolation Forest) */}
        <ChartCard
          title="Detector de Anomalías Transaccionales"
          badge={{ label: 'Isolation Forest', variant: 'ml' }}
          height="h-auto"
        >
          <div className="space-y-4 py-2">
            <SearchInput
              placeholder="ID de transacción (ej: TXN-99821)"
              onSearch={handleSearch}
              loading={anomaly.loading}
              label="Transacción a evaluar"
            />
            {txId && !anomaly.loading && (
              <div className="animate-fade-in">
                {anomaly.error ? (
                  <p className="text-danger text-sm">{anomaly.error}</p>
                ) : anomaly.data ? (
                  <div className="p-5 rounded-xl border bg-slate-800/40 border-slate-700 space-y-3">
                    <div className="flex justify-between items-center">
                      <p className="text-xs text-slate-500 uppercase tracking-widest">Resultado del análisis</p>
                      <Badge variant={anomaly.data.es_anomalia ? 'danger' : 'success'} dot>
                        {anomaly.data.es_anomalia ? 'Anomalía Detectada' : 'Transacción Normal'}
                      </Badge>
                    </div>
                    <div className="flex gap-6">
                      <div>
                        <p className="text-xs text-slate-500">Anomaly Score</p>
                        <p className="font-mono text-2xl font-semibold text-slate-100">{anomaly.data.score.toFixed(4)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-slate-500">Transacción ID</p>
                        <p className="font-mono text-sm text-slate-300 mt-1">{anomaly.data.transaccion_id}</p>
                      </div>
                    </div>
                    {/* Score visual bar */}
                    <div className="h-2.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${anomaly.data.es_anomalia ? 'bg-danger' : 'bg-success'}`}
                        style={{ width: `${Math.min(100, Math.abs(anomaly.data.score) * 100)}%` }}
                      />
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </ChartCard>

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
      </div>

      {/* Triage de Anomalías (Fase 2, docs/features/plan_correcciones_pendientes.md §3) */}
      <div className="animate-fade-in-up stagger-1">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <ShieldAlert size={18} className="text-slate-400" aria-hidden="true" />
          <h3 className="font-sans font-semibold text-slate-200">Triage de Anomalías</h3>
          <Badge variant="neutral">{revisiones.total} en "{revisionEstado}"</Badge>
          <div className="ml-auto">
            <Select
              size="sm"
              value={revisionEstado}
              onChange={(e) => setRevisionEstado(e.target.value as AnomaliaEstado)}
            >
              <option value="nueva">Nuevas</option>
              <option value="confirmada">Confirmadas</option>
              <option value="descartada">Descartadas</option>
              <option value="revisada">Revisadas</option>
            </Select>
          </div>
        </div>

        <DataTable
          columns={revisionColumns}
          data={revisiones.data}
          loading={revisiones.loading}
          rowKey={(r) => r.id}
          emptyTitle={revisionEstado === 'nueva' ? 'Sin anomalías nuevas' : `Sin anomalías en estado "${revisionEstado}"`}
          emptyDescription="Las transacciones calificadas como anómalas por el detector aparecen aquí para su revisión."
        />
        <Pagination
          page={revisionPagination.page}
          pageSize={revisionPagination.pageSize}
          total={revisiones.total}
          totalPages={revisiones.totalPages}
          onPageChange={revisionPagination.setPage}
          onPageSizeChange={revisionPagination.setPageSize}
        />
        {(revisiones.error || actualizarRevision.error) && (
          <div className="flex items-center gap-2 text-xs text-danger mt-3">
            <Activity size={12} aria-hidden="true" />
            <span>{revisiones.error ?? actualizarRevision.error}</span>
          </div>
        )}
      </div>

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
            <input
              id="audit-desde" type="date"
              value={auditFilters.fecha_desde}
              onChange={(e) => setAuditFilters({ ...auditFilters, fecha_desde: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-2 py-1.5 text-xs text-slate-200 outline-none focus-ring"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="audit-hasta" className="text-[11px] font-semibold uppercase text-slate-500">Hasta</label>
            <input
              id="audit-hasta" type="date"
              value={auditFilters.fecha_hasta}
              onChange={(e) => setAuditFilters({ ...auditFilters, fecha_hasta: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-2 py-1.5 text-xs text-slate-200 outline-none focus-ring"
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
