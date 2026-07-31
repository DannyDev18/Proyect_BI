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
type Modo = 'proyeccion' | 'mes_especifico';

const hoy = new Date();
const MES_MAXIMO = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`;

/** Proyección de Comisiones Variables (docs/manual_metas_y_comisiones.md §1.3.3). Dos
 * modos:
 *   - "Proyección" (promedio 3/6 meses cerrados de cada vendedor -> próximo mes
 *     calendario, cumplimiento neutro, sin bonos/devoluciones -- no hay meta futura
 *     que comparar todavía).
 *   - "Mes específico" (nuevo): reconstruye lo que se hubiera pagado REALMENTE un mes
 *     ya cerrado con la configuración vigente HOY (matriz/crédito/tipo de vendedor),
 *     usando la meta, los bonos y las devoluciones reales de ese mes -- para responder
 *     "si esta configuración hubiera estado vigente, ¿cuánto se hubiera pagado en
 *     [mes X]?". Ninguno de los dos modos compara contra el esquema plano -- para esa
 *     comparación retroactiva existe la alerta de divergencia del piloto en sombra. */
export function CommissionSimulationPanel() {
  const [modo, setModo] = useState<Modo>('proyeccion');
  const [meses, setMeses] = useState<3 | 6>(3);
  const [mesEspecifico, setMesEspecifico] = useState(MES_MAXIMO);
  const simulation = useCommissionSimulation();

  const handleSimular = () => {
    if (modo === 'mes_especifico') {
      const [anioStr, mesStr] = mesEspecifico.split('-');
      simulation.simulate({ anio: parseInt(anioStr, 10), mes: parseInt(mesStr, 10) });
    } else {
      simulation.simulate({ mesesHistorico: meses });
    }
  };

  // La respuesta no distingue el modo explícitamente -- `meses_historico === 1` es la
  // huella de una reconstrucción de mes específico (la proyección solo admite 3 o 6).
  const esMesEspecifico = simulation.data?.meses_historico === 1;

  const columns: DataTableColumn<ProyeccionVendedor>[] = [
    { key: 'vendedor_origen', header: 'Código vendedor', render: (r) => <span className="font-mono text-slate-200">{r.vendedor_origen}</span> },
    { key: 'nombre_vendedor', header: 'Vendedor', render: (r) => <span className="text-slate-300">{r.nombre_vendedor ?? '—'}</span> },
    { key: 'periodo_proyectado', header: esMesEspecifico ? 'Mes reconstruido' : 'Período proyectado', render: (r) => <span className="text-slate-400">{r.periodo_proyectado}</span> },
    { key: 'venta_neta_promedio', header: esMesEspecifico ? 'Venta neta del mes' : 'Venta neta promedio', headerTitle: esMesEspecifico ? 'Venta neta real de ese mes.' : `Promedio mensual de los últimos ${meses} meses cerrados.`, numeric: true, render: (r) => <span className="text-slate-400">{fmtMoney(r.venta_neta_promedio)}</span> },
    { key: 'margen_bruto_promedio', header: esMesEspecifico ? 'Margen bruto del mes' : 'Margen bruto promedio', headerTitle: `${esMesEspecifico ? 'Margen bruto real de ese mes.' : `Promedio mensual de los últimos ${meses} meses cerrados.`} Excluye líneas de clases marcadas como grupo X en la matriz (ej. chatarra) -- no aportan a la comisión y su costo suele estar mal registrado.`, numeric: true, render: (r) => <span className="text-slate-400">{fmtMoney(r.margen_bruto_promedio)}</span> },
    { key: 'comision_variable_proyectada', header: esMesEspecifico ? 'Comisión variable (reconstruida)' : 'Comisión variable proyectada', numeric: true, render: (r) => <span className="text-warning font-semibold">{fmtMoney(r.comision_variable_proyectada)}</span> },
    { key: 'tasa_efectiva_pct', header: '% comisión / margen', headerTitle: 'Comisión como % del margen bruto -- la tasa efectiva real, no la tasa nominal de la matriz.', numeric: true, render: (r) => <span className="font-mono text-slate-300">{r.tasa_efectiva_pct.toFixed(2)}%</span> },
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-4">
        <FlaskConical className="w-8 h-8 text-warning" aria-hidden="true" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Simulación de comisión variable</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Proyecta el próximo mes con el patrón de venta reciente, o reconstruye cuánto se hubiera pagado en un mes
            específico ya cerrado con la configuración actual.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1 bg-slate-800/70 border border-slate-700/50 rounded-full p-0.5 w-fit mb-5">
        <button
          type="button"
          onClick={() => setModo('proyeccion')}
          className={`px-4 py-1.5 text-xs font-medium rounded-full transition-colors focus-ring ${modo === 'proyeccion' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-slate-200'}`}
        >
          Proyección (próximo mes)
        </button>
        <button
          type="button"
          onClick={() => setModo('mes_especifico')}
          className={`px-4 py-1.5 text-xs font-medium rounded-full transition-colors focus-ring ${modo === 'mes_especifico' ? 'bg-primary/20 text-primary' : 'text-slate-400 hover:text-slate-200'}`}
        >
          Mes específico
        </button>
      </div>

      <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
        {modo === 'proyeccion' ? (
          <p className="text-xs text-slate-500 max-w-md">
            Con las ventas recientes de cada vendedor y la configuración vigente, ¿cuánto pagaría el esquema variable
            el próximo mes calendario?
          </p>
        ) : (
          <p className="text-xs text-slate-500 max-w-md">
            Con la configuración de comisión variable vigente HOY, ¿cuánto se hubiera pagado realmente en el mes que
            elijas? Usa la meta, los bonos y las devoluciones reales de ese período.
          </p>
        )}
        <div className="flex items-end gap-3">
          {modo === 'proyeccion' ? (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-slate-400" htmlFor="simulation-meses">Meses de historial</label>
              <Select id="simulation-meses" value={meses} onChange={(e) => setMeses(parseInt(e.target.value) as 3 | 6)}>
                {OPCIONES_MESES.map((m) => <option key={m} value={m}>{m} meses</option>)}
              </Select>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-slate-400" htmlFor="simulation-mes-especifico">Mes a reconstruir</label>
              <input
                id="simulation-mes-especifico"
                type="month"
                value={mesEspecifico}
                max={MES_MAXIMO}
                onChange={(e) => setMesEspecifico(e.target.value)}
                className="input-field"
              />
            </div>
          )}
          <Button variant="primary" onClick={handleSimular} loading={simulation.loading} icon={<Play className="w-4 h-4" aria-hidden="true" />}>
            {modo === 'proyeccion' ? 'Proyectar' : 'Reconstruir'}
          </Button>
        </div>
      </div>

      {simulation.error && <div className="p-4 mb-4 text-danger text-sm bg-danger/30 rounded-lg border border-danger/50">{simulation.error}</div>}

      {simulation.data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
            <KpiCard title={esMesEspecifico ? 'Comisión variable pagada' : 'Comisión variable proyectada'} value={fmtMoney(simulation.data.comision_variable_total_proyectada)} icon={DollarSign} trend="neutral" />
            <KpiCard title={esMesEspecifico ? 'Margen bruto del mes' : 'Margen bruto promedio mensual'} value={fmtMoney(simulation.data.margen_bruto_total_promedio)} icon={DollarSign} trend="neutral" />
            <KpiCard title="% comisión / margen" value={pct(simulation.data.tasa_efectiva_pct_global)} icon={Percent} trend={simulation.data.tasa_efectiva_pct_global <= 20 ? 'up' : 'down'} />
            <KpiCard title={esMesEspecifico ? 'Vendedores con venta ese mes' : 'Vendedores proyectados'} value={String(simulation.data.vendedores_proyectados)} icon={Users} trend="neutral" />
          </div>
          <p className="text-xs text-slate-500 mb-1 flex items-center gap-1.5">
            <CalendarClock className="w-3.5 h-3.5" aria-hidden="true" />
            {esMesEspecifico ? (
              <>Reconstrucción real de <span className="text-slate-300 font-medium">{simulation.data.periodo_proyectado}</span>.</>
            ) : (
              <>Proyección para <span className="text-slate-300 font-medium">{simulation.data.periodo_proyectado}</span>, con base
              en los últimos {simulation.data.meses_historico} meses cerrados de cada vendedor.</>
            )}
          </p>
          <p className="text-xs text-slate-600 mb-4 italic">
            {esMesEspecifico ? (
              <>Usa la matriz de categorías, los factores de crédito y el tipo de vendedor vigentes HOY -- no la
              configuración que estaba vigente en ese mes histórico -- para responder "si esta configuración hubiera
              estado activa, ¿cuánto se hubiera pagado?". Sí incluye la meta real de cada vendedor en ese período (el
              tramo de cumplimiento real, no neutro), y los bonos y devoluciones reales de ese mes -- a diferencia de
              la proyección al próximo mes, aquí ya existen datos reales de los tres.</>
            ) : (
              <>Usa la matriz de categorías, los factores de crédito y el tipo de vendedor vigentes HOY -- no la
              configuración histórica de cada mes -- porque el objetivo es responder "si mantengo la config actual,
              ¿cuánto pagaría con el patrón de venta reciente de cada vendedor?". Asume cumplimiento neutro de la meta
              (tramo Meta, sin bono ni penalización) porque la meta del período proyectado todavía no existe; no
              incluye bonos ni devoluciones estimadas, que son eventos puntuales del mes ya cerrado, no un patrón
              proyectable.</>
            )}
          </p>

          <DataTable
            columns={columns}
            data={simulation.data.detalle}
            rowKey={(r) => r.vendedor_origen}
            emptyTitle="Sin vendedores con ventas en el período elegido"
          />
        </>
      )}

      {!simulation.data && !simulation.loading && (
        <p className="text-slate-500 text-sm text-center py-10">
          {modo === 'proyeccion'
            ? 'Elige la ventana de historial y presiona "Proyectar" para estimar la comisión variable del próximo mes con datos reales del EDW.'
            : 'Elige un mes ya cerrado y presiona "Reconstruir" para ver cuánto se hubiera pagado ese mes con la configuración actual.'}
        </p>
      )}
    </div>
  );
}
