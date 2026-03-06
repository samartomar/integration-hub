import type { AxiosInstance } from "axios";
import {
  createAdminApi,
  createVendorApi,
  createVendorApiPublic,
  createRuntimeApi,
} from "frontend-shared";
import {
  getAdminApiBaseUrl,
  getVendorApiBaseUrl,
  getRuntimeApiBaseUrl,
} from "../config/apiConfig";
import { getAuthTokenProvider } from "./authTokenProvider";

const adminBaseUrl = getAdminApiBaseUrl();
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

export const adminApi = createAdminApi(adminBaseUrl);
export const vendorApi = createVendorApi(vendorBaseUrl);
export const vendorApiPublic = createVendorApiPublic(vendorBaseUrl);
export const runtimeApi = createRuntimeApi(runtimeBaseUrl);

addBearerToken(adminApi);
addBearerToken(vendorApi);
addBearerToken(runtimeApi);
