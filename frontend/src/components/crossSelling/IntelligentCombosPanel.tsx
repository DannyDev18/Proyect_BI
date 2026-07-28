import { Layers, Package, ShieldCheck, Sparkles, Star, TrendingUp } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { KpiCardSkeleton } from '../ui/KpiCard';
import { ErrorState } from '../ui/ErrorState';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { useCrossSellCombos } from '../../hooks/crossSelling';
import { useCrossSellStore } from '../../store/crossSellStore';
import { fmtMoney } from '../../utils/format';
import type { CombinacionInteligente } from '../../types/crossSelling';

const ICONOS_POR_ESTRATEGIA: Record<string, LucideIcon> = {
  mayor_afinidad_historica: Star,
  mayor_margen_relativo: TrendingUp,
  reincidencia_cliente: Package,
  diversidad_categorias: ShieldCheck,
};

/** Fase 4 de docs/features/plan_refactor_venta_cruzada_ia.md (CAMBIO 5/6): combos
 * generados por estrategias reales y declaradas -- cada tarjeta muestra la estrategia
 * (`Badge`) y `porque` (evidencia real, no una frase genérica). Un combo sin datos
 * suficientes simplemente no aparece (el backend ya lo filtró). */
export const IntelligentCombosPanel = ({ clienteId }: { clienteId: string | null }) => {
  const combos = useCrossSellCombos(clienteId);
  const agregarACanasta = useCrossSellStore((s) => s.agregarACanasta);

  if (combos.loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <KpiCardSkeleton /><KpiCardSkeleton />
      </div>
    );
  }
  if (combos.error) {
    return (
      <div className="card p-6">
        <ErrorState message={combos.error} onRetry={combos.refetch} />
      </div>
    );
  }

  const lista = combos.data?.combinaciones ?? [];
  if (lista.length === 0) {
    return (
      <div className="card p-6">
        <p className="text-sm text-slate-500">No hay combos con datos suficientes por ahora.</p>
      </div>
    );
  }

  const agregarCombo = (combo: CombinacionInteligente) => {
    combo.productos.forEach((p) => agregarACanasta({ codart: p.codart, nombre: p.nombre }));
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {lista.map((combo, i) => {
        const Icon = ICONOS_POR_ESTRATEGIA[combo.estrategia] ?? Sparkles;
        return (
          <div key={combo.estrategia} className="animate-fade-in-up card card-hover p-6" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="flex justify-between items-start mb-3">
              <div>
                <p className="font-sans font-semibold text-slate-200 flex items-center gap-2">
                  <Icon size={16} className="text-primary" /> {combo.nombre}
                </p>
              </div>
              <div className="flex gap-1.5">
                {combo.afinidad != null && <Badge variant="info">{combo.afinidad.toLocaleString('es-EC')} facturas</Badge>}
                {combo.popularidad != null && <Badge variant="primary">{combo.popularidad.toFixed(0)}% de su gasto</Badge>}
              </div>
            </div>
            <div className="space-y-1 mb-3">
              {combo.productos.map((p) => (
                <div key={p.codart} className="flex justify-between text-sm">
                  <span className="text-slate-300 truncate">{p.nombre}</span>
                  <span className="text-slate-500 font-mono text-xs shrink-0 ml-2">{fmtMoney(p.precio)}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between gap-3 pt-3 border-t border-slate-800">
              <p className="text-xs text-slate-500 italic flex items-center gap-1">
                <Layers size={11} className="shrink-0" /> {combo.porque}
              </p>
              <Button variant="ghost" size="sm" onClick={() => agregarCombo(combo)} className="shrink-0">
                Agregar
              </Button>
            </div>
            {combo.margen_esperado != null && (
              <p className="text-xs text-success mt-2">+{fmtMoney(combo.margen_esperado)} margen esperado</p>
            )}
          </div>
        );
      })}
    </div>
  );
};
