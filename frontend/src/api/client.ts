/// <reference types="vite/client" />
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL as string;

if (!API_URL) {
  console.error('[API Client] VITE_API_URL is not set. Check your .env file.');
}

export const apiClient = axios.create({
  baseURL: API_URL,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
});

// Response interceptor: pass through error detail from backend
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Attach a user-friendly message
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      error.userMessage =
        typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2);
    } else if (error.message) {
      error.userMessage = error.message;
    } else {
      error.userMessage = 'An unexpected error occurred.';
    }
    return Promise.reject(error);
  }
);

export function getErrorMessage(error: unknown): string {
  if (error && typeof error === 'object' && 'userMessage' in error) {
    return (error as { userMessage: string }).userMessage;
  }
  if (error instanceof Error) return error.message;
  return 'An unexpected error occurred.';
}
