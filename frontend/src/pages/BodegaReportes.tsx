import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FileDown, FileSpreadsheet, Printer } from 'lucide-react';
import { AlertBadge } from '../components/ui/AlertBadge';
import { Button } from '../components/ui/Button';
import { BodegaFilterBar } from '../components/bodega/BodegaFilterBar';
import { useReporteBodega } from '../hooks/bodega';
import { descargarReporteExcel } from '../services/bodega';
import { useBodegaFiltersStore, toQueryFilters } from '../store/bodegaFiltersStore';
import { useToast } from '../store/toastStore';
import type { ColumnaReporte, SeccionReporte, TipoReporteBodega, TonoKpi } from '../types/bodega';

const REPORTES: { tipo: TipoReporteBodega; titulo: string; pregunta: string; descripcion: string }[] = [
  {
    tipo: 'justificacion',
    titulo: 'Justificación de Abastecimiento',
    pregunta: '¿Qué comprar este mes y por qué?',
    descripcion: 'Compras propuestas con justificación, rotación, proyección y transferencias (§2.1)',
  },
  {
    tipo: 'transferencias',
    titulo: 'Candidatos a Transferencia',
    pregunta: '¿Qué mover entre bodegas?',
    descripcion: 'Excedentes vs déficits entre bodegas, con justificación estadística y confianza (§2.2)',
  },
  {
    tipo: 'analisis-mensual',
    titulo: 'Análisis de Stock y Abastecimiento',
    pregunta: '¿Cómo cerró el mes el inventario?',
    descripcion: 'Consolidado mensual: críticos, excesos, comparativa y plan de compras (§2.3)',
  },
];

const tonoCls: Record<TonoKpi, string> = {
  positivo: 'text-success',
  negativo: 'text-danger',
  neutral: 'text-slate-200',
};

const RESALTAR_VALORES = new Set(['Alta', 'Crítico']);
const BADGE_VARIANT: Record<string, 'critical' | 'warning' | 'info' | 'success' | 'neutral'> = {
  alta: 'critical', crítico: 'critical',
  media: 'warning', cerca: 'warning', baja: 'neutral',
  seguro: 'success', exceso: 'info',
};

const fmtCelda = (valor: unknown, columna: ColumnaReporte): React.ReactNode => {
  if (valor === null || valor === undefined || valor === '') return '—';
  if (columna.tipo === 'badge') {
    const variant = BADGE_VARIANT[String(valor).toLowerCase()] ?? 'neutral';
    return <AlertBadge variant={variant}>{String(valor)}</AlertBadge>;
  }
  if (columna.tipo === 'moneda' && typeof valor === 'number') {
    return valor.toLocaleString('es-EC', { style: 'currency', currency: 'USD' });
  }
  if (columna.tipo === 'porcentaje' && typeof valor === 'number') {
    return `${valor > 0 ? '+' : ''}${valor.toFixed(1)}%`;
  }
  if (columna.tipo === 'numero' && typeof valor === 'number') {
    return valor.toLocaleString('es-EC', { maximumFractionDigits: 2 });
  }
  return String(valor);
};

/** Fase 5 (docs/features/plan_actualizacion_modulo_bodega.md): tabla con columnas de
 * negocio ya definidas por el backend -- ya no se deriva de las claves crudas del JSON. */
