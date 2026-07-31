// utils/apiError.ts
import { isAxiosError } from 'axios';

/**
 * Extrae un mensaje de error legible para el usuario a partir de un error de TanStack Query.
 * FastAPI devuelve el detalle de negocio en `response.data.detail` (string o lista de errores
 * de validación Pydantic); sin esto, el mensaje que llegaba a la UI era el genérico de axios
 * ("Request failed with status code 400"), que no le dice nada al usuario sobre qué corregir.
 */
export const getApiErrorMessage = (error: unknown): string | null => {
  if (!error) return null;

  if (isAxiosError(error)) {
    if (!error.response) {
      return 'No se pudo conectar con el servidor. Verifica tu conexión e intenta nuevamente.';
    }
    const detail = error.response.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const mensajes = detail
        .map((d) => (typeof d === 'string' ? d : d?.msg))
        .filter(Boolean);
      if (mensajes.length > 0) return mensajes.join(' · ');
    }
    if (error.response.status === 404) return 'No se encontró la información solicitada.';
    if (error.response.status === 403) return 'No tienes permisos para acceder a esta información.';
    return 'Ocurrió un error al procesar la solicitud. Intenta nuevamente.';
  }

  return error instanceof Error ? error.message : 'Error al cargar datos';
};
