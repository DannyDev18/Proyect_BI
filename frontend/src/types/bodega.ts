export interface BodegaKPIs {
  items_riesgo_desabastecimiento: number;
  items_sobrestock: number;
  valorizacion_inventario: number;
  rotacion_mensual: number;
  alertas_criticas?: number;
}

export interface DemandaResponse {
  producto_cod: string;
  demanda_proxima_semana: number;
}
