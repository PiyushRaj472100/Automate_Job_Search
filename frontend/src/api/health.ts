import { apiClient } from './client';
import type { HealthResponse, ReadyResponse, MetricsResponse } from '../types/api';

export const healthApi = {
  getHealth: () => apiClient.get<HealthResponse>('/health'),
  getReady: () => apiClient.get<ReadyResponse>('/ready'),
  getMetrics: () => apiClient.get<MetricsResponse>('/metrics'),
};
