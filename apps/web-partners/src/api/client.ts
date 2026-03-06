import {
  createVendorApi,
  createVendorApiPublic,
  createRuntimeApi,
} from "frontend-shared";
import type { AxiosInstance } from "axios";
import { getVendorApiBaseUrl, getRuntimeApiBaseUrl } from "../config/apiConfig";
import { getAuthTokenProvider } from "./authTokenProvider";

const vendorBaseUrl = getVendorApiBaseUrl();
const runtimeBaseUrl = getRuntimeApiBaseUrl();

function addBearerToken(api: AxiosInstance): void {
  api.interceptors.request.use(async (config) => {
    const getToken = getAuthTokenProvider();
    if (getToken) {
      const token = await getToken();
      if (token) config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });
}

const vendorApiInstance = createVendorApi(vendorBaseUrl);
const runtimeApiInstance = createRuntimeApi(runtimeBaseUrl);
addBearerToken(vendorApiInstance);
addBearerToken(runtimeApiInstance);
vendorApiInstance.interceptors.response.use(
  (r) => r,
  (err) => {
    const data = err.response?.data;
    const status = err.response?.status;
    // 401/403/5xx are handled by sessionStore in createVendorApi; banner shows instead of auto-reload
    if (typeof data === "string" && data.trimStart().startsWith("<")) {
      const hint =
        import.meta.env.DEV
          ? "Set VITE_VENDOR_API_BASE_URL to your Vendor API URL (or use .env.local with http://localhost:8080 for local dev)."
          : "VITE_VENDOR_API_BASE_URL may point to the SPA instead of the API.";
      return Promise.reject(
        new Error(
          `Vendor API returned HTML instead of JSON. ${hint} Check DevTools Network tab for the request URL.`,
        ),
      );
    }
    if (status === 403 && data && typeof data === "object") {
      const msg =
        (data as { error?: { message?: string } })?.error?.message ??
        (data as { message?: string })?.message;
      if (msg) {
        return Promise.reject(new Error(`${status} Forbidden: ${msg}`));
      }
    }
    return Promise.reject(err);
  },
);
export const vendorApi: AxiosInstance = vendorApiInstance;
export const runtimeApi: AxiosInstance = runtimeApiInstance;
export const vendorApiPublic: AxiosInstance =
  createVendorApiPublic(vendorBaseUrl);
