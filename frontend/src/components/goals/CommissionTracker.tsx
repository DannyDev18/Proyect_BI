import { useState, useEffect, useMemo } from 'react';
import { Wallet, Gift } from 'lucide-react';

import { usePeriods, useCommissionTracking } from '../../hooks/goals';
import { useVendedores } from '../../hooks/gerencia';
import type { GoalPeriodOption, VendorCommissionRow, ComponenteFormulaTraza } from '../../types/goals';
import { fmtMoney, pct } from '../../utils/format';
import { Select } from '../ui/Select';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { Badge } from '../ui/Badge';

// Misma fuente de etiquetas que `commission_engine.ETIQUETAS_COMPONENTES_FORMULA`
// (backend) -- duplicada aquí por simplicidad, igual patrón que `COMPONENTE_LABEL`
// en `CommissionConfigPanel.tsx`.
const ETIQUETA_COMPONENTE: Record<string, string> = {
  base_lineas_venta: 'Líneas de venta (margen/categoría)',
  base_cobranza: 'Cobranza (por tramo de días de cobro)',
  contado_agencia: 'Ventas de contado de la agencia',
  factor_tipo_vendedor: 'Factor de tipo de vendedor',
  multiplicador_cumplimiento: 'Multiplicador de cumplimiento de meta',
  devoluciones: 'Devoluciones estimadas',
  bonos: 'Bonos (cross-sell, cliente nuevo, cobranza sana)',
};

function badgeVariantParaNivel(nivel: string): 'success' | 'info' | 'warning' | 'danger' {
  const n = nivel.toLowerCase();
  if (n.includes('sin comisión') || n.includes('lejos')) return 'danger';
  if (n.includes('sobrecumplimiento') || n.includes('excelente')) return 'success';
  if (n.includes('cerca')) return 'warning';
  return 'info';
}

function DesgloseComisionVendedor({ row }: { row: VendorCommissionRow }) {
  if (row.componentes.length === 0) {
    return <p className="p-4 text-xs text-slate-500">Sin desglose disponible para este vendedor.</p>;
  }
  return (
    <div className="p-4">
      <p className="text-xs font-semibold text-slate-400 mb-2">Cómo se construyó esta comisión</p>
      <ol className="space-y-1.5">
        {row.componentes.map((c: ComponenteFormulaTraza) => (
          <li key={c.orden} className="flex items-center justify-between gap-4 text-xs">
            <span className="text-slate-400">
              <span className="font-mono text-slate-600 mr-2">{c.orden}.</span>
              {c.operador === 'sumar' && <span className="text-success mr-1">+</span>}
              {c.operador === 'restar' && <span className="text-danger mr-1">−</span>}
              {c.operador === 'multiplicar' && <span className="text-info mr-1">×</span>}
              {ETIQUETA_COMPONENTE[c.componente] ?? c.componente}
            </span>
            <span className="flex items-center gap-3 font-mono">
              <span className="text-slate-300">
                {c.operador === 'multiplicar' ? `${c.monto.toFixed(4)}x` : fmtMoney(c.monto)}
              </span>
              <span className="text-slate-600" title="Acumulado de la fórmula después de este paso">
                = {fmtMoney(c.acumulado_tras_paso)}
              </span>
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-2 pt-2 border-t border-slate-800 flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-300">Comisión final</span>
        <span className="font-mono font-semibold text-primary">{fmtMoney(row.comision_devengada)}</span>
      </div>
      {row.comision_devengada === 0 && row.pct_cumplimiento < 100 && (
        <p className="mt-2 text-xs text-danger">
          Este vendedor no alcanzó el umbral mínimo de cumplimiento ({row.nivel}) -- la comisión final es $0,
          bonos incluidos.
        </p>
      )}
    </div>
  );
}

/** Panel gerencial de comisiones (docs/modulo_metas.md): cumplimiento real (Venta Neta)
 * y comisión devengada por vendedor -- cierra el hallazgo R-1 de
 * docs/auditoria/14_...md (`GoalsConsole` solo muestra la meta configurada, sin venta
 * real). Componente hermano de `GoalsConsole`, mismo sistema visual (DataTable) para no
 * fragmentar el look del panel gerencial de Metas.
 *
 * Fase 1 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-1/R-3): una
 * sola columna de comisión -- la variable, ya con el gate de cumplimiento (Fase 2:
 * $0 bajo el 90%, bonos incluidos) y el techo de bonos aplicados. El esquema plano ya
 * no forma parte del sistema. Cada fila se expande para ver el desglose de 7
 * componentes de la fórmula. */
export function CommissionTracker() {
  const [period, setPeriod] = useState({ anio: new Date().getFullYear(), mes: new Date().getMonth() + 1 });
  const [hasInitializedPeriod, setHasInitializedPeriod] = useState(false);
  const [vendedorFiltro, setVendedorFiltro] = useState<string>('');

  const periods = usePeriods();
  const { data: vendedoresLista } = useVendedores();
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

  const tracking = useCommissionTracking(period.anio, period.mes, vendedorFiltro || null);
  const totalComision = tracking.data.reduce((sum, f) => sum + f.comision_devengada, 0);

  const columns: DataTableColumn<VendorCommissionRow>[] = [
    { key: 'vendedor', header: 'Vendedor', render: (f) => <span className="font-semibold text-primary">{f.vendedor}</span> },
    { key: 'venta_real', header: 'Venta Neta', render: (f) => <span className="text-slate-300">{fmtMoney(f.venta_real)}</span> },
    { key: 'monto_meta', header: 'Meta', render: (f) => <span className="text-slate-400">{fmtMoney(f.monto_meta)}</span> },
    { key: 'pct_cumplimiento', header: '% cumplimiento', render: (f) => <span className="text-slate-300">{pct(f.pct_cumplimiento)}</span> },
    {
      key: 'nivel',
      header: 'Tramo',
      render: (f) => <Badge variant={badgeVariantParaNivel(f.nivel)}>{f.nivel}</Badge>,
    },
    { key: 'tasa', header: 'Tasa efectiva', render: (f) => <span className="text-slate-400">{f.tasa_aplicada_pct.toFixed(2)}%</span> },
    {
      key: 'comision',
      header: 'Comisión',
      numeric: true,
      render: (f) => <span className="font-semibold text-primary">{fmtMoney(f.comision_devengada)}</span>,
    },
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Wallet className="w-8 h-8 text-primary" aria-hidden="true" />
          <h2 className="text-2xl font-bold tracking-tight">Comisiones devengadas</h2>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-slate-400" htmlFor="commission-tracker-vendedor">Vendedor</label>
            <Select
              id="commission-tracker-vendedor"
              value={vendedorFiltro}
              onChange={(e) => setVendedorFiltro(e.target.value)}
              className="min-w-[180px]"
            >
              <option value="">Todos los vendedores</option>
              {vendedoresLista?.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </Select>
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
      </div>

      <div className="bg-slate-800/50 rounded-lg p-5 border border-slate-700/50">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-200">Cumplimiento real y comisión por vendedor</h3>
          <div className="flex items-center gap-4 text-sm text-slate-400">
            <div className="flex items-center gap-1.5">
              <Gift size={14} className="text-primary" aria-hidden="true" />
              Total del período: <span className="font-mono text-primary font-semibold">{fmtMoney(totalComision)}</span>
            </div>
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
          maxHeight="max-h-none"
          renderExpanded={(r) => <DesgloseComisionVendedor row={r} />}
        />
      </div>
    </div>
  );
}
