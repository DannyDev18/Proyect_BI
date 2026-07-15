import { useState } from 'react';
import { Activity, Cpu, FileText } from 'lucide-react';
import { useAnomalyDetector, useAuditLogs, useModelsStatus } from '../hooks/admin';
import { usePagination } from '../hooks/usePagination';
import { AlertBadge } from '../components/ui/AlertBadge';
import { SearchInput } from '../components/ui/SearchInput';
import { ChartCard } from '../components/ui/ChartCard';
import { DataTable, type DataTableColumn } from '../components/ui/DataTable';
import { Pagination } from '../components/ui/Pagination';

const levelColor = {
  INFO:  'text-cyan-400',
  WARN:  'text-amber-400',
  ERROR: 'text-red-400',
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
  const anomaly = useAnomalyDetector();
  const models = useModelsStatus();
  const [txId, setTxId] = useState('');

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
        <AlertBadge variant="success" dot>Sistema operativo</AlertBadge>
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
                  <p className="text-red-400 text-sm">{anomaly.error}</p>
                ) : anomaly.data ? (
                  <div className="p-5 rounded-xl border bg-slate-800/40 border-slate-700 space-y-3">
                    <div className="flex justify-between items-center">
                      <p className="text-xs text-slate-500 uppercase tracking-widest">Resultado del análisis</p>
                      <AlertBadge variant={anomaly.data.es_anomalia ? 'critical' : 'success'} dot>
                        {anomaly.data.es_anomalia ? 'Anomalía Detectada' : 'Transacción Normal'}
                      </AlertBadge>
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
                        className={`h-full rounded-full transition-all duration-700 ${anomaly.data.es_anomalia ? 'bg-red-500' : 'bg-green-500'}`}
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
              <p className="text-sm text-red-400">{models.error}</p>
            ) : (
              models.data.map((m) => (
                <div key={m.name} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-slate-700 hover:border-slate-600 transition-colors">
                  <div className="flex items-center gap-3">
                    <Cpu size={16} className="text-cyan-400 flex-shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-slate-200">{m.name}</p>
                      {m.r2 != null && <p className="text-xs text-slate-500 font-mono">R² = {m.r2.toFixed(2)}</p>}
                    </div>
                  </div>
                  <AlertBadge variant={m.status === 'OK' ? 'success' : 'critical'}>{m.status}</AlertBadge>
                </div>
              ))
            )}
          </div>
        </ChartCard>
      </div>

      {/* Audit Log */}
      <div className="animate-fade-in-up stagger-2">
        <div className="flex items-center gap-3 mb-3">
          <FileText size={18} className="text-slate-400" aria-hidden="true" />
          <h3 className="font-sans font-semibold text-slate-200">Log de Auditoría del Sistema</h3>
          <AlertBadge variant="neutral" className="ml-auto">{auditLogs.total} eventos</AlertBadge>
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
          <div className="flex items-center gap-2 text-xs text-red-400 mt-3">
            <Activity size={12} aria-hidden="true" />
            <span>{auditLogs.error}</span>
          </div>
        )}
      </div>
    </div>
  );
};
