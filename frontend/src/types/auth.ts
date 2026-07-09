export type Role = 'administrador' | 'gerencia' | 'bodega' | 'ventas';

export interface User {
  id: string | number;
  name: string;
  email: string;
  role: Role;
  sucursalId?: string;
}
