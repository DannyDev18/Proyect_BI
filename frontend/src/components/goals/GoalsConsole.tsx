import { useState, useEffect } from "react";
import {
  CheckCircle,
  XCircle,
  TrendingUp,
  Trophy,
  AlertTriangle,
  Loader2,
} from "lucide-react";

interface GoalProposal {
  id: number;
  vendedor: string;
  monto_meta: number;
  comision_base_pct: number;
  estado: string;
}

import { api } from "../../services/api";

export function GoalsConsole() {
  const [proposals, setProposals] = useState<GoalProposal[]>([]);
  const [pressure, setPressure] = useState<number>(10);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  const [months, setMonths] = useState<{anio: number, mes: number, label: string}[]>([]);
  const [period, setPeriod] = useState({ anio: new Date().getFullYear(), mes: new Date().getMonth() + 1 });

  useEffect(() => {
    fetchPeriods();
  }, []);

  const fetchPeriods = async () => {
    try {
      const res = await api.get(`/api/v1/gerencia/goals/periods`);
      const data = res.data || [];
      const mapped = data.map((d: any) => {
        const date = new Date(d.anio, d.mes - 1, 1);
        const name = date.toLocaleString('es-ES', { month: 'long' });
        return {
          anio: d.anio,
          mes: d.mes,
          label: `${name.charAt(0).toUpperCase() + name.slice(1)} ${d.anio}`
        }
      });
      setMonths(mapped);
      if (mapped.length > 0) {
        setPeriod({ anio: mapped[0].anio, mes: mapped[0].mes });
      }
    } catch (err) {
      console.error(err);
    }
  };
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchProposals();
  }, [period]);

  const fetchProposals = async () => {
    setLoading(true);
    try {
      const res = await api.get(
        `/api/v1/gerencia/goals/tracking?anio=${period.anio}&mes=${period.mes}`,
      );
      setProposals(res.data.reporte_cumplimiento || []);
    } catch (err) {
      console.error("Error cargando metas:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    const factor = 1 + pressure / 100;
    try {
      await api.post(
        `/api/v1/gerencia/goals/generate?anio=${period.anio}&mes=${period.mes}&pressure_factor=${factor}`
      );
      await fetchProposals();
    } catch (err) {
      console.error("Error generando metas:", err);
      setLoading(false);
    }
  };

  const handleReview = async (
    id: number,
    estado: "APROBADA" | "RECHAZADA",
    monto: number,
    comision: number,
  ) => {
    setActionLoadingId(id);
    try {
      await api.put(`/api/v1/gerencia/goals/${id}/review`, {
        monto_meta: monto,
        estado: estado,
        comision_base_pct: comision,
      });
      await fetchProposals();
    } catch (err) {
      console.error("Error procesando aprobacion:", err);
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="p-6 bg-slate-900 text-white rounded-lg border border-slate-800 shadow-xl max-w-7xl mx-auto mt-6">
      <div className="flex items-center gap-3 mb-6">
        <Trophy className="w-8 h-8 text-teal-400" />
        <h2 className="text-2xl font-bold tracking-tight">
          Consola Inteligente de Metas & Comisiones
        </h2>
      </div>

      {/* Panel de Configuración Automática con Cursors definidos */}
      <div className="p-5 bg-slate-800/50 rounded-lg mb-6 flex flex-wrap gap-6 items-center border border-slate-700/50">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400">
            Año / Mes de Planificación
          </label>
          <select
            className="bg-slate-800 p-2 rounded text-sm border border-slate-700 cursor-pointer focus:border-teal-400 focus:outline-none transition-colors"
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
          </select>
        </div>

        <div className="flex-1 min-w-[200px] flex flex-col gap-1">
          <label className="text-xs font-semibold text-slate-400">
            Factor de Presión Comercial (+{pressure}%)
          </label>
          <input
            type="range"
            min="0"
            max="25"
            value={pressure}
            disabled={loading}
            onChange={(e) => setPressure(parseInt(e.target.value))}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-teal-400"
          />
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading}
          className="bg-teal-500 hover:bg-teal-400 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 font-bold py-2.5 px-5 rounded text-sm transition-all duration-200 ease-in-out cursor-pointer flex items-center gap-2"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <TrendingUp className="w-4 h-4" />
          )}
          Generar Plan con Inteligencia ML
        </button>
      </div>

      {/* Grilla Interactiva */}
      <div className="bg-slate-800/50 rounded-lg p-5 border border-slate-700/50">
        <h3 className="text-lg font-semibold mb-4 text-slate-200">
          Revisión de Flujo y Propuestas
        </h3>

        {loading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-10 h-10 animate-spin text-teal-400" />
          </div>
        ) : proposals.length === 0 ? (
          <div className="text-center py-10 text-slate-400">
            No hay metas propuestas para este periodo. Genera el plan usando la configuración de arriba.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 font-medium">
                  <th className="p-3">Vendedor</th>
                  <th className="p-3">Sucursal</th>
                  <th className="p-3">Meta Propuesta ($)</th>
                  <th className="p-3">Comisión (%)</th>
                  <th className="p-3">Estado</th>
                  <th className="p-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {[...proposals].sort((a, b) => a.vendedor.localeCompare(b.vendedor)).map((p) => {
                  // Calcular dinámicamente el valor mostrado si no está aprobada/tachada aún, o simplemente mostrar efecto visual
                  // Como "pressure" en el backend aplica un factor base (1.10 etc),
                  // si el usuario mueve el slider "en vivo" aplicaremos (valor_original / 1.10_default * nuevo_factor).
                  // Pero como no sabemos el default con el que se generó, lo más sencillo
                  // si no está aprobada, es aplicar un factor adicional simulado O asumir que el default era 10%
                  const isModified = pressure !== 10 && p.estado === "PROPUESTA";
                  const baseValue = p.monto_meta;
                  
                  // 1. Calculamos el monto numérico a enviar al backend
                  const numericMonto = isModified ? (baseValue / 1.1) * (1 + pressure / 100) : baseValue;
                  
                  // 2. Generamos el formato visual que configuraste
                  const formattedMonto = new Intl.NumberFormat('es-EC', {
                    style: 'currency',
                    currency: 'USD',
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                  }).format(numericMonto);

                  return (
                  <tr
                    key={p.id}
                    className="border-b border-slate-800 hover:bg-slate-800/50 transition-all duration-150"
                  >
                    <td className="p-3 font-semibold text-teal-50">
                      {p.vendedor}
                    </td>
                    <td className="p-3 text-slate-300">
                      {p.sucursal}
                    </td>
                    <td className="p-3">
                      <input
                        type="text"
                        value={isModified ? formattedMonto : new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(p.monto_meta)}
                        onChange={(e) => {
                          const newProposals = [...proposals];
                          const idx = newProposals.findIndex((x) => x.id === p.id);
                          if (idx !== -1) {
                            // Extraer solo dígitos para que el estado puro sea número si el usuario edita
                            const cleaned = e.target.value.replace(/[^0-9.-]+/g,"");
                            newProposals[idx].monto_meta = parseFloat(cleaned) || 0;
                            setProposals(newProposals);
                          }
                        }}
                        className="bg-slate-800 w-32 p-1.5 rounded border border-slate-700 focus:outline-none focus:border-teal-400 transition-colors cursor-text"
                      />
                    </td>
                    <td className="p-3">
                      <input
                        type="number"
                        value={p.comision_base_pct}
                        onChange={(e) => {
                          const newProposals = [...proposals];
                          const idx = newProposals.findIndex((x) => x.id === p.id);
                          if (idx !== -1) {
                            newProposals[idx].comision_base_pct = parseFloat(e.target.value) || 0;
                            setProposals(newProposals);
                          }
                        }}
                        className="bg-slate-800 w-16 p-1.5 rounded border border-slate-700 focus:outline-none focus:border-teal-400 transition-colors cursor-text"
                      />
                    </td>
                    <td className="p-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                          p.estado === "APROBADA"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
                            : p.estado === "RECHAZADA"
                            ? "bg-rose-500/10 text-rose-400 border border-rose-500/25" 
                            : "bg-amber-500/10 text-amber-400 border border-amber-500/25"
                        }`}
                      >
                        {p.estado === "APROBADA" ? (
                          <CheckCircle className="w-3.5 h-3.5" />
                        ) : p.estado === "RECHAZADA" ? (
                          <XCircle className="w-3.5 h-3.5" />
                        ) : (
                          <AlertTriangle className="w-3.5 h-3.5" />
                        )}
                        {p.estado}
                      </span>
                    </td>
                    <td className="p-3 text-right flex justify-end gap-2">
                      <button
                        onClick={() =>
                          handleReview(
                            p.id,
                            "APROBADA",
                            isModified ? numericMonto : p.monto_meta,
                            p.comision_base_pct,
                          )
                        }
                        disabled={actionLoadingId === p.id}
                        className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold py-1.5 px-3 rounded text-xs transition-colors duration-200 cursor-pointer flex items-center gap-1"
                      >
                        {actionLoadingId === p.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : null}
                        Aprobar
                      </button>
                      <button
                        onClick={() =>
                          handleReview(
                            p.id,
                            "RECHAZADA",
                            isModified ? numericMonto : p.monto_meta,
                            p.comision_base_pct,
                          )
                        }
                        disabled={actionLoadingId === p.id}
                        className="bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-semibold py-1.5 px-3 rounded text-xs transition-colors duration-200 cursor-pointer flex items-center gap-1"
                      >
                        {actionLoadingId === p.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : null}
                        Rechazar
                      </button>
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
