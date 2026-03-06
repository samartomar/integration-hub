/**
 * Dev tools are gated behind an explicit flag so prod builds are unaffected.
 * Falls back to MODE === "development" if the flag is missing.
 */
export function isDevToolsEnabled(): boolean {
  const flag = import.meta.env.VITE_VENDOR_DEV_TOOLS;
  if (typeof flag === "string") {
    return flag.toLowerCase() === "true";
  }
  return import.meta.env.MODE === "development";
}
