import { apiClient } from './client';
import type { SheetStatusResponse, SheetCreateResponse } from '../types/api';

export const sheetsApi = {
  getStatus: (resumeId: string) =>
    apiClient.get<SheetStatusResponse>(`/resumes/${resumeId}/sheets`),

  create: (resumeId: string) =>
    apiClient.post<SheetCreateResponse>(`/resumes/${resumeId}/sheets`),
};
