// utils/format.ts
export const fmt = (n?: number | null): string => {
  if (n == null || isNaN(n)) return '—';
  
  // Para valores muy grandes, usar formato compacto
  if (n >= 1_000_000) {
    return `$${(n / 1_000_000).toFixed(1)}M`;
  }
  
  // Para valores entre 1000 y 999,999, mostrar con separador de miles
  if (n >= 1_000) {
    return `$${n.toLocaleString('es-EC', { 
      minimumFractionDigits: 0, 
      maximumFractionDigits: 0 
    })}`;
  }
  
  return `$${n.toFixed(0)}`;
};

// Agregar la exportación de pct
export const pct = (n: number): string => {
  if (n == null || isNaN(n)) return '—';
  return `${n.toFixed(1)}%`;
};

// También puedes agregar fmtFull si lo necesitas
export const fmtFull = (n?: number | null): string => {
  if (n == null || isNaN(n)) return '—';
  return new Intl.NumberFormat('es-EC', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
};
export const fmtMoney = (n?: number | null): string => {
  if (n == null || isNaN(n)) return '—';
  return new Intl.NumberFormat('es-EC', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
};

// "hace Xm/h/d" a partir de un ISO datetime -- usado por la barra de procedencia de
// datos (ProvenanceRail, docs/auditoria/33_actualizacion_modulo_gerencia.md, H4).
export const timeAgo = (isoDate: string | null | undefined): string => {
  if (!isoDate) return '—';
  const diffMs = Date.now() - new Date(isoDate).getTime();
  if (diffMs < 0 || isNaN(diffMs)) return '—';
  const minutos = Math.floor(diffMs / 60_000);
  if (minutos < 1) return 'hace instantes';
  if (minutos < 60) return `hace ${minutos}m`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `hace ${horas}h`;
  const dias = Math.floor(horas / 24);
  return `hace ${dias}d`;
};

// Etiqueta del eje X del gráfico de predicción de ventas: 'semana' muestra el inicio de
// semana (MM-DD, igual al formato diario previo), 'mes' muestra "Mes AAAA" abreviado.
export const formatEjeFecha = (fecha?: string, granularidad: 'semana' | 'mes' = 'semana'): string => {
  if (!fecha) return '';
  if (granularidad === 'semana') return fecha.slice(5);
  const [anio, mes] = fecha.split('-');
  const nombre = new Date(Number(anio), Number(mes) - 1, 1).toLocaleDateString('es-EC', { month: 'short' });
  return `${nombre} ${anio}`;
};