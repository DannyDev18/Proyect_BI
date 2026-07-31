import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Exportado (no solo local a este módulo) para que `services/session.ts` pueda hacer
// `queryClient.clear()` en el cierre de sesión (auditoría 43, H43-8): sin esto, la caché
// de un usuario sobrevive intacta al login del siguiente usuario en la misma pestaña,
// porque este singleton nunca se recrea con una navegación SPA (sin recarga de página).
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export const AppProviders = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);
