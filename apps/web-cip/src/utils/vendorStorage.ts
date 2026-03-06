/** Single source of truth for Vendor persona storage */

const ACTIVE_VENDOR_KEY = "integrationHub.activeVendorCode";
const VENDOR_API_KEY_PREFIX = "VENDOR_API_KEY::";

const LEGACY_VENDOR_KEYS_KEY = "integrationHub.vendorApiKeys";

function storageKeyForVendor(vendorCode: string): string {
  return `${VENDOR_API_KEY_PREFIX}${vendorCode.trim().toUpperCase()}`;
}

/** Migrate keys from legacy JSON map to per-vendor format (one-time) */
function migrateFromLegacyFormat(): void {
  if (typeof window === "undefined") return;
  try {
    const raw = localStorage.getItem(LEGACY_VENDOR_KEYS_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as unknown;
    if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) {
      for (const [k, v] of Object.entries(parsed)) {
        if (typeof k === "string" && typeof v === "string" && v.trim()) {
          const code = k.trim().toUpperCase();
          const key = storageKeyForVendor(code);
          if (!localStorage.getItem(key)) {
            localStorage.setItem(key, (v as string).trim());
          }
        }
      }
      localStorage.removeItem(LEGACY_VENDOR_KEYS_KEY);
      window.dispatchEvent(new CustomEvent("vendorKeysChanged"));
    }
  } catch {
    /* ignore */
  }
}

export function getActiveVendorCode(): string | null {
  if (typeof window === "undefined") return null;
  const v = localStorage.getItem(ACTIVE_VENDOR_KEY);
  return v && v.trim() ? v.trim().toUpperCase() : null;
}

export function setActiveVendorCode(code: string): void {
  if (typeof window === "undefined") return;
  const trimmed = code.trim().toUpperCase();
  if (trimmed) {
    localStorage.setItem(ACTIVE_VENDOR_KEY, trimmed);
  } else {
    localStorage.removeItem(ACTIVE_VENDOR_KEY);
  }
}

export function setVendorApiKeyForVendor(vendorCode: string, apiKey: string): void {
  if (typeof window === "undefined") return;
  migrateFromLegacyFormat();
  const key = storageKeyForVendor(vendorCode);
  if (apiKey.trim()) {
    localStorage.setItem(key, apiKey.trim());
  } else {
    localStorage.removeItem(key);
  }
  window.dispatchEvent(new CustomEvent("vendorKeysChanged"));
}

export function getVendorApiKeyForVendor(vendorCode: string): string | null {
  if (typeof window === "undefined") return null;
  migrateFromLegacyFormat();
  const key = storageKeyForVendor(vendorCode);
  const v = localStorage.getItem(key);
  return v && v.trim() ? v.trim() : null;
}
