import { useState, useEffect, useMemo } from 'react';
import { Wallet, Gift } from 'lucide-react';

import { usePeriods, useCommissionTracking } from '../../hooks/goals';
import type { GoalPeriodOption, NivelComision, VendorCommissionRow } from '../../types/goals';
import { fmtMoney, pct } from '../../utils/format';
import { Select } from '../ui/Select';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { AlertBadge } from '../ui/AlertBadge';

const NIVEL_VARIANT: Record<NivelComision, 'success' | 'info' | 'warning' | 'critical'> = {
  EXCELENTE: 'success',
  META: 'info',
  CERCA: 'warning',
  LEJOS: 'critical',
};

const NIVEL_LABEL: Record<NivelComision, string> = {
  EXCELENTE: 'Excelente',
  META: 'Meta',
  CERCA: 'Cerca',
  LEJOS: 'Lejos',
};

/** Panel gerencial de comisiones (docs/modulo_metas.md): cumplimiento real (Venta Neta)
 * y comisión devengada por vendedor -- cierra el hallazgo R-1 de
 * docs/auditoria/14_...md (`GoalsConsole` solo muestra la meta configurada, sin venta
 * real). Componente hermano de `GoalsConsole`, mismo sistema visual (DataTable) para no
 * fragmentar el look del panel gerencial de Metas. */
export function CommissionTracker() {
  const [period, setPeriod] = useState({ anio: new Date().getFullYear(), mes: new Date().getMonth() + 1 });
  const [hasInitializedPeriod, setHasInitializedPeriod] = useState(false);

  const periods = usePeriods();
  const months = useMemo<GoalPeriodOption[]>(() => periods.data.map((d) => {
    const date = new Date(d.anio, d.mes - 1, 1);
    const name = date.toLocaleString('es-ES', { month: 'long' });
    return { anio: d.anio, mes: d.mes, label: `${name.charAt(0).toUpperCase() + name.slice(1)} ${d.anio}` };
  }), [periods.data]);

  useEffect(() => {
    if (!hasInitializedPeriod && months.length > 0) {
      setPeriod({ anio: months[0].anio, mes: months[0].mes });
      setHasInitializedPeriod(true);
    }
  }, [months, hasInitializedPeriod]);

  const tracking = useCommissionTracking(period.anio, period.mes);
  const totalComision = tracking.data.reduce((sum, f) => sum + f.comision_devengada, 0);
  // Comisiones Variables (docs/features/plan_integracion_comisiones_variables.md):
  // `comision_variable` solo viene poblado cuando el backend corre en modo "sombra"/
  // "variable" (COMISION_MODO) -- la columna se agrega dinámicamente, sin romper el
  // panel para instalaciones que sigan en modo "plana".
  const modoSombraActivo = tracking.data.some((f) => f.comision_variable != null);
  const totalComisionVariable = tracking.data.reduce((sum, f) => sum + (f.comision_variable ?? 0), 0);

  const columns: DataTableColumn<VendorCommissionRow>[] = [
    { key: 'vendedor', header: 'Vendedor', render: (f) => <span className="font-semibold text-primary">{f.vendedor}</span> },
    { key: 'venta_real', header: 'Venta Neta', render: (f) => <span className="text-slate-300">{fmtMoney(f.venta_real)}</span> },
    { key: 'monto_meta', header: 'Meta', render: (f) => <span className="text-slate-400">{fmtMoney(f.monto_meta)}</span> },
    { key: 'pct_cumplimiento', header: 'Cumplimiento', render: (f) => <span className="text-slate-300">{pct(f.pct_cumplimiento)}</span> },
    {
      key: 'nivel',
      header: 'Nivel',
      render: (f) => <AlertBadge variant={NIVEL_VARIANT[f.nivel]}>{NIVEL_LABEL[f.nivel]}</AlertBadge>,
    },
    { key: 'tasa', header: 'Tasa', render: (f) => <span className="text-slate-400">{f.tasa_aplicada_pct.toFixed(2)}%</span> },
    {
      key: 'comision',
      header: 'Comisión (plana)',
      numeric: true,
      render: (f) => <span className="font-semibold text-primary">{fmtMoney(f.comision_devengada)}</span>,
    },
    ...(modoSombraActivo ? [{
      key: 'comision_variable',
      header: 'Comisión (variable · piloto)',
      numeric: true,
      render: (f: VendorCommissionRow) => (
        f.comision_variable != null
          ? <span className="font-semibold text-warning">{fmtMoney(f.comision_variable)}</span>
          : <span className="text-slate-600">—</span>
      ),
    } as DataTableColumn<VendorCommissionRow>] : []),
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Wallet className="w-8 h-8 text-primary" aria-hidden="true" />
          <h2 className="text-2xl font-bold tracking-tight">Comisiones devengadas</h2>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400" htmlFor="commission-tracker-period">Período</label>
          <Select
            id="commission-tracker-period"
            onChange={(e) => {
              const selectedValue = e.target.value;
              const selectedMonth = months.find((m) => `${m.anio}-${m.mes}` === selectedValue);
              if (selectedMonth) setPeriod({ anio: selectedMonth.anio, mes: selectedMonth.mes });
            }}
            value={`${period.anio}-${period.mes}`}
          >
            {months.map((m, idx) => (
              <option key={idx} value={`${m.anio}-${m.mes}`}>{m.label}</option>
            ))}
          </Select>
        </div>
      </div>

      <div className="bg-slate-800/50 rounded-lg p-5 border border-slate-700/50">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-200">Cumplimiento real y comisión por vendedor</h3>
          <div className="flex items-center gap-4 text-sm text-slate-400">
            <div className="flex items-center gap-1.5">
              <Gift size={14} className="text-primary" aria-hidden="true" />
              Total plana: <span className="font-mono text-primary font-semibold">{fmtMoney(totalComision)}</span>
            </div>
            {modoSombraActivo && (
              <div className="flex items-center gap-1.5">
                <Gift size={14} className="text-warning" aria-hidden="true" />
                Total variable: <span className="font-mono text-warning font-semibold">{fmtMoney(totalComisionVariable)}</span>
              </div>
            )}
          </div>
        </div>

        <DataTable
          columns={columns}
          data={tracking.data}
          rowKey={(f) => f.id}
          loading={tracking.loading}
          error={tracking.error ?? undefined}
          onRetry={tracking.refetch}
          emptyTitle="No hay metas configuradas para este período"
        />
      </div>
    </div>
  );
}
