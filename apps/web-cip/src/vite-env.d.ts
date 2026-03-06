/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ADMIN_API_BASE_URL: string;
  readonly VITE_VENDOR_API_BASE_URL?: string;
  readonly VITE_RUNTIME_API_BASE_URL?: string;
  readonly VITE_PHI_APPROVED_GROUP?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
