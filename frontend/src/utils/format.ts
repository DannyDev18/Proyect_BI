export const fmt = (n?: number | null): string => {
  if (n == null || isNaN(n)) return '—';
  return n >= 1_000_000
    ? `$${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000
    ? `$${(n / 1_000).toFixed(0)}k`
    : `$${n.toFixed(0)}`;
};

export const pct = (n: number): string => `${n.toFixed(1)}%`;
