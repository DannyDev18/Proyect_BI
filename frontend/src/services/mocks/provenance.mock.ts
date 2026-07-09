// Placeholder facts for the Data Provenance Rail — no dedicated data-lineage
// endpoint exists yet. Swap for a real services/ call (e.g. GET /api/v1/system/status)
// once the backend exposes DW sync + model freshness metadata.
export const PROVENANCE_FACTS: string[] = [
  'DW sync 2m ago',
  'Gradient Boosting v3',
  'Isolation Forest activo',
];
