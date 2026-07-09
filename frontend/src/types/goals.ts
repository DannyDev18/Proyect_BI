export interface GoalProposal {
  id: number;
  vendedor: string;
  sucursal: string;
  monto_meta: number;
  comision_base_pct: number;
  estado: string;
}

export interface GoalPeriod {
  anio: number;
  mes: number;
}

export interface GoalPeriodOption extends GoalPeriod {
  label: string;
}
