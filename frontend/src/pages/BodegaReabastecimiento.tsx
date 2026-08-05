import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Tabs } from '../components/ui/Tabs';
import { BodegaFilterBar } from '../components/bodega/BodegaFilterBar';
import { ReplenishmentListaInteligente } from '../components/bodega/ReplenishmentListaInteligente';
import { ReplenishmentSimuladorPanel } from '../components/bodega/ReplenishmentSimuladorPanel';
import { ReplenishmentPropuestasPanel } from '../components/bodega/ReplenishmentPropuestasPanel';
import { ReplenishmentPoliticaPanel } from '../components/bodega/ReplenishmentPoliticaPanel';
import { useAuthStore } from '../store/authStore';
import { useBodegaFiltersStore, toQueryFilters } from '../store/bodegaFiltersStore';

type VistaReabastecimiento = 'lista' | 'simulador' | 'propuestas' | 'configuracion';

/** Módulo de Gestión de Inventario y Reabastecimiento (MGIR), Fase 6 de
 * docs/features/plan_modulo_inventario_reabastecimiento.md -- vistas hijas del rediseño
 * de Reabastecimiento Inteligente (docs/features/plan_reabastecimiento_inteligente.md)
 * separadas en pestañas, mismo patrón que `DashboardMetas.tsx` (Operación/Config/
 * Simulación/Bitácora) en vez de rutas independientes: las 4 vistas comparten el mismo
 * filtro global de Bodega (`BodegaFilterBar`) y no necesitan URLs propias -- una ruta
 * nueva por vista habría exigido persistir el filtro en un store compartido entre
 * rutas sin ganar nada que las pestañas no den ya. Convive con `/bodega/almacenes`
 * (Predicción de Necesidad de Compra, motor determinista sin cambios). */
export const BodegaReabastecimiento = () => {
  const { user } = useAuthStore();
  const esGerenciaOAdmin = user?.role === 'gerencia' || user?.role === 'administrador';

  const store = useBodegaFiltersStore();
  const filters = useMemo(() => toQueryFilters(store), [store]);

  const [vista, setVista] = useState<VistaReabastecimiento>('lista');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <Link to="/bodega" className="text-xs text-slate-500 hover:text-primary flex items-center gap-1 mb-1 focus-ring rounded">
            <ArrowLeft size={12} /> Dashboard de Bodega
          </Link>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Reabastecimiento Inteligente</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Priorizado por riesgo real de quiebre (stock de seguridad + punto de reorden), no por volumen de ventas
          </p>
        </div>
      </div>

      <BodegaFilterBar />

      <Tabs
        value={vista}
        onChange={(v) => setVista(v as VistaReabastecimiento)}
        items={[
          { value: 'lista', label: 'Lista inteligente' },
          { value: 'simulador', label: 'Simulador what-if' },
          { value: 'propuestas', label: 'Propuestas de compra' },
          ...(esGerenciaOAdmin ? [{ value: 'configuracion', label: 'Configuración' }] : []),
        ]}
      />

      {vista === 'lista' && <ReplenishmentListaInteligente filters={filters} />}
      {vista === 'simulador' && esGerenciaOAdmin && <ReplenishmentSimuladorPanel filters={filters} />}
      {vista === 'propuestas' && <ReplenishmentPropuestasPanel filters={filters} />}
      {vista === 'configuracion' && esGerenciaOAdmin && <ReplenishmentPoliticaPanel />}
    </div>
  );
};
