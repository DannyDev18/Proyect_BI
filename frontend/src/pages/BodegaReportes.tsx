import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FileDown, FileSpreadsheet, Printer } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { BodegaFilterBar } from '../components/bodega/BodegaFilterBar';
import { useReporteBodega } from '../hooks/bodega';
import { descargarReporteExcel } from '../services/bodega';
import { useBodegaFiltersStore, toQueryFilters } from '../store/bodegaFiltersStore';
import { useToast } from '../store/toastStore';
import type { TipoReporteBodega } from '../types/bodega';

const REPORTES: { tipo: TipoReporteBodega; titulo: string; descripcion: string }[] = [
  {
    tipo: 'justificacion',
    titulo: 'Justificación de Abastecimiento',
    descripcion: 'Compras propuestas con justificación, rotación, proyección y transferencias (§2.1)',
  },
  {
    tipo: 'transferencias',
    titulo: 'Candidatos a Transferencia',
    descripcion: 'Excedentes vs déficits entre bodegas y ahorro por no comprar (§2.2)',
  },
  {
    tipo: 'analisis-mensual',
    titulo: 'Análisis de Stock y Abastecimiento',
    descripcion: 'Consolidado mensual: críticos, excesos, comparativa y plan de compras (§2.3)',
  },
];

const esTabla = (v: unknown): v is Record<string, unknown>[] =>
  Array.isArray(v) && v.length > 0 && typeof v[0] === 'object' && v[0] !== null;

const fmtCelda = (v: unknown): string => {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return v.toLocaleString('es-EC');
  if (typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${x}`).join(', ');
  return String(v);
};

const titulo = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** Render recursivo del JSON del reporte: listas de objetos → tablas; objetos → secciones;
 * escalares → pares clave/valor. Imprimible (window.print) = PDF del navegador. */
const SeccionReporte = ({ nombre, valor, nivel = 0 }: { nombre: string; valor: unknown; nivel?: number }) => {
  if (esTabla(valor)) {
    const columnas = [...new Set(valor.flatMap((f) => Object.keys(f)))];
    return (
      <div className="mb-6 break-inside-avoid">
        <h4 className={`font-semibold text-slate-200 print:text-black mb-2 ${nivel === 0 ? 'text-base' : 'text-sm'}`}>{titulo(nombre)}</h4>
        <div className="overflow-x-auto border border-slate-800 print:border-gray-300 rounded-lg">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 print:bg-gray-100 text-slate-500 print:text-gray-700 uppercase tracking-wider">
              <tr>{columnas.map((c) => <th key={c} className="px-3 py-2 whitespace-nowrap">{titulo(c)}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 print:divide-gray-200">
              {valor.slice(0, 60).map((fila, i) => (
                <tr key={i} className={String(fila.prioridad) === 'Alta' ? 'bg-red-500/5 print:bg-red-50' : ''}>
                  {columnas.map((c) => (
                    <td key={c} className="px-3 py-1.5 text-slate-300 print:text-black whitespace-nowrap max-w-[280px] overflow-hidden text-ellipsis">
                      {fmtCelda(fila[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {valor.length > 60 && (
          <p className="text-[11px] text-slate-500 mt-1">Mostrando 60 de {valor.length} filas — el Excel incluye todas.</p>
        )}
      </div>
    );
  }
  if (valor !== null && typeof valor === 'object') {
    const entradas = Object.entries(valor as Record<string, unknown>);
    const escalares = entradas.filter(([, v]) => v === null || typeof v !== 'object' || (Array.isArray(v) && !esTabla(v)));
    const complejas = entradas.filter(([k]) => !escalares.some(([ke]) => ke === k));
    return (
      <div className={`mb-6 ${nivel > 0 ? 'pl-1' : ''}`}>
        {nivel >= 0 && nombre && <h3 className={`font-semibold text-slate-100 print:text-black mb-3 ${nivel === 0 ? 'text-lg' : 'text-sm'}`}>{titulo(nombre)}</h3>}
        {escalares.length > 0 && (
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 mb-4">
            {escalares.map(([k, v]) => (
              <div key={k}>
                <dt className="text-[11px] uppercase tracking-widest text-slate-500 print:text-gray-500">{titulo(k)}</dt>
                <dd className="text-sm font-mono text-slate-200 print:text-black">{fmtCelda(v)}</dd>
              </div>
            ))}
          </dl>
        )}
        {complejas.map(([k, v]) => <SeccionReporte key={k} nombre={k} valor={v} nivel={nivel + 1} />)}
      </div>
    );
  }
  return null;
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in print:hidden">
        <div>
          <Link to="/bodega" className="text-xs text-slate-500 hover:text-cyan-400 flex items-center gap-1 mb-1 focus-ring rounded">
            <ArrowLeft size={12} aria-hidden="true" /> Dashboard de Bodega
          </Link>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Reportes para Gerencia</h1>
          <p className="text-sm text-slate-500 mt-0.5">Justificación de abastecimiento con evidencia del EDW y proyecciones</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="primary" size="sm" onClick={exportarExcel} disabled={reporte.loading}
            loading={descargando} icon={!descargando ? <FileSpreadsheet size={14} aria-hidden="true" /> : undefined}
            className="!bg-emerald-600 !border-emerald-600 hover:!bg-emerald-500 hover:!border-emerald-500"
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

      {/* Selector de reporte */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 print:hidden">
        {REPORTES.map((r) => (
          <button key={r.tipo} type="button" onClick={() => setTipo(r.tipo)} aria-pressed={tipo === r.tipo}
            className={`card p-4 text-left transition-all cursor-pointer border focus-ring
              ${tipo === r.tipo ? 'border-cyan-500 bg-cyan-500/5' : 'border-transparent hover:border-slate-600'}`}>
            <div className="flex items-center gap-2 mb-1">
              <FileDown size={15} aria-hidden="true" className={tipo === r.tipo ? 'text-cyan-400' : 'text-slate-500'} />
              <p className="font-semibold text-sm text-slate-200">{r.titulo}</p>
            </div>
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
            {store.almacen ? ` · Almacén: ${store.almacen}` : ' · Todas las bodegas'}
            {store.categoria ? ` · Categoría: ${store.categoria}` : ''}
          </p>
        </div>

        {reporte.loading && <p className="text-sm text-slate-500 animate-pulse-slow">Generando reporte con datos del EDW…</p>}
        {reporte.error && <p className="text-sm text-red-400">{reporte.error}</p>}
        {reporte.data && (
          <SeccionReporte nombre="" valor={reporte.data.contenido} nivel={0} />
        )}
      </div>
    </div>
  );
};
