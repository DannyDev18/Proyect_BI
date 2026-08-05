import { useState } from 'react';
import { CalendarClock, DollarSign, FlaskConical, Percent, Play, Users } from 'lucide-react';

import { useCommissionSimulation } from '../../hooks/commissionConfig';
import type { ComponenteComision, ProyeccionVendedor } from '../../types/commissionConfig';
import { Button } from '../ui/Button';
import { Select } from '../ui/Select';
import { Badge } from '../ui/Badge';
import { DataTable, type DataTableColumn } from '../ui/DataTable';
import { KpiCard } from '../ui/KpiCard';
import { fmtMoney, pct } from '../../utils/format';

/** Fila expandible con la tubería paso a paso (auditoría 45, docs/features/plan_
 * comisiones_sobrecumplimiento_umbral_y_desglose.md §3.3): "cómo se construye la
 * comisión, cuánto gané de cada cosa" -- venta, cobranza, contado de agencia, factor de
 * tipo, multiplicador de cumplimiento, devoluciones, bonos, hasta el total final. Solo
 * muestra los componentes que la fórmula vigente tiene activos (nunca un $0.00 que
 * sugiera falsamente que un componente inactivo aportó algo). */
function DesgloseComision({ row }: { row: ProyeccionVendedor }) {
  if (row.componentes.length === 0) {
    return <p className="p-4 text-xs text-slate-500">Sin desglose disponible para este vendedor.</p>;
  }
  return (
    <div className="p-4">
      <p className="text-xs font-semibold text-slate-400 mb-2">Cómo se construyó esta comisión</p>
      <ol className="space-y-1.5">
        {row.componentes.map((c: ComponenteComision) => (
          <li key={c.orden} className="flex items-center justify-between gap-4 text-xs">
            <span className="text-slate-400">
              <span className="font-mono text-slate-600 mr-2">{c.orden}.</span>
              {c.operador === 'sumar' && <span className="text-success mr-1">+</span>}
              {c.operador === 'restar' && <span className="text-danger mr-1">−</span>}
              {c.operador === 'multiplicar' && <span className="text-info mr-1">×</span>}
              {c.etiqueta}
            </span>
            <span className="flex items-center gap-3 font-mono">
              <span className="text-slate-300">
                {c.es_factor ? `${c.monto.toFixed(4)}x` : fmtMoney(c.monto)}
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
        <span className="font-mono font-semibold text-warning">{fmtMoney(row.comision_variable_proyectada)}</span>
      </div>
      {!row.comisiona && (
        <p className="mt-2 text-xs text-danger">
          Este vendedor no alcanzó el umbral mínimo de cumplimiento ({row.nivel ?? 'tramo sin comisión'}) -- el
          multiplicador de cumplimiento es 0, aunque los bonos (si los hay) se sigan sumando.
        </p>
      )}
    </div>
  );
}

const OPCIONES_MESES = [3, 6] as const;
type Modo = 'proyeccion' | 'mes_especifico';

const hoy = new Date();
const MES_MAXIMO = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`;

/** Proyección de Comisiones Variables (docs/manual_metas_y_comisiones.md §1.3.3). Dos
 * modos:
 *   - "Proyección" (promedio 3/6 meses cerrados de cada vendedor -> próximo mes
 *     calendario, cumplimiento neutro, sin bonos/devoluciones -- no hay meta futura
 *     que comparar todavía).
 *   - "Mes específico": reconstruye lo que se hubiera pagado REALMENTE un mes ya
 *     cerrado, usando la meta, los bonos y las devoluciones reales de ese mes. Dos
 *     variantes (Fase 4, docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md,
 *     R-4): con la configuración vigente AL CIERRE de ese período ("reconstrucción
 *     fiel", coincide con lo que "Comisiones devengadas" liquida) o con la
 *     configuración vigente HOY ("qué pasaría si"). Ninguno de los dos modos compara
 *     contra el esquema plano -- ya retirado del sistema (Fase 1). */
export function CommissionSimulationPanel() {
  const [modo, setModo] = useState<Modo>('proyeccion');
  const [meses, setMeses] = useState<3 | 6>(3);
  const [mesEspecifico, setMesEspecifico] = useState(MES_MAXIMO);
  // Fase 4 (docs/features/plan_motor_metas_v3_y_comisiones_unificadas.md, R-4):
  // "reconstrucción fiel" (config vigente AL CIERRE, coincide con lo real) vs.
  // "config de hoy" (qué se hubiera pagado si la config actual ya hubiera estado
  // vigente). Antes solo existía el segundo modo, sin decirlo -- el usuario leía la
  // divergencia como "el simulador no concuerda con las comisiones reales".
  const [reconstruccionFiel, setReconstruccionFiel] = useState(true);
  const simulation = useCommissionSimulation();

  const handleSimular = () => {
    if (modo === 'mes_especifico') {
      const [anioStr, mesStr] = mesEspecifico.split('-');
      simulation.simulate({
        anio: parseInt(anioStr, 10), mes: parseInt(mesStr, 10),
        usarConfiguracionDeHoy: !reconstruccionFiel,
      });
    } else {
      simulation.simulate({ mesesHistorico: meses });
    }
  };

  // El backend etiqueta explícitamente el modo desde la Fase 4 -- ya no hace falta
  // inferirlo de `meses_historico === 1`.
  const esMesEspecifico = simulation.data?.modo !== 'proyeccion';
  const esReconstruccionFiel = simulation.data?.modo === 'reconstruccion_fiel';

  const columns: DataTableColumn<ProyeccionVendedor>[] = [
    { key: 'vendedor_origen', header: 'Código vendedor', render: (r) => <span className="font-mono text-slate-200">{r.vendedor_origen}</span> },
    { key: 'nombre_vendedor', header: 'Vendedor', render: (r) => <span className="text-slate-300">{r.nombre_vendedor ?? '—'}</span> },
    { key: 'periodo_proyectado', header: esMesEspecifico ? 'Mes reconstruido' : 'Período proyectado', render: (r) => <span className="text-slate-400">{r.periodo_proyectado}</span> },
    { key: 'venta_neta_promedio', header: esMesEspecifico ? 'Venta neta del mes' : 'Venta neta promedio', headerTitle: esMesEspecifico ? 'Venta neta real de ese mes.' : `Promedio mensual de los últimos ${meses} meses cerrados.`, numeric: true, render: (r) => <span className="text-slate-400">{fmtMoney(r.venta_neta_promedio)}</span> },
    { key: 'margen_bruto_promedio', header: esMesEspecifico ? 'Margen bruto del mes' : 'Margen bruto promedio', headerTitle: `${esMesEspecifico ? 'Margen bruto real de ese mes.' : `Promedio mensual de los últimos ${meses} meses cerrados.`} Excluye líneas de clases marcadas como grupo X en la matriz (ej. chatarra) -- no aportan a la comisión y su costo suele estar mal registrado.`, numeric: true, render: (r) => <span className="text-slate-400">{fmtMoney(r.margen_bruto_promedio)}</span> },
    { key: 'comision_variable_proyectada', header: esMesEspecifico ? 'Comisión variable (reconstruida)' : 'Comisión variable proyectada', numeric: true, render: (r) => <span className="text-warning font-semibold">{fmtMoney(r.comision_variable_proyectada)}</span> },
    {
      key: 'pct_cumplimiento', header: '% cumplimiento', numeric: true,
      headerTitle: esMesEspecifico ? 'Venta real / meta del período.' : 'Cumplimiento neutro simulado (100%) -- la meta del período proyectado todavía no existe.',
      render: (r) => <span className="font-mono text-slate-300">{r.pct_cumplimiento != null ? `${r.pct_cumplimiento.toFixed(1)}%` : '—'}</span>,
    },
    {
      key: 'nivel', header: 'Tramo', headerTitle: 'Tramo de cumplimiento aplicado (configurable en el panel de configuración).',
      render: (r) => r.nivel ? <Badge variant={r.comisiona ? 'info' : 'danger'}>{r.nivel}</Badge> : <span className="text-slate-600">—</span>,
    },
    {
      key: 'tasa_efectiva_pct', header: '% comisión / margen de venta', numeric: true,
      headerTitle: 'Comisión total (incluye cobranza y contado de agencia, que no tienen margen de línea propio) como % del margen bruto de las LÍNEAS de venta -- no es comparable 1:1 entre un vendedor de líneas y uno con mucha cobranza/contado. Ver el desglose de esta fila para la composición real.',
      render: (r) => {
        const totalNoLineas = r.componentes
          .filter((c) => c.componente === 'base_cobranza' || c.componente === 'contado_agencia')
          .reduce((acc, c) => acc + c.monto, 0);
        const base = r.componentes.find((c) => c.componente === 'base_lineas_venta')?.monto ?? 0;
        const pesoNoLineas = (base + totalNoLineas) > 0 ? (totalNoLineas / (base + totalNoLineas)) * 100 : 0;
        return (
          <span className="inline-flex items-center gap-1.5">
            <span className="font-mono text-slate-300">{r.tasa_efectiva_pct.toFixed(2)}%</span>
            {pesoNoLineas > 50 && (
              <span title="Más del 50% de la base es cobranza/contado de agencia, no líneas de venta -- esta tasa no es comparable con la de un vendedor puramente de líneas.">
                <Percent className="w-3 h-3 text-warning" aria-hidden="true" />
              </span>
            )}
          </span>
        );
      },
    },
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
            ¿Cuánto se pagó (o se hubiera pagado) realmente en el mes que elijas? Usa la meta, los bonos y las
            devoluciones reales de ese período -- elige si quieres la configuración vigente en ese momento
            (coincide con lo liquidado) o la vigente hoy (un "qué pasaría si").
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
            <>
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
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-slate-400" htmlFor="simulation-config-modo">Configuración a usar</label>
                <Select
                  id="simulation-config-modo"
                  value={reconstruccionFiel ? 'fiel' : 'hoy'}
                  onChange={(e) => setReconstruccionFiel(e.target.value === 'fiel')}
                >
                  <option value="fiel">Vigente al cierre del período (reconstrucción fiel)</option>
                  <option value="hoy">Vigente hoy ("qué pasaría si")</option>
                </Select>
              </div>
            </>
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
              <>{esReconstruccionFiel ? 'Reconstrucción fiel' : 'Reconstrucción con la configuración de hoy'} de{' '}
              <span className="text-slate-300 font-medium">{simulation.data.periodo_proyectado}</span>.</>
            ) : (
              <>Proyección para <span className="text-slate-300 font-medium">{simulation.data.periodo_proyectado}</span>, con base
              en los últimos {simulation.data.meses_historico} meses cerrados de cada vendedor.</>
            )}
          </p>
          <p className="text-xs text-slate-600 mb-4 italic">
            {esMesEspecifico ? (
              esReconstruccionFiel ? (
                <>Usa la matriz de categorías y el tipo de vendedor vigentes AL CIERRE de ese período -- el mismo
                cálculo, con la misma configuración, que produce "Comisiones devengadas". Debe coincidir centavo a
                centavo con lo realmente liquidado (o lo que se liquidaría si el período estuviera cerrado).</>
              ) : (
                <>Usa la matriz de categorías y el tipo de vendedor vigentes HOY -- no la configuración que estaba
                vigente en ese mes histórico -- para responder "si esta configuración hubiera estado activa, ¿cuánto
                se hubiera pagado?". Puede diferir de "Comisiones devengadas" a propósito si la configuración cambió
                desde entonces. Sí incluye la meta, los bonos y las devoluciones reales de ese período.</>
              )
            ) : (
              <>Usa la matriz de categorías y el tipo de vendedor vigentes HOY -- no la configuración histórica de
              cada mes -- porque el objetivo es responder "si mantengo la config actual, ¿cuánto pagaría con el
              patrón de venta reciente de cada vendedor?". Asume cumplimiento neutro de la meta (tramo Meta, sin bono
              ni penalización) porque la meta del período proyectado todavía no existe; <span className="text-warning">no
              incluye bonos ni devoluciones estimadas</span> -- son eventos puntuales del mes ya cerrado, no un
              patrón proyectable, así que esta cifra subestima a propósito lo que un mes real con bonos pagaría.</>
            )}
          </p>

          <DataTable
            columns={columns}
            data={simulation.data.detalle}
            rowKey={(r) => r.vendedor_origen}
            emptyTitle="Sin vendedores con ventas en el período elegido"
            renderExpanded={(r) => <DesgloseComision row={r} />}
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
