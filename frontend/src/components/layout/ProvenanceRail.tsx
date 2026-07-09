import { PROVENANCE_FACTS } from '../../services/mocks/provenance.mock';

/**
 * Data Provenance Rail — a persistent, low-contrast strip of system/data-lineage
 * facts, present on every authenticated page. Static (no marquee/scroll) so it
 * respects prefers-reduced-motion by default and stays simple.
 */
export const ProvenanceRail = () => (
  <div className="h-8 flex items-center px-4 md:px-8 border-b border-slate-800 bg-slate-950 text-[11px] font-mono text-slate-500 tracking-wide overflow-hidden whitespace-nowrap flex-shrink-0">
    {PROVENANCE_FACTS.join('  ·  ')}
  </div>
);
