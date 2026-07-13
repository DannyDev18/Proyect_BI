import { useEffect, useState } from 'react';
import type { PaginationQuery } from '../types/pagination';
import { DEFAULT_PAGE_SIZE } from '../types/pagination';

/** Estado de paginación con reset automático al cambiar `resetKey` (típicamente los
 * filtros globales) -- evita quedar en una página vacía tras un cambio de filtro que
 * reduce el total de resultados. */
export const usePagination = (resetKey: unknown, initialPageSize = DEFAULT_PAGE_SIZE) => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setPage(1); }, [JSON.stringify(resetKey)]);

  const query: PaginationQuery = { page, page_size: pageSize };

  return {
    page,
    pageSize,
    query,
    setPage,
    setPageSize: (size: number) => { setPageSize(size); setPage(1); },
  };
};
