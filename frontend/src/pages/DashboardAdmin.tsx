import { useState } from 'react';
import { Activity, Cpu, FileText } from 'lucide-react';
import { useAnomalyDetector } from '../hooks/useAnalytics';
import { AlertBadge } from '../components/ui/AlertBadge';
import { SearchInput } from '../components/ui/SearchInput';
import { ChartCard } from '../components/ui/ChartCard';

// ─── Static audit log entries (Live polling to be wired when /admin/audit-logs endpoint is ready) ───
const AUDIT_ENTRIES = [
  { ts: '2026-07-03 10:15:22', level: 'INFO',  source: 'ETL_WORKER',    msg: 'Data synchronization completed. 5 200 rows inserted to PostgreSQL.' },
  { ts: '2026-07-03 11:42:01', level: 'INFO',  source: 'ML_PIPELINE',  msg: 'Random Forest re-trained. R² = 0.89 · RMSE = 1 240.' },
  { ts: '2026-07-03 12:05:14', level: 'WARN',  source: 'API_AUTH',     msg: 'Access forbidden (403) — Rol "ventas" tried /api/v1/analytics/admin/anomalies.' },
  { ts: '2026-07-03 12:12:15', level: 'INFO',  source: 'ADMIN_PANEL',  msg: 'User admin@empresa.com logged in from 192.168.0.10.' },
  { ts: '2026-07-03 14:00:00', level: 'INFO',  source: 'ML_PIPELINE',  msg: 'Isolation Forest model loaded. 0 warnings.' },
  { ts: '2026-07-03 14:30:05', level: 'ERROR', source: 'ETL_WORKER',   msg: 'SAP connection timeout. Retry 1/3.' },
];

const levelColor = {
  INFO:  'text-cyan-400',
  WARN:  'text-amber-400',
  ERROR: 'text-red-400',
};

// ─── MLOps status cards (static — wire to /admin/mlops/status when ready) ───
const MODEL_STATUS = [
  { name: 'Random Forest (Ventas)',      r2: 0.89, status: 'OK' },
  { name: 'Isolation Forest (Anomalías)', r2: null, status: 'OK' },
  { name: 'K-Means RFM (Seg. Clientes)', r2: null, status: 'OK' },
  { name: 'Apriori (Cross-sell)',         r2: null, status: 'OK' },
];

export const DashboardAdmin = () => {
  const anomaly = useAnomalyDetector();
  const [txId, setTxId] = useState('');

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
            {MODEL_STATUS.map((m) => (
              <div key={m.name} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/40 border border-slate-700 hover:border-slate-600 transition-colors">
                <div className="flex items-center gap-3">
                  <Cpu size={16} className="text-cyan-400 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-slate-200">{m.name}</p>
                    {m.r2 != null && <p className="text-xs text-slate-500 font-mono">R² = {m.r2}</p>}
                  </div>
                </div>
                <AlertBadge variant="success">{m.status}</AlertBadge>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      {/* Audit Log */}
      <div className="card animate-fade-in-up stagger-2 overflow-hidden">
        <div className="p-5 border-b border-slate-800 flex items-center gap-3">
          <FileText size={18} className="text-slate-400" />
          <h3 className="font-display font-semibold text-slate-200">Log de Auditoría del Sistema</h3>
          <AlertBadge variant="neutral" className="ml-auto">Últimas 24 h</AlertBadge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs whitespace-nowrap font-mono">
            <thead className="bg-slate-950/60 text-slate-600 uppercase tracking-wide">
              <tr>
                <th className="px-6 py-3">Timestamp</th>
                <th className="px-6 py-3">Nivel</th>
                <th className="px-6 py-3">Módulo</th>
                <th className="px-6 py-3">Mensaje</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {AUDIT_ENTRIES.map((e, i) => (
                <tr key={i} className="hover:bg-slate-800/20 transition-colors">
                  <td className="px-6 py-3 text-slate-500">{e.ts}</td>
                  <td className={`px-6 py-3 font-semibold ${levelColor[e.level as keyof typeof levelColor] ?? 'text-slate-400'}`}>
                    {e.level}
                  </td>
                  <td className="px-6 py-3 text-slate-400">{e.source}</td>
                  <td className="px-6 py-3 text-slate-300 max-w-xs truncate">{e.msg}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <Activity size={12} />
            <span>Polling en tiempo real disponible cuando se exponga <code className="text-slate-500">GET /api/v1/admin/audit-logs</code>.</span>
          </div>
        </div>
      </div>
    </div>
  );
};
