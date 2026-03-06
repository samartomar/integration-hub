const ACTIVE_VENDOR_KEY = "integrationHub.activeVendorCode";
const VENDOR_API_KEY_PREFIX = "VENDOR_API_KEY::";
const LEGACY_VENDOR_KEYS_KEY = "integrationHub.vendorApiKeys";

function storageKeyForVendor(vendorCode: string): string {
  return `${VENDOR_API_KEY_PREFIX}${vendorCode.trim().toUpperCase()}`;
}

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

/**
 * Clear all vendor session data from localStorage.
 * Used when API key is invalid (e.g. 401) to force re-register/login.
 */
export function clearVendorSession(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(ACTIVE_VENDOR_KEY);
    localStorage.removeItem(LEGACY_VENDOR_KEYS_KEY);
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k?.startsWith(VENDOR_API_KEY_PREFIX)) keysToRemove.push(k);
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
    window.dispatchEvent(new CustomEvent("vendorKeysChanged"));
  } catch {
    /* ignore */
  }
}

/**
 * Clear vendor session and redirect to / so user can re-register.
 * Call on 401 to avoid "ghost" sessions with deleted keys.
 */
export function resetVendorSessionAndReload(): void {
  clearVendorSession();
  setTimeout(() => {
    window.location.href = "/";
  }, 0);
}

export interface VendorSessionPayload {
  apiKey: string;
  licenseeCode?: string;
}

/**
 * Save API key and optionally set active licensee. Used by registration flow and dev switcher.
 * If licenseeCode is omitted, uses the current active vendor code.
 */
export function saveVendorApiKeyAndLicensee(payload: VendorSessionPayload): void {
  const { apiKey, licenseeCode } = payload;
  if (typeof window === "undefined") return;
  if (!apiKey.trim()) return;
  const code = licenseeCode?.trim() ?? getActiveVendorCode() ?? "";
  setVendorApiKeyForVendor(code, apiKey.trim());
  if (licenseeCode?.trim()) {
    setActiveVendorCode(licenseeCode.trim());
  }
}
