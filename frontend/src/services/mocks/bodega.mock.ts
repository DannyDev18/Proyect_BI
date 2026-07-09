// Placeholder data — no backend endpoint exists yet for reorder recommendations.
// Swap for a real services/bodega.ts call once the endpoint is available.
export interface ReorderAlert {
  sku: string;
  name: string;
  stock: number;
  demanda: number;
  reorden: number;
  estado: 'critical' | 'warning' | 'neutral';
}

export const MOCK_ALERTS: ReorderAlert[] = [
  { sku: 'TEC-0012', name: 'Laptop Pro 14',       stock: 15, demanda: 45, reorden: 30, estado: 'warning'  },
  { sku: 'HOG-0932', name: 'Lavadora Automática',  stock: 4,  demanda: 22, reorden: 15, estado: 'critical' },
  { sku: 'TEC-8821', name: 'Monitor Ultrawide 34', stock: 0,  demanda: 15, reorden: 10, estado: 'critical' },
  { sku: 'AUD-2201', name: 'Auriculares BT Pro',   stock: 32, demanda: 20, reorden: 10, estado: 'neutral'  },
];