const TablaSeccion = ({ seccion }: { seccion: SeccionReporte }) => {
  const MAX_FILAS = 60;
  const filas = seccion.filas.slice(0, MAX_FILAS);
  return (
    <div className="mb-8 break-inside-avoid">
      <h3 className="font-semibold text-slate-100 print:text-black text-base mb-1">{seccion.titulo}</h3>
      {seccion.descripcion && (
        <p className="text-xs text-slate-500 print:text-gray-600 mb-2">{seccion.descripcion}</p>
      )}
      {filas.length === 0 ? (
        <p className="text-xs text-slate-500 italic">Sin datos con los filtros actuales.</p>
      ) : (
        <div className="overflow-x-auto border border-slate-800 print:border-gray-300 rounded-lg">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 print:bg-gray-100 text-slate-500 print:text-gray-700 uppercase tracking-wider">
              <tr>{seccion.columnas.map((c) => <th key={c.key} className="px-3 py-2 whitespace-nowrap">{c.etiqueta}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 print:divide-gray-200">
              {filas.map((fila, i) => {
                const resaltar = seccion.resaltar_key != null && RESALTAR_VALORES.has(String(fila[seccion.resaltar_key]));
                return (
                  <tr key={i} className={resaltar ? 'bg-danger/5 print:bg-danger' : ''}>
                    {seccion.columnas.map((c) => (
                      <td key={c.key} className="px-3 py-1.5 text-slate-300 print:text-black whitespace-nowrap max-w-[280px] overflow-hidden text-ellipsis">
                        {fmtCelda(fila[c.key], c)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {seccion.filas.length > MAX_FILAS && (
        <p className="text-[11px] text-slate-500 mt-1">Mostrando {MAX_FILAS} de {seccion.filas.length} filas — el Excel incluye todas.</p>
      )}
    </div>
  );
};

/** §2: Reportes de bodega para presentación a gerencia, con export Excel y PDF (print). */
export const BodegaReportes = () => {
  const store = useBodegaFiltersStore();
  const filters = useMemo(() => toQueryFilters(store), [store]);
  const [tipo, setTipo] = useState<TipoReporteBodega>('justificacion');
  const [descargando, setDescargando] = useState(false);
  const reporte = useReporteBodega(tipo, filters);
  const meta = REPORTES.find((r) => r.tipo === tipo)!;
  const toast = useToast();

  const exportarExcel = async () => {
    setDescargando(true);
    try {
      await descargarReporteExcel(tipo, filters);
      toast('Reporte Excel descargado correctamente.', 'success');
    } catch {
      toast('No se pudo descargar el reporte Excel. Intenta nuevamente.', 'error');
    } finally {
      setDescargando(false);
    }
  };

  const filtrosAplicados = reporte.data ? Object.entries(reporte.data.filtros_aplicados) : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in print:hidden">
        <div>
          <Link to="/bodega" className="text-xs text-slate-500 hover:text-primary flex items-center gap-1 mb-1 focus-ring rounded">
            <ArrowLeft size={12} aria-hidden="true" /> Dashboard de Bodega
          </Link>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Reportes para Gerencia</h1>
          <p className="text-sm text-slate-500 mt-0.5">Justificación de abastecimiento con evidencia del EDW y proyecciones</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="success" size="sm" onClick={exportarExcel} disabled={reporte.loading}
            loading={descargando} icon={!descargando ? <FileSpreadsheet size={14} aria-hidden="true" /> : undefined}
            aria-label="Exportar reporte a Excel">
            {descargando ? 'Generando…' : 'Exportar Excel'}
          </Button>
          <Button variant="primary" size="sm" onClick={() => window.print()} disabled={reporte.loading}
            icon={<Printer size={14} aria-hidden="true" />} aria-label="Imprimir o exportar a PDF">
            Imprimir / PDF
          </Button>
        </div>
      </div>

      <div className="print:hidden">
        <BodegaFilterBar />
      </div>

      {/* Selector de reporte: cada tarjeta explica qué decisión soporta */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 print:hidden">
        {REPORTES.map((r) => (
          <button key={r.tipo} type="button" onClick={() => setTipo(r.tipo)} aria-pressed={tipo === r.tipo}
            className={`card p-4 text-left transition-all cursor-pointer border focus-ring
              ${tipo === r.tipo ? 'border-primary bg-primary/5' : 'border-transparent hover:border-slate-600'}`}>
            <div className="flex items-center gap-2 mb-1">
              <FileDown size={15} aria-hidden="true" className={tipo === r.tipo ? 'text-primary' : 'text-slate-500'} />
              <p className="font-semibold text-sm text-slate-200">{r.pregunta}</p>
            </div>
            <p className="text-xs text-slate-400 mb-1">{r.titulo}</p>
            <p className="text-xs text-slate-500">{r.descripcion}</p>
          </button>
        ))}
      </div>

      {/* Contenido del reporte (imprimible) */}
      <div className="card p-8 print:shadow-none print:border-none print:bg-white print:text-black">
        <div className="border-b border-slate-800 print:border-gray-300 pb-4 mb-6">
          <h2 className="text-xl font-display font-semibold text-slate-100 print:text-black">{meta.titulo}</h2>
          <p className="text-xs text-slate-500 print:text-gray-600 mt-1">
            Generado: {reporte.data?.generado_en ?? '…'} · Plataforma Inteligente de Analítica Empresarial
          </p>
          {filtrosAplicados.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {filtrosAplicados.map(([k, v]) => (
                <span key={k} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 print:bg-gray-100 text-slate-400 print:text-gray-700 border border-slate-700 print:border-gray-300">
                  {k.replace(/_/g, ' ')}: {String(v)}
                </span>
              ))}
            </div>
          )}
        </div>

        {reporte.loading && <p className="text-sm text-slate-500 animate-pulse-slow">Generando reporte con datos del EDW…</p>}
        {reporte.error && <p className="text-sm text-danger">{reporte.error}</p>}
        {reporte.data && (
          <>
            {/* Banda de KPIs del resumen ejecutivo */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
              {reporte.data.resumen_ejecutivo.map((kpi) => (
                <div key={kpi.etiqueta} className="border border-slate-800 print:border-gray-300 rounded-lg p-3">
                  <p className="text-[10px] uppercase tracking-widest text-slate-500 print:text-gray-500">{kpi.etiqueta}</p>
                  <p className={`text-lg font-mono font-semibold ${tonoCls[kpi.tono]} print:text-black`}>{kpi.valor}</p>
                </div>
              ))}
            </div>

            {/* Interpretación en lenguaje natural */}
            <p className="text-sm text-slate-300 print:text-black bg-slate-900/60 print:bg-gray-50 border border-slate-800 print:border-gray-300 rounded-lg p-4 mb-6">
              {reporte.data.interpretacion}
            </p>

            {reporte.data.secciones.map((s) => <TablaSeccion key={s.titulo} seccion={s} />)}
          </>
        )}
      </div>
    </div>
  );
};
