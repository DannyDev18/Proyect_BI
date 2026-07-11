import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface GoalProgressGaugeProps {
  /** Porcentaje de cumplimiento, 0-100+ (puede superar 100 si se sobrecumplió la meta). */
  pctCumplimiento: number;
  height?: number;
}

interface Zone {
  from: number; // fracción del dominio [0, DOMAIN_MAX]
  to: number;
  color: string;
}

// Mismos 4 tramos que docs/modulo_metas.md ("PROPUESTA IA" Fase 1/4) y
// commission_engine.py (UMBRAL_CERCA/META/EXCELENTE): las fronteras del arco codifican
// los umbrales reales de comisión, no son decorativas.
const ZONES: Zone[] = [
  { from: 0, to: 0.8, color: '#ef4444' },   // Lejos -- red-500
  { from: 0.8, to: 0.9, color: '#f59e0b' }, // Cerca -- amber-500
  { from: 0.9, to: 1.0, color: '#22d3ee' }, // Meta -- cyan-400
  { from: 1.0, to: 1.3, color: '#22c55e' }, // Excelente -- green-500
];
const DOMAIN_MAX = 1.3;
const BOUNDARIES = [0, 0.8, 0.9, 1.0, 1.3];

export const GoalProgressGauge = ({ pctCumplimiento, height = 200 }: GoalProgressGaugeProps) => {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const width = 320;
    const cx = width / 2;
    const cy = height - 28;
    const radius = Math.min(width / 2, height) - 30;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width} ${height}`).attr('preserveAspectRatio', 'xMidYMid meet');

    const angleScale = d3.scaleLinear().domain([0, DOMAIN_MAX]).range([-Math.PI / 2, Math.PI / 2]).clamp(true);

    const g = svg.append('g').attr('transform', `translate(${cx},${cy})`);

    const arcGen = d3
      .arc<Zone>()
      .innerRadius(radius - 20)
      .outerRadius(radius)
      .startAngle((d) => angleScale(d.from))
      .endAngle((d) => angleScale(d.to))
      .cornerRadius(2);

    g.selectAll('path.zone')
      .data(ZONES)
      .join('path')
      .attr('class', 'zone')
      .attr('d', arcGen as unknown as (d: Zone) => string)
      .attr('fill', (d) => d.color)
      .attr('opacity', 0.9);

    BOUNDARIES.forEach((b) => {
      const angle = angleScale(b) - Math.PI / 2;
      const lx = Math.cos(angle) * (radius + 13);
      const ly = Math.sin(angle) * (radius + 13);
      g.append('text')
        .attr('x', lx)
        .attr('y', ly)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('class', 'fill-slate-500')
        .style('font-size', '9px')
        .style('font-family', 'JetBrains Mono, monospace')
        .text(`${Math.round(b * 100)}`);
    });

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const valueFraction = Math.max(0, pctCumplimiento) / 100;
    const needleAngle = angleScale(valueFraction) - Math.PI / 2;
    const needleLength = radius - 28;
    const targetX = Math.cos(needleAngle) * needleLength;
    const targetY = Math.sin(needleAngle) * needleLength;

    const needle = g
      .append('line')
      .attr('x1', 0)
      .attr('y1', 0)
      .attr('x2', 0)
      .attr('y2', -4)
      .attr('stroke', '#f8fafc')
      .attr('stroke-width', 3)
      .attr('stroke-linecap', 'round');

    g.append('circle').attr('r', 5).attr('fill', '#f8fafc').attr('stroke', '#0f172a').attr('stroke-width', 1.5);

    if (prefersReducedMotion) {
      needle.attr('x2', targetX).attr('y2', targetY);
    } else {
      needle.transition().duration(900).ease(d3.easeCubicOut).attr('x2', targetX).attr('y2', targetY);
    }
  }, [pctCumplimiento, height]);

  return (
    <svg
      ref={svgRef}
      className="w-full"
      style={{ height }}
      role="img"
      aria-label={`Medidor de cumplimiento de meta: ${pctCumplimiento.toFixed(1)}%`}
    />
  );
};
