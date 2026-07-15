import { useState } from 'react';
import { GoalsConsole } from '../components/goals/GoalsConsole';
import { GoalsAISummaryPanel } from '../components/goals/GoalsAISummaryPanel';
import { CommissionTracker } from '../components/goals/CommissionTracker';
import { CommissionConfigPanel } from '../components/goals/CommissionConfigPanel';
import { CommissionSimulationPanel } from '../components/goals/CommissionSimulationPanel';
import { Tabs } from '../components/ui/Tabs';

type VistaMetas = 'operacion' | 'configuracion' | 'simulacion';

export const DashboardMetas = () => {
  const [vista, setVista] = useState<VistaMetas>('operacion');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Metas y Comisiones</h1>
          <p className="text-sm text-slate-500 mt-0.5">Aprobación, liquidación y control estratégico automatizado</p>
        </div>
      </div>

      <Tabs
        value={vista}
        onChange={(v) => setVista(v as VistaMetas)}
        items={[
          { value: 'operacion', label: 'Operación' },
          { value: 'configuracion', label: 'Comisiones Variables · Config' },
          { value: 'simulacion', label: 'Comisiones Variables · Simulación' },
        ]}
      />

      {vista === 'operacion' && (
        <>
          <div className="grid grid-cols-1">
            <GoalsConsole />
          </div>

          <CommissionTracker />

          <GoalsAISummaryPanel />
        </>
      )}

      {vista === 'configuracion' && <CommissionConfigPanel />}
      {vista === 'simulacion' && <CommissionSimulationPanel />}
    </div>
  );
};
