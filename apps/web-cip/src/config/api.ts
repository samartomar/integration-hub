import { getAdminApiBaseUrl, getVendorApiBaseUrl } from "./apiConfig";

export const apiConfig = {
  get adminApiBaseUrl() {
    return getAdminApiBaseUrl();
  },
  get vendorApiBaseUrl() {
    return getVendorApiBaseUrl();
  },
};
