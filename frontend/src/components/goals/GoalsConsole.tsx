import { useState, useEffect, useMemo } from "react";
import { TrendingUp, Trophy, Info } from "lucide-react";

import { usePeriods, useGoalsTracking, useGenerateGoals, useReviewGoal, useMetaSugeridaGerencia } from "../../hooks/goals";
import type { GoalPeriodOption, GoalProposal } from "../../types/goals";
import { Select } from "../ui/Select";
import { Button } from "../ui/Button";
import { DataTable, type DataTableColumn } from "../ui/DataTable";
import { AlertBadge } from "../ui/AlertBadge";
import { Drawer } from "../ui/Drawer";
import { useToast } from "../../store/toastStore";
import { fmtMoney, pct } from "../../utils/format";

const ESTADO_BADGE: Record<string, { variant: 'success' | 'critical' | 'warning'; label: string }> = {
  APROBADA: { variant: 'success', label: 'APROBADA' },
  RECHAZADA: { variant: 'critical', label: 'RECHAZADA' },
};

export function GoalsConsole() {
  const [pressure, setPressure] = useState<number>(10);
  const [period, setPeriod] = useState({ anio: new Date().getFullYear(), mes: new Date().getMonth() + 1 });
  const [hasInitializedPeriod, setHasInitializedPeriod] = useState(false);
  const [detalleVendedor, setDetalleVendedor] = useState<GoalProposal | null>(null);
  const toast = useToast();
  const desglose = useMetaSugeridaGerencia(detalleVendedor?.vendedor_origen ?? null);

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
      setPeriod({ anio: months[0].anio, mes: months[0].mes });
      setHasInitializedPeriod(true);
    }
  }, [months, hasInitializedPeriod]);

  const tracking = useGoalsTracking(period.anio, period.mes);
  const [proposals, setProposals] = useState<GoalProposal[]>([]);
  useEffect(() => {
    setProposals(tracking.data);
  }, [tracking.data]);

  const generateMut = useGenerateGoals();
  const reviewMut = useReviewGoal();
  const loading = tracking.loading || generateMut.loading;

  const handleGenerate = async () => {
    const factor = 1 + pressure / 100;
    try {
      await generateMut.generate({ anio: period.anio, mes: period.mes, factor });
      toast('Plan de metas generado correctamente.', 'success');
    } catch (err) {
      console.error("Error generando metas:", err);
      toast('No se pudo generar el plan de metas.', 'error');
    }
  };

  const handleReview = async (
    id: number,
    estado: "APROBADA" | "RECHAZADA",
    monto: number,
    comision: number,
  ) => {
    try {
      await reviewMut.review({ id, monto_meta: monto, estado, comision_base_pct: comision });
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
          title="Ver cómo se calculó la meta sugerida (IQR)"
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
        const isModified = pressure !== 10 && p.estado === "PROPUESTA";
        const baseValue = p.monto_meta;
        const numericMonto = isModified ? (baseValue / 1.1) * (1 + pressure / 100) : baseValue;
        const formattedMonto = new Intl.NumberFormat('es-EC', {
          style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2,
        }).format(numericMonto);
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
      key: 'comision',
      header: 'Comisión (%)',
      render: (p) => (
        <input
          type="number"
          aria-label={`Comisión para ${p.vendedor}`}
          value={p.comision_base_pct}
          onChange={(e) => {
            const newProposals = [...proposals];
            const idx = newProposals.findIndex((x) => x.id === p.id);
            if (idx !== -1) {
              newProposals[idx].comision_base_pct = parseFloat(e.target.value) || 0;
              setProposals(newProposals);
            }
          }}
          className="bg-slate-800 w-16 p-1.5 rounded border border-slate-700 focus-ring cursor-text"
        />
      ),
    },
    {
      key: 'estado',
      header: 'Estado',
      render: (p) => {
        const badge = ESTADO_BADGE[p.estado] ?? { variant: 'warning' as const, label: p.estado };
        return <AlertBadge variant={badge.variant}>{badge.label}</AlertBadge>;
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      numeric: true,
      render: (p) => {
        const isModified = pressure !== 10 && p.estado === "PROPUESTA";
        const baseValue = p.monto_meta;
        const numericMonto = isModified ? (baseValue / 1.1) * (1 + pressure / 100) : baseValue;
        return (
          <div className="flex justify-end gap-2">
            <Button
              variant="primary"
              size="sm"
              loading={reviewMut.pendingId === p.id}
              onClick={() => handleReview(p.id, "APROBADA", isModified ? numericMonto : p.monto_meta, p.comision_base_pct)}
            >
              Aprobar
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={reviewMut.pendingId === p.id}
              onClick={() => handleReview(p.id, "RECHAZADA", isModified ? numericMonto : p.monto_meta, p.comision_base_pct)}
            >
              Rechazar
            </Button>
          </div>
        );
      },
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
          >
            {months.map((m, idx) => (
              <option key={idx} value={`${m.anio}-${m.mes}`}>{m.label}</option>
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
            disabled={loading}
            onChange={(e) => setPressure(parseInt(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-teal-400 focus-ring"
          />
        </div>

        <Button variant="primary" onClick={handleGenerate} loading={loading} icon={<TrendingUp className="w-4 h-4" aria-hidden="true" />}>
          Generar Plan con Inteligencia ML
        </Button>
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
          emptyDescription="Genera el plan usando la configuración de arriba."
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
            <div className="card p-3">
              <p className="text-xs text-slate-500">Meta sugerida (estadística)</p>
              <p className="text-lg font-semibold text-slate-100">{fmtMoney(desglose.data.meta_sugerida_estadistica)}</p>
              <p className="text-xs text-slate-500 mt-1">{desglose.data.metodo_estadistico}</p>
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
                <p className="text-xs text-slate-500">Componente estacional</p>
                <p className="text-base font-semibold text-slate-200">
                  {desglose.data.componente_estacional != null ? fmtMoney(desglose.data.componente_estacional) : '—'}
                </p>
              </div>
              <div className="card p-3">
                <p className="text-xs text-slate-500">Componente tendencia</p>
                <p className="text-base font-semibold text-slate-200">{fmtMoney(desglose.data.componente_tendencia)}</p>
              </div>
            </div>
            <div className="card p-3">
              <p className="text-xs text-slate-500">Factor de tendencia aplicado</p>
              <p className="text-base font-semibold text-slate-200">{desglose.data.factor_tendencia_aplicado.toFixed(3)}×</p>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
