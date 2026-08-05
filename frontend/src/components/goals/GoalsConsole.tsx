import { useState, useEffect, useMemo, useRef } from "react";
import { Loader2, Trophy, Info } from "lucide-react";

import { usePeriods, useGoalsTracking, useGenerateGoals, useReviewGoal, useMetaSugeridaGerencia } from "../../hooks/goals";
import { useVendedores } from "../../hooks/gerencia";
import type { GoalPeriodOption, GoalProposal } from "../../types/goals";
import { Select } from "../ui/Select";
import { Button } from "../ui/Button";
import { DataTable, type DataTableColumn } from "../ui/DataTable";
import { Badge } from "../ui/Badge";
import { Drawer } from "../ui/Drawer";
import { Tabs } from "../ui/Tabs";
import { useToast } from "../../store/toastStore";
import { fmtMoney, pct } from "../../utils/format";
import { MetaConfigPanel } from "./MetaConfigPanel";

const ESTADO_BADGE: Record<string, { variant: 'success' | 'danger' | 'warning'; label: string }> = {
  APROBADA: { variant: 'success', label: 'APROBADA' },
  RECHAZADA: { variant: 'danger', label: 'RECHAZADA' },
};

export function GoalsConsole() {
  const [pressure, setPressure] = useState<number>(10);
  const [period, setPeriod] = useState({ anio: new Date().getFullYear(), mes: new Date().getMonth() + 1 });
  const [hasInitializedPeriod, setHasInitializedPeriod] = useState(false);
  const [vendedorFiltro, setVendedorFiltro] = useState<string>('');
  const [detalleVendedor, setDetalleVendedor] = useState<GoalProposal | null>(null);
  const [tab, setTab] = useState<'propuestas' | 'formula'>('propuestas');
  const toast = useToast();
  const desglose = useMetaSugeridaGerencia(detalleVendedor?.vendedor_origen ?? null, period.anio, period.mes);
  const { data: vendedoresLista } = useVendedores();

  const periods = usePeriods();
  const months = useMemo<GoalPeriodOption[]>(() => periods.data.map((d) => {
    const date = new Date(d.anio, d.mes - 1, 1);
    const name = date.toLocaleString('es-ES', { month: 'long' });
    return {
      anio: d.anio,
      mes: d.mes,
      label: `${name.charAt(0).toUpperCase() + name.slice(1)} ${d.anio}`,
    };
  }), [periods.data]);

  useEffect(() => {
    if (!hasInitializedPeriod && months.length > 0) {
      // El horizonte de planificación ahora incluye meses históricos con metas ya
      // generadas -- elegir siempre el mes calendario vigente (o, si no está en la
      // lista, el más cercano hacia adelante) en vez de `months[0]` (el más antiguo),
      // para que la consola abra en el período que gerencia normalmente va a revisar.
      const hoy = new Date();
      const actual = months.find((m) => m.anio === hoy.getFullYear() && m.mes === hoy.getMonth() + 1);
      const siguienteFuturo = months.find((m) => m.anio > hoy.getFullYear() || (m.anio === hoy.getFullYear() && m.mes >= hoy.getMonth() + 1));
      const inicial = actual ?? siguienteFuturo ?? months[0];
      setPeriod({ anio: inicial.anio, mes: inicial.mes });
      setHasInitializedPeriod(true);
    }
  }, [months, hasInitializedPeriod]);

  const tracking = useGoalsTracking(period.anio, period.mes, vendedorFiltro || null);
  const [proposals, setProposals] = useState<GoalProposal[]>([]);
  useEffect(() => {
    setProposals(tracking.data);
  }, [tracking.data]);

  const generateMut = useGenerateGoals();
  const reviewMut = useReviewGoal();
  const loading = tracking.loading;

  // La fórmula de metas (motor v3) se aplica automáticamente sobre la propuesta que
  // luego se pasa a aprobar -- sin un botón manual "Generar Plan": al mover el factor de
  // presión comercial o cambiar de período, las propuestas PENDIENTES se recalculan
  // solas (debounce de 600ms mientras se arrastra el slider, para no golpear el EDW en
  // cada pixel de movimiento). `generate_proposals` es idempotente sobre filas en
  // estado PROPUESTA -- nunca toca una meta ya APROBADA/RECHAZADA.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!hasInitializedPeriod) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const factor = 1 + pressure / 100;
      generateMut.generate({ anio: period.anio, mes: period.mes, factor }).catch((err) => {
        console.error("Error generando metas:", err);
        toast('No se pudieron actualizar las propuestas de meta.', 'error');
      });
    }, 600);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period.anio, period.mes, pressure, hasInitializedPeriod]);

  const handleReview = async (
    id: number,
    estado: "APROBADA" | "RECHAZADA",
    monto: number,
  ) => {
    try {
      await reviewMut.review({ id, monto_meta: monto, estado });
      toast(estado === 'APROBADA' ? 'Meta aprobada.' : 'Meta rechazada.', 'success');
    } catch (err) {
      console.error("Error procesando aprobacion:", err);
      toast('No se pudo procesar la revisión de la meta.', 'error');
    }
  };

  const columns: DataTableColumn<GoalProposal>[] = [
    {
      key: 'vendedor', header: 'Vendedor',
      render: (p) => (
        <button
          className="font-semibold text-primary hover:text-primary hover:underline inline-flex items-center gap-1"
          onClick={() => setDetalleVendedor(p)}
          title="Ver cómo se calculó la meta sugerida"
        >
          {p.vendedor}
          <Info size={12} className="text-slate-500" aria-hidden="true" />
        </button>
      ),
    },
    {
      key: 'monto',
      header: 'Meta Propuesta ($)',
      render: (p) => {
        // H-10 (docs/auditoria/46_motor_metas_configurable.md): antes este campo
        // "previsualizaba" un cambio de presión recalculando en el frontend
        // `(monto / 1.1) * (1 + pressure/100)`, asumiendo que la meta ya mostrada
        // siempre traía un 10% incorporado -- falso para vendedores internos (×0.95) o
        // nuevos (mediana del equipo). El monto mostrado es siempre el que el backend
        // ya calculó con la fórmula real (motor v3) y la presión vigente -- se
        // recalcula solo, sin botón manual, al ajustar el slider de arriba.
        const formattedMonto = new Intl.NumberFormat('es-EC', {
          style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2,
        }).format(p.monto_meta);
        return (
          <input
            type="text"
            aria-label={`Meta propuesta para ${p.vendedor}`}
            value={formattedMonto}
            onChange={(e) => {
              const newProposals = [...proposals];
              const idx = newProposals.findIndex((x) => x.id === p.id);
              if (idx !== -1) {
                const cleaned = e.target.value.replace(/[^0-9.-]+/g, "");
                newProposals[idx].monto_meta = parseFloat(cleaned) || 0;
                setProposals(newProposals);
              }
            }}
            className="bg-slate-800 w-32 p-1.5 rounded border border-slate-700 focus-ring cursor-text"
          />
        );
      },
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (p) => {
        const badge = ESTADO_BADGE[p.estado] ?? { variant: 'warning' as const, label: p.estado };
        return <Badge variant={badge.variant}>{badge.label}</Badge>;
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      numeric: true,
      render: (p) => (
        <div className="flex justify-end gap-2">
          <Button
            variant="primary"
            size="sm"
            loading={reviewMut.pendingId === p.id}
            onClick={() => handleReview(p.id, "APROBADA", p.monto_meta)}
          >
            Aprobar
          </Button>
          <Button
            variant="danger"
            size="sm"
            loading={reviewMut.pendingId === p.id}
            onClick={() => handleReview(p.id, "RECHAZADA", p.monto_meta)}
          >
            Rechazar
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto mt-6">
      <div className="flex items-center gap-3 mb-6">
        <Trophy className="w-8 h-8 text-primary" aria-hidden="true" />
        <h2 className="text-2xl font-bold tracking-tight">
          Consola Inteligente de Metas & Comisiones
        </h2>
      </div>

      <Tabs
        className="mb-5"
        value={tab}
        onChange={(v) => setTab(v as typeof tab)}
        items={[
          { value: 'propuestas', label: 'Propuestas del período' },
          { value: 'formula', label: 'Fórmula de metas' },
        ]}
      />

      {tab === 'formula' ? (
        <MetaConfigPanel />
      ) : (
      <>
      {/* Panel de Configuración Automática con Cursors definidos */}
      <div className="p-5 bg-slate-800/50 rounded-lg mb-6 flex flex-wrap gap-6 items-center border border-slate-700/50">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400" htmlFor="goals-console-period">
            Año / Mes de Planificación
          </label>
          <Select
            id="goals-console-period"
            onChange={(e) => {
              const selectedValue = e.target.value;
              const selectedMonth = months.find(m => `${m.anio}-${m.mes}` === selectedValue);
              if (selectedMonth) {
                setPeriod({ anio: selectedMonth.anio, mes: selectedMonth.mes });
              }
            }}
            value={`${period.anio}-${period.mes}`}
            disabled={loading}
            className="min-w-[190px]"
          >
            {months.map((m, idx) => (
              <option key={idx} value={`${m.anio}-${m.mes}`}>{m.label}</option>
            ))}
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400" htmlFor="goals-console-vendedor">
            Vendedor
          </label>
          <Select
            id="goals-console-vendedor"
            value={vendedorFiltro}
            onChange={(e) => setVendedorFiltro(e.target.value)}
            disabled={loading}
            className="min-w-[180px]"
          >
            <option value="">Todos los vendedores</option>
            {vendedoresLista?.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </Select>
        </div>

        <div className="flex-1 min-w-[200px] flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400" htmlFor="goals-console-pressure">
            Factor de Presión Comercial (+{pressure}%)
          </label>
          <input
            id="goals-console-pressure"
            type="range"
            min="0"
            max="25"
            value={pressure}
            onChange={(e) => setPressure(parseInt(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-teal-400 focus-ring"
          />
        </div>

        <div className="text-xs text-slate-500 flex items-center gap-1.5 min-w-[170px]">
          {generateMut.loading ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" aria-hidden="true" />
              Actualizando propuestas...
            </>
          ) : (
            'Las propuestas se recalculan solas con la fórmula de metas al ajustar el período o la presión.'
          )}
        </div>
      </div>

      {/* Grilla Interactiva */}
      <div className="bg-slate-800/50 rounded-lg p-5 border border-slate-700/50">
        <h3 className="text-lg font-semibold mb-4 text-slate-200">
          Revisión de Flujo y Propuestas
        </h3>

        <DataTable
          columns={columns}
          data={[...proposals].sort((a, b) => a.vendedor.localeCompare(b.vendedor))}
          rowKey={(p) => p.id}
          loading={loading}
          error={tracking.error ?? undefined}
          onRetry={tracking.refetch}
          emptyTitle="No hay metas propuestas para este periodo"
          emptyDescription="Las propuestas se generan solas con la fórmula de metas vigente al elegir un período con vendedores elegibles."
          maxHeight="max-h-none"
        />
      </div>

      <Drawer
        open={!!detalleVendedor}
        onClose={() => setDetalleVendedor(null)}
        title={detalleVendedor ? `Cómo se calculó la meta de ${detalleVendedor.vendedor}` : ''}
      >
        {desglose.loading ? (
          <div className="skeleton h-40 rounded" />
        ) : desglose.error ? (
          <p className="text-sm text-danger">{desglose.error}</p>
        ) : desglose.data ? (
          <div className="space-y-4">
            <Badge variant={desglose.data.es_trazabilidad_persistida ? 'success' : 'warning'}>
              {desglose.data.es_trazabilidad_persistida
                ? 'Valores reales de la meta ya generada'
                : 'Recálculo en vivo (esta meta aún no se ha generado para este período)'}
            </Badge>
            <div className="card p-3">
              <p className="text-xs text-slate-500">
                Meta calculada para {desglose.data.mes_objetivo}/{desglose.data.anio_objetivo}
              </p>
              <p className="text-lg font-semibold text-slate-100">{fmtMoney(desglose.data.meta_sugerida_estadistica)}</p>
              <p className="text-xs text-slate-500 mt-1">{METODO_LABEL[desglose.data.metodo_estadistico] ?? desglose.data.metodo_estadistico}</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-3">
                <p className="text-xs text-slate-500">Meses de histórico</p>
                <p className="text-base font-semibold text-slate-200">{desglose.data.meses_historico_usados}</p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Atípicos excluidos (IQR)</p>
                <p className="text-base font-semibold text-slate-200">{desglose.data.valores_atipicos_excluidos}</p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Meses atípicos (IsolationForest)</p>
                <p className="text-base font-semibold text-slate-200">{desglose.data.meses_atipicos_ml_detectados}</p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Coef. de variación</p>
                <p className="text-base font-semibold text-slate-200">{pct(desglose.data.coeficiente_variacion * 100)}</p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Índice estacional aplicado</p>
                <p className="text-base font-semibold text-slate-200">
                  {desglose.data.indice_estacional_aplicado.toFixed(3)}× <span className="text-xs text-slate-500">({FUENTE_LABEL[desglose.data.fuente_indice_estacional]})</span>
                </p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Factor de tendencia aplicado</p>
                <p className="text-base font-semibold text-slate-200">{desglose.data.factor_tendencia_aplicado.toFixed(3)}×</p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Meta antes de estacionalidad/tendencia</p>
                <p className="text-base font-semibold text-slate-200">
                  {desglose.data.componente_estacional != null ? fmtMoney(desglose.data.componente_estacional) : '—'}
                </p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Meta tras aplicar tendencia</p>
                <p className="text-base font-semibold text-slate-200">{fmtMoney(desglose.data.componente_tendencia)}</p>
              </div>
            </div>
            <div className="card p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">Banda de alcanzabilidad</p>
                {desglose.data.banda_actuo && <Badge variant="warning">Actuó: recortó la meta</Badge>}
              </div>
              <p className="text-base font-semibold text-slate-200">
                Referencia (mediana reciente × estacionalidad): {fmtMoney(desglose.data.referencia_alcanzable)}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Meta antes de la banda: {fmtMoney(desglose.data.meta_pre_banda)} → Meta final: {fmtMoney(desglose.data.meta_sugerida_estadistica)}
              </p>
            </div>
          </div>
        ) : null}
      </Drawer>
      </>
      )}
    </div>
  );
}

const METODO_LABEL: Record<string, string> = {
  estacional_propio_v2: 'Estacionalidad propia del vendedor (≥2 años del mismo mes)',
  estacional_empresa_v2: 'Estacionalidad de la empresa (histórico propio insuficiente)',
  tendencia_robusta_v2: 'Tendencia reciente, sin estacionalidad (histórico corto)',
  equipo_prorrateado_v2: 'Mediana del equipo (histórico casi nulo)',
  sin_historico: 'Sin histórico suficiente',
  estadistico_iqr_v1: 'Motor estadístico (legado)',
  estadistico_iqr_ml_v1: 'Motor estadístico + señal ML (legado)',
};

const FUENTE_LABEL: Record<string, string> = {
  propio: 'propio del vendedor',
  empresa: 'de toda la empresa',
  neutro: 'sin señal estacional',
};
