import axios, { type AxiosInstance } from "axios";
import { getActiveVendorCode } from "../utils/vendorStorage";
import { sessionStore } from "../session/sessionStore";

function addSessionErrorInterceptor(api: AxiosInstance): void {
  api.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error?.response?.status;
      if (status === 401 || status === 403) {
        sessionStore.markExpired("Your session expired. Please reconnect.");
      } else if (status >= 500 || status == null) {
        sessionStore.markExpired("We lost connection to the backend.");
      }
      return Promise.reject(error);
    },
  );
}

export function createAdminApi(baseUrl: string): AxiosInstance {
  const api = axios.create({
    baseURL: baseUrl,
    headers: { "Content-Type": "application/json" },
  });
  // Auth: JWT Bearer only. Consuming app injects the token provider.
  addSessionErrorInterceptor(api);
  return api;
}

/** Runtime API: /v1/execute, /v1/ai/execute. Auth: JWT Bearer only. */
export function createRuntimeApi(baseUrl: string): AxiosInstance {
  const api = axios.create({
    baseURL: baseUrl,
    headers: { "Content-Type": "application/json" },
  });
  addSessionErrorInterceptor(api);
  return api;
}

export function createVendorApi(baseUrl: string): AxiosInstance {
  const api = axios.create({
    baseURL: baseUrl,
    headers: { "Content-Type": "application/json" },
  });
  // Auth: JWT Bearer only. Consuming app injects the token provider.
  addVendorContext(api);
  addSessionErrorInterceptor(api);
  return api;
}

/** Add x-vendor-code from active vendor when present (for vendor context with JWT auth). */
export function addVendorContext(api: AxiosInstance): void {
  api.interceptors.request.use((config) => {
    if (typeof window !== "undefined" && !config.headers?.["x-vendor-code"]) {
      const code = getActiveVendorCode();
      if (code) config.headers["x-vendor-code"] = code;
    }
    return config;
  });
}

export function createVendorApiPublic(baseUrl: string): AxiosInstance {
  const api = axios.create({
    baseURL: baseUrl,
    headers: { "Content-Type": "application/json" },
  });
  addSessionErrorInterceptor(api);
  return api;
}
