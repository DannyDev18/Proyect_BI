import { useState } from 'react';
import { CalendarClock, DollarSign, FlaskConical, Percent, Play, Users } from 'lucide-react';

import { useCommissionSimulation } from '../../hooks/commissionConfig';
import type { ProyeccionVendedor } from '../../types/commissionConfig';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { KpiCard } from '../ui/KpiCard';
import { fmtMoney, pct } from '../../utils/format';

const OPCIONES_MESES = [3, 6] as const;

/** Proyección de Comisiones Variables (docs/manual_metas_y_comisiones.md §1.3.3): toma
 * los últimos 3 o 6 meses YA CERRADOS de cada vendedor como base histórica y proyecta
 * cuánto pagaría el esquema variable configurado (matriz de categorías, factores de
 * crédito, tipo de vendedor -- todos vigentes HOY) el próximo mes calendario. No
 * compara contra el esquema plano -- para esa comparación retroactiva existe la alerta
 * de divergencia del piloto en sombra, no este panel. */
export function CommissionSimulationPanel() {
  const [meses, setMeses] = useState<3 | 6>(3);
  const simulation = useCommissionSimulation();

  const handleSimular = () => simulation.simulate(meses);

  const columns: DataTableColumn<ProyeccionVendedor>[] = [
    { key: 'vendedor_origen', header: 'Código vendedor', render: (r) => <span className="font-mono text-slate-200">{r.vendedor_origen}</span> },
    { key: 'nombre_vendedor', header: 'Vendedor', render: (r) => <span className="text-slate-300">{r.nombre_vendedor ?? '—'}</span> },
    { key: 'periodo_proyectado', header: 'Período proyectado', render: (r) => <span className="text-slate-400">{r.periodo_proyectado}</span> },
    { key: 'venta_neta_promedio', header: 'Venta neta promedio', headerTitle: `Promedio mensual de los últimos ${meses} meses cerrados.`, numeric: true, render: (r) => <span className="text-slate-400">{fmtMoney(r.venta_neta_promedio)}</span> },
    { key: 'margen_bruto_promedio', header: 'Margen bruto promedio', headerTitle: `Promedio mensual de los últimos ${meses} meses cerrados. Excluye líneas de clases marcadas como grupo X en la matriz (ej. chatarra) -- no aportan a la comisión y su costo suele estar mal registrado.`, numeric: true, render: (r) => <span className="text-slate-400">{fmtMoney(r.margen_bruto_promedio)}</span> },
    { key: 'comision_variable_proyectada', header: 'Comisión variable proyectada', numeric: true, render: (r) => <span className="text-warning font-semibold">{fmtMoney(r.comision_variable_proyectada)}</span> },
    { key: 'tasa_efectiva_pct', header: '% comisión / margen', headerTitle: 'Comisión proyectada como % del margen bruto promedio -- la tasa efectiva real, no la tasa nominal de la matriz.', numeric: true, render: (r) => <span className="font-mono text-slate-300">{r.tasa_efectiva_pct.toFixed(2)}%</span> },
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
        <div className="flex items-center gap-3">
          <FlaskConical className="w-8 h-8 text-warning" aria-hidden="true" />
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Proyección de comisión variable</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Con las ventas recientes de cada vendedor y la configuración de la matriz vigente, ¿cuánto pagaría el
              esquema variable el próximo mes?
            </p>
          </div>
        </div>
        <div className="flex items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-slate-400" htmlFor="simulation-meses">Meses de historial</label>
            <Select id="simulation-meses" value={meses} onChange={(e) => setMeses(parseInt(e.target.value) as 3 | 6)}>
              {OPCIONES_MESES.map((m) => <option key={m} value={m}>{m} meses</option>)}
            </Select>
          </div>
          <Button variant="primary" onClick={handleSimular} loading={simulation.loading} icon={<Play className="w-4 h-4" aria-hidden="true" />}>
            Proyectar
          </Button>
        </div>
      </div>

      {simulation.error && <div className="p-4 mb-4 text-danger text-sm bg-danger/30 rounded-lg border border-danger/50">{simulation.error}</div>}

      {simulation.data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
            <KpiCard title="Comisión variable proyectada" value={fmtMoney(simulation.data.comision_variable_total_proyectada)} icon={DollarSign} trend="neutral" />
            <KpiCard title="Margen bruto promedio mensual" value={fmtMoney(simulation.data.margen_bruto_total_promedio)} icon={DollarSign} trend="neutral" />
            <KpiCard title="% comisión / margen" value={pct(simulation.data.tasa_efectiva_pct_global)} icon={Percent} trend={simulation.data.tasa_efectiva_pct_global <= 20 ? 'up' : 'down'} />
            <KpiCard title="Vendedores proyectados" value={String(simulation.data.vendedores_proyectados)} icon={Users} trend="neutral" />
          </div>
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <CalendarClock className="w-3.5 h-3.5" aria-hidden="true" />
            Proyección para <span className="text-slate-300 font-medium">{simulation.data.periodo_proyectado}</span>, con base
            en los últimos {simulation.data.meses_historico} meses cerrados de cada vendedor.
          </p>
          <p className="text-xs text-slate-600 mb-4 italic">
            Usa la matriz de categorías, los factores de crédito y el tipo de vendedor vigentes HOY -- no la
            configuración histórica de cada mes -- porque el objetivo es responder "si mantengo la config actual,
            ¿cuánto pagaría con el patrón de venta reciente de cada vendedor?". Asume cumplimiento neutro de la meta
            (tramo Meta, sin bono ni penalización) porque la meta del período proyectado todavía no existe; no
            incluye bonos ni devoluciones estimadas, que son eventos puntuales del mes ya cerrado, no un patrón
            proyectable.
          </p>

          <DataTable
            columns={columns}
            data={simulation.data.detalle}
            rowKey={(r) => r.vendedor_origen}
            emptyTitle="Sin vendedores con ventas en la ventana elegida"
          />
        </>
      )}

      {!simulation.data && !simulation.loading && (
        <p className="text-slate-500 text-sm text-center py-10">
          Elige la ventana de historial y presiona "Proyectar" para estimar la comisión variable del próximo mes con
          datos reales del EDW.
        </p>
      )}
    </div>
  );
}
