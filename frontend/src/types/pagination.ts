// Paginación genérica reutilizable (espejo de backend/app/schemas/pagination.py,
// docs/auditoria/24_prediccion_categoria_paginacion.md).

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PaginationQuery {
  page: number;
  page_size: number;
}

export const DEFAULT_PAGE_SIZE = 25;
