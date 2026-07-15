export interface ProvenanceModelo {
  nombre: string;
  algoritmo: string | null;
  entrenado_en: string | null;
  activo: boolean;
}

export interface ProvenanceResponse {
  ultima_carga_dw: string | null;
  modelos: ProvenanceModelo[];
}
