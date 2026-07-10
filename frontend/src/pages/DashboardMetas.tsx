import { GoalsConsole } from '../components/goals/GoalsConsole';
import { GoalsAISummaryPanel } from '../components/goals/GoalsAISummaryPanel';

export const DashboardMetas = () => {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-between items-center gap-3 animate-fade-in">
        <div>
          <h1 className="text-3xl font-display font-semibold text-slate-100">Metas y Comisiones</h1>
          <p className="text-sm text-slate-500 mt-0.5">Aprobación, liquidación y control estratégico automatizado</p>
        </div>
      </div>

      <div className="grid grid-cols-1">
          <GoalsConsole />
      </div>

      <GoalsAISummaryPanel />
    </div>
  );
};
