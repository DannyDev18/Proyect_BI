import { api } from './http';
import type { ProvenanceResponse } from '../types/system';

export const getProvenance = () =>
  api.get<ProvenanceResponse>('/api/v1/system/provenance');
