export function isFeatureEnabled(
  effectiveFeatures: Record<string, boolean> | null | undefined,
  featureCode: string
): boolean {
  const code = featureCode?.trim();
  if (!code) return false;
  return effectiveFeatures?.[code] === true;
}
