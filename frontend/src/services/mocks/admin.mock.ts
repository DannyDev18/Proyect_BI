// Placeholder data — wire to GET /api/v1/admin/audit-logs and GET /api/v1/admin/mlops/status
// (the latter already has a service wrapper in services/admin.ts::getMLOpsStatus, currently unused)
// once those endpoints return this shape from the backend.
import type { AuditLogEntry, ModelStatus } from '../../types/admin';

export const AUDIT_ENTRIES: AuditLogEntry[] = [
  { ts: '2026-07-03 10:15:22', level: 'INFO',  source: 'ETL_WORKER',   msg: 'Data synchronization completed. 5 200 rows inserted to PostgreSQL.' },
  { ts: '2026-07-03 11:42:01', level: 'INFO',  source: 'ML_PIPELINE',  msg: 'Random Forest re-trained. R² = 0.89 · RMSE = 1 240.' },
  { ts: '2026-07-03 12:05:14', level: 'WARN',  source: 'API_AUTH',     msg: 'Access forbidden (403) — Rol "ventas" tried /api/v1/analytics/admin/anomalies.' },
  { ts: '2026-07-03 12:12:15', level: 'INFO',  source: 'ADMIN_PANEL',  msg: 'User admin@empresa.com logged in from 192.168.0.10.' },
  { ts: '2026-07-03 14:00:00', level: 'INFO',  source: 'ML_PIPELINE',  msg: 'Isolation Forest model loaded. 0 warnings.' },
  { ts: '2026-07-03 14:30:05', level: 'ERROR', source: 'ETL_WORKER',   msg: 'SAP connection timeout. Retry 1/3.' },
];

export const MODEL_STATUS: ModelStatus[] = [
  { name: 'Random Forest (Ventas)',       r2: 0.89, status: 'OK' },
  { name: 'Isolation Forest (Anomalías)', r2: null, status: 'OK' },
  { name: 'K-Means RFM (Seg. Clientes)',  r2: null, status: 'OK' },
  { name: 'Apriori (Cross-sell)',         r2: null, status: 'OK' },
];
