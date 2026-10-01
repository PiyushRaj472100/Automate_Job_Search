import { apiClient } from './client';
import type {
  SourcePolicy,
  SourceHealthCheck,
  SearchQuery,
  QueryGenerationRequest,
  SearchDiscoveryRequest,
  SearchDiscoveryResponse,
} from '../types/api';

export const discoveryApi = {
  getSources: () => apiClient.get<Record<string, SourcePolicy>>('/discovery/sources'),

  getSourceHealth: () =>
    apiClient.get<Record<string, SourceHealthCheck>>('/discovery/health'),

  generateQueries: (payload: QueryGenerationRequest) =>
    apiClient.post<SearchQuery[]>('/discovery/generate-queries', payload),

  search: (payload: SearchDiscoveryRequest) =>
    apiClient.post<SearchDiscoveryResponse>('/discovery/search', payload),
};
