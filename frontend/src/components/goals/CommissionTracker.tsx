import { useState, useEffect, useMemo } from 'react';
import { Wallet, Loader2, Gift } from 'lucide-react';

import { usePeriods, useCommissionTracking } from '../../hooks/goals';
import type { GoalPeriodOption, NivelComision } from '../../types/goals';
import { fmtMoney, pct } from '../../utils/format';

const NIVEL_STYLES: Record<NivelComision, string> = {
  EXCELENTE: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/25',
  META: 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/25',
  CERCA: 'bg-amber-500/10 text-amber-400 border border-amber-500/25',
  LEJOS: 'bg-rose-500/10 text-rose-400 border border-rose-500/25',
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
 * real). Componente hermano de `GoalsConsole`, mismo sistema visual (tabla en Tailwind
 * plano, sin `ChartCard`) para no fragmentar el look del panel gerencial de Metas. */
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

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Wallet className="w-8 h-8 text-teal-400" />
          <h2 className="text-2xl font-bold tracking-tight">Comisiones devengadas</h2>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400">Período</label>
          <select
            className="bg-slate-800 p-2 rounded text-sm border border-slate-700 cursor-pointer focus:border-teal-400 focus:outline-none transition-colors"
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
          </select>
        </div>
      </div>

      <div className="bg-slate-800/50 rounded-lg p-5 border border-slate-700/50">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-200">Cumplimiento real y comisión por vendedor</h3>
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            <Gift size={14} className="text-teal-400" />
            Total del período: <span className="font-mono text-teal-300 font-semibold">{fmtMoney(totalComision)}</span>
          </div>
        </div>

        {tracking.loading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-10 h-10 animate-spin text-teal-400" />
          </div>
        ) : tracking.error ? (
          <p className="text-red-400 text-sm py-6 text-center">{tracking.error}</p>
        ) : tracking.data.length === 0 ? (
          <div className="text-center py-10 text-slate-400">No hay metas configuradas para este período.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 font-medium">
                  <th className="p-3">Vendedor</th>
                  <th className="p-3">Venta Neta</th>
                  <th className="p-3">Meta</th>
                  <th className="p-3">Cumplimiento</th>
                  <th className="p-3">Nivel</th>
                  <th className="p-3">Tasa</th>
                  <th className="p-3 text-right">Comisión</th>
                </tr>
              </thead>
              <tbody>
                {tracking.data.map((f) => (
                  <tr key={f.id} className="border-b border-slate-800 hover:bg-slate-800/50 transition-all duration-150">
                    <td className="p-3 font-semibold text-teal-50">{f.vendedor}</td>
                    <td className="p-3 font-mono text-slate-300">{fmtMoney(f.venta_real)}</td>
                    <td className="p-3 font-mono text-slate-400">{fmtMoney(f.monto_meta)}</td>
                    <td className="p-3 font-mono text-slate-300">{pct(f.pct_cumplimiento)}</td>
                    <td className="p-3">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${NIVEL_STYLES[f.nivel]}`}>
                        {NIVEL_LABEL[f.nivel]}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-slate-400">{f.tasa_aplicada_pct.toFixed(2)}%</td>
                    <td className="p-3 text-right font-mono font-semibold text-teal-300">{fmtMoney(f.comision_devengada)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
