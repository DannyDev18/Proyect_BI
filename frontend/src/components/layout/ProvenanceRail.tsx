import { useProvenance } from '../../hooks/system';
import { timeAgo } from '../../utils/format';

/**
 * Data Provenance Rail — a persistent, low-contrast strip of system/data-lineage
 * facts, present on every authenticated page. Static (no marquee/scroll) so it
 * respects prefers-reduced-motion by default and stays simple.
 *
 * Antes consumía un mock estático (`services/mocks/provenance.mock.ts`) con strings
 * hardcodeados presentados como estado real del sistema -- docs/auditoria/
 * 33_actualizacion_modulo_gerencia.md, H4. Ahora consume GET /system/provenance
 * (última carga del DW + estado real de los 6 modelos ML).
 */
export const ProvenanceRail = () => {
  const { data, loading } = useProvenance();

  const facts = loading || !data
    ? ['Cargando estado del sistema…']
    : [
        `DW sync ${timeAgo(data.ultima_carga_dw)}`,
        ...data.modelos
          .filter((m) => m.activo)
          .map((m) => `${m.nombre}${m.algoritmo ? ` (${m.algoritmo})` : ''} activo`),
      ];

  return (
    <div className="h-8 flex items-center px-4 md:px-8 border-b border-slate-800 bg-slate-950 text-[11px] font-mono text-slate-500 tracking-wide overflow-hidden whitespace-nowrap flex-shrink-0">
      {facts.join('  ·  ')}
    </div>
  );
};
