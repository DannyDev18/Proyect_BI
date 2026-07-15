import { useState } from 'react';
import { DollarSign, FlaskConical, Percent, Play, TrendingDown, TrendingUp } from 'lucide-react';

import { useCommissionSimulation } from '../../hooks/commissionConfig';
import type { SimulacionVendedorMes } from '../../types/commissionConfig';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { KpiCard } from '../ui/KpiCard';
import { fmtMoney, pct } from '../../utils/format';

const OPCIONES_MESES = [3, 6, 12, 24];

/** Simulación retroactiva plano vs. variable (docs/features/plan_integracion_
 * comisiones_variables.md §3.4, Fase 2: "el argumento decisivo" para gerencia). Se
 * dispara bajo demanda -- consulta pesada sobre el EDW a grano de línea de venta. */
export function CommissionSimulationPanel() {
  const [meses, setMeses] = useState(12);
  const simulation = useCommissionSimulation();

  const handleSimular = () => simulation.simulate(meses);

  const columns: DataTableColumn<SimulacionVendedorMes>[] = [
    { key: 'vendedor', header: 'Vendedor', render: (r) => <span className="font-mono text-slate-200">{r.vendedor_origen}</span> },
    { key: 'periodo', header: 'Período', render: (r) => <span className="text-slate-400">{r.mes}/{r.anio}</span> },
    { key: 'venta_neta', header: 'Venta Neta', numeric: true, render: (r) => <span className="text-slate-300">{fmtMoney(r.venta_neta)}</span> },
    { key: 'comision_plana', header: 'Comisión plana', numeric: true, render: (r) => <span className="text-teal-300">{fmtMoney(r.comision_plana)}</span> },
    { key: 'comision_variable', header: 'Comisión variable', numeric: true, render: (r) => <span className="text-amber-300">{fmtMoney(r.comision_variable)}</span> },
    {
      key: 'diferencia', header: 'Diferencia', numeric: true,
      render: (r) => (
        <span className={`inline-flex items-center gap-1 font-semibold ${r.diferencia >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {r.diferencia >= 0 ? <TrendingUp size={13} aria-hidden="true" /> : <TrendingDown size={13} aria-hidden="true" />}
          {fmtMoney(r.diferencia)}{r.diferencia_pct != null && ` (${r.diferencia_pct >= 0 ? '+' : ''}${r.diferencia_pct.toFixed(1)}%)`}
        </span>
      ),
    },
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <div className="flex items-center gap-3">
          <FlaskConical className="w-8 h-8 text-amber-400" aria-hidden="true" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Simulación: esquema plano vs. variable</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              "Qué habría pasado" -- elimina el miedo al costo desconocido antes de activar el piloto.
            </p>
          </div>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-slate-400" htmlFor="simulation-meses">Meses a simular</label>
            <Select id="simulation-meses" value={meses} onChange={(e) => setMeses(parseInt(e.target.value))}>
              {OPCIONES_MESES.map((m) => <option key={m} value={m}>{m} meses</option>)}
            </Select>
          </div>
          <Button variant="primary" onClick={handleSimular} loading={simulation.loading} icon={<Play className="w-4 h-4" aria-hidden="true" />}>
            Simular
          </Button>
        </div>
      </div>

      {simulation.error && <div className="p-4 mb-4 text-red-400 text-sm bg-red-950/30 rounded-lg border border-red-900/50">{simulation.error}</div>}

      {simulation.data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
            <KpiCard title="Costo total (plana)" value={fmtMoney(simulation.data.costo_total_plana)} icon={DollarSign} trend="neutral" />
            <KpiCard title="Costo total (variable)" value={fmtMoney(simulation.data.costo_total_variable)} icon={DollarSign} trend={simulation.data.costo_total_variable <= simulation.data.costo_total_plana ? 'up' : 'down'} />
            <KpiCard title="% comisión / margen (plana)" value={pct(simulation.data.pct_comision_sobre_margen_plana)} icon={Percent} trend="neutral" />
            <KpiCard title="% comisión / margen (variable)" value={pct(simulation.data.pct_comision_sobre_margen_variable)} icon={Percent} trend={simulation.data.pct_comision_sobre_margen_variable <= 20 ? 'up' : 'down'} />
          </div>
          <p className="text-xs text-slate-500 mb-1">
            {simulation.data.meses_simulados} meses · {simulation.data.vendedores_simulados} vendedores ·
            margen bruto total del período: {fmtMoney(simulation.data.margen_bruto_total)}
          </p>
          <p className="text-xs text-slate-600 mb-4 italic">
            Cada mes se calcula con la matriz de categorías y los factores de crédito vigentes al cierre de ese mes
            (no con la configuración actual), para que un cambio reciente no reescriba lo que el esquema nuevo
            habría pagado en meses ya simulados.
          </p>

          <DataTable
            columns={columns}
            data={simulation.data.detalle}
            rowKey={(r) => `${r.vendedor_origen}-${r.anio}-${r.mes}`}
            emptyTitle="Sin resultados"
          />
        </>
      )}

      {!simulation.data && !simulation.loading && (
        <p className="text-slate-500 text-sm text-center py-10">
          Elige el número de meses y presiona "Simular" para comparar el esquema plano contra el variable con datos reales del EDW.
        </p>
      )}
    </div>
  );
}
