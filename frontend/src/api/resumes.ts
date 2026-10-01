import { apiClient } from './client';
import type {
  ResumeSummaryResponse,
  ResumeDetailResponse,
  ResumeUploadResult,
} from '../types/api';

export const resumesApi = {
  list: () => apiClient.get<ResumeSummaryResponse[]>('/resumes'),

  getById: (id: string) => apiClient.get<ResumeDetailResponse>(`/resumes/${id}`),

  getProfile: (id: string) => apiClient.get<Record<string, unknown>>(`/resumes/${id}/profile`),

  upload: (file: File, profileName: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (profileName) formData.append('profile_name', profileName);
    return apiClient.post<ResumeUploadResult>('/resumes', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};
